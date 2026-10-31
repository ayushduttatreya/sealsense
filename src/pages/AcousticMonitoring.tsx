import { useState, useRef, useEffect } from 'react';
import {
  Mic, MicOff, FlaskConical, Clock, Info, Check, X,
  Activity, Volume2, CheckCheck, ShieldAlert, Layers,
  Upload, FileAudio, AlertTriangle, Sparkles, Loader2, RefreshCw,
  Database, Trash2, Download, Search, Filter, Edit3, BarChart3,
  CheckCircle2, BookOpen, ExternalLink, Play
} from 'lucide-react';
import { SourceBadge } from '../components/SourceBadge';
import { api } from '../lib/api';
import type {
  AcousticEvent, ValidationStatus, AcousticInferenceResult,
  RetainedAudioSample, GroundTruthLabel, VerificationMethod, DatasetEvaluationReport,
  ReferenceAudioCatalogItem
} from '../types';

interface Props {
  events: AcousticEvent[];
  onValidate?: (id: string, status: 'validated' | 'rejected', notes: string) => Promise<void>;
  onBatchReview?: (eventIds: string[], action?: 'reviewed' | 'validated' | 'rejected', notes?: string) => Promise<void>;
}

function statusColor(status: AcousticEvent['inference_status'] | AcousticInferenceResult['status']) {
  const normalized = status.toLowerCase();
  const map: Record<string, string> = {
    complete: 'ok', running: 'warn', unavailable: 'unknown',
    experimental: 'exp', ready: 'ok', error: 'crit',
  };
  return map[normalized] ?? 'unknown';
}

function bandColor(band: AcousticEvent['confidence_band']) {
  const map: Record<string, string> = {
    low: '#f97316', medium: '#eab308', high: '#22c55e', uncertain: '#6b7280',
  };
  return map[band] ?? '#6b7280';
}

function generateSyntheticWavBlob(durationSec = 10.0, sampleRate = 16000): Blob {
  const numSamples = Math.floor(durationSec * sampleRate);
  const buffer = new ArrayBuffer(44 + numSamples * 2);
  const view = new DataView(buffer);

  function writeString(offset: number, str: string) {
    for (let i = 0; i < str.length; i++) {
      view.setUint8(offset + i, str.charCodeAt(i));
    }
  }

  writeString(0, 'RIFF');
  view.setUint32(4, 36 + numSamples * 2, true);
  writeString(8, 'WAVE');
  writeString(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // Mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(36, 'data');
  view.setUint32(40, numSamples * 2, true);

  let offset = 44;
  for (let i = 0; i < numSamples; i++) {
    const t = i / sampleRate;
    const freq = 200 + (600 * t) / durationSec;
    const sample = 0.25 * Math.sin(2 * Math.PI * freq * t) + 0.05 * (Math.random() * 2 - 1);
    const clamped = Math.max(-1, Math.min(1, sample));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
    offset += 2;
  }

  return new Blob([buffer], { type: 'audio/wav' });
}

export function AcousticMonitoring({ events, onValidate, onBatchReview }: Props) {
  const [activeTab, setActiveTab] = useState<'live_upload' | 'dataset_library'>('live_upload');

  const [valFilter, setValFilter] = useState<ValidationStatus | 'all'>('all');
  const [reviewFilter, setReviewFilter] = useState<'all' | 'unreviewed' | 'reviewed'>('all');
  const [tierFilter, setTierFilter] = useState<'all' | 'alert' | 'detection'>('all');
  const [inspectEventId, setInspectEventId] = useState<string>(events[events.length - 1]?.id ?? '');
  const [validationModal, setValidationModal] = useState<{ id: string; status: 'validated' | 'rejected'; notes: string } | null>(null);
  const [reviewing, setReviewing] = useState<boolean>(false);

  // Demonstration Mode: 3-way input selector ('reference' | 'synthetic' | 'hardware' | 'upload')
  const [demoMode, setDemoMode] = useState<'reference' | 'synthetic' | 'hardware' | 'upload'>('reference');

  // Public Reference Dataset Catalog State
  const [refCatalog, setRefCatalog] = useState<ReferenceAudioCatalogItem[]>([]);
  const [loadingCatalog, setLoadingCatalog] = useState<boolean>(false);
  const [importingRefId, setImportingRefId] = useState<string | null>(null);

  // Synthetic Bioacoustic Impulse Scenario State
  const [simImpulseRate, setSimImpulseRate] = useState<number>(12.0);
  const [simAmplitude, setSimAmplitude] = useState<number>(0.6);
  const [simNoiseLevel, setSimNoiseLevel] = useState<number>(0.04);
  const [simDuration, setSimDuration] = useState<number>(10.0);
  const [simSeed, setSimSeed] = useState<number>(42);
  const [generatingSim, setGeneratingSim] = useState<boolean>(false);

  // Recorded Audio Ingestion State
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState<boolean>(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadResult, setUploadResult] = useState<AcousticInferenceResult | null>(null);
  const [saveToQueue, setSaveToQueue] = useState<boolean>(false);
  const [retainSample, setRetainSample] = useState<boolean>(true);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Retained Dataset & Offline Evaluation State
  const [samples, setSamples] = useState<RetainedAudioSample[]>([]);
  const [loadingSamples, setLoadingSamples] = useState<boolean>(false);
  const [evalReport, setEvalReport] = useState<DatasetEvaluationReport | null>(null);
  const [evaluating, setEvaluating] = useState<boolean>(false);
  const [evalThreshold, setEvalThreshold] = useState<number>(0.05);
  const [sampleSearch, setSampleSearch] = useState<string>('');
  const [sampleLabelFilter, setSampleLabelFilter] = useState<'all' | GroundTruthLabel>('all');
  const [sampleSourceFilter, setSampleSourceFilter] = useState<'all' | 'public_reference' | 'user_upload' | 'synthetic' | 'real'>('all');
  const [editingSample, setEditingSample] = useState<RetainedAudioSample | null>(null);
  const [editForm, setEditForm] = useState<{
    label: GroundTruthLabel;
    method: VerificationMethod;
    reviewer: string;
    notes: string;
  }>({
    label: 'UNREVIEWED',
    method: 'unverified',
    reviewer: 'Inspector',
    notes: '',
  });
  const [savingAnnotation, setSavingAnnotation] = useState<boolean>(false);

  const activeEvent = events.find(e => e.id === inspectEventId) ?? events[events.length - 1];
  const micActive = activeEvent?.inference_status !== 'unavailable';

  const unreviewedCount = events.filter(e => (e.review_status ?? 'unreviewed') === 'unreviewed').length;

  const filteredEvents = events.filter(e => {
    if (valFilter !== 'all' && e.validation_status !== valFilter) return false;
    if (reviewFilter !== 'all' && (e.review_status ?? 'unreviewed') !== reviewFilter) return false;
    if (tierFilter !== 'all' && (e.event_tier ?? 'detection') !== tierFilter) return false;
    return true;
  });

  const loadSamples = async () => {
    setLoadingSamples(true);
    try {
      const data = await api.audioSamples({ limit: 100 });
      setSamples(data);
    } catch (err) {
      console.error('Failed to load retained audio samples', err);
    } finally {
      setLoadingSamples(false);
    }
  };

  const loadCatalog = async () => {
    setLoadingCatalog(true);
    try {
      const items = await api.referenceCatalog();
      setRefCatalog(items);
    } catch (err) {
      console.error('Failed to load reference audio catalog', err);
    } finally {
      setLoadingCatalog(false);
    }
  };

  useEffect(() => {
    loadSamples();
    loadCatalog();
  }, []);

  const handleBatchReview = async (ids: string[]) => {
    if (!onBatchReview || ids.length === 0) return;
    setReviewing(true);
    try {
      await onBatchReview(ids, 'reviewed', 'operator_console');
    } finally {
      setReviewing(false);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith('.wav')) {
      setUploadError('Only standard WAV audio files are supported (.wav).');
      setSelectedFile(null);
      return;
    }

    if (file.size > 20 * 1024 * 1024) {
      setUploadError(`File exceeds the 20 MB limit (${(file.size / (1024 * 1024)).toFixed(1)} MB).`);
      setSelectedFile(null);
      return;
    }

    setSelectedFile(file);
    setUploadError(null);
    setUploadResult(null);
  };

  const handleExecuteUpload = async (fileToUpload?: File | Blob, filename?: string, synthetic = false) => {
    const targetFile = fileToUpload ?? selectedFile;
    if (!targetFile) return;

    const name = filename ?? (targetFile instanceof File ? targetFile.name : 'audio_recording.wav');
    setUploading(true);
    setUploadError(null);

    try {
      const result = await api.uploadAcousticRecording(
        targetFile,
        name,
        'zone-a',
        'esp32-zone-a-01',
        saveToQueue,
        retainSample,
        synthetic
      );
      setUploadResult(result);
      if (retainSample) {
        await loadSamples();
      }
    } catch (err: any) {
      setUploadError(err.message || 'Failed to process audio recording');
      setUploadResult(null);
    } finally {
      setUploading(false);
    }
  };

  const handleSyntheticTest = () => {
    setSelectedFile(null);
    const blob = generateSyntheticWavBlob(10.0, 16000);
    handleExecuteUpload(blob, 'synthetic_chirp_10s.wav', true);
  };

  const handleImportReference = async (catalogId: string) => {
    setImportingRefId(catalogId);
    setUploadError(null);
    setUploadResult(null);
    setSelectedFile(null);
    try {
      const result = await api.importReference({
        catalog_id: catalogId,
        retain_sample: retainSample,
        zone_id: 'zone-a',
        device_id: 'esp32-zone-a-01',
      });
      setUploadResult(result);
      if (retainSample) {
        await loadSamples();
      }
    } catch (err: any) {
      setUploadError(err.message || 'Failed to import reference recording');
    } finally {
      setImportingRefId(null);
    }
  };

  const handleGenerateSyntheticImpulse = async () => {
    setGeneratingSim(true);
    setUploadError(null);
    setUploadResult(null);
    setSelectedFile(null);
    try {
      const result = await api.generateSyntheticImpulse({
        impulse_rate: simImpulseRate,
        amplitude: simAmplitude,
        noise_level: simNoiseLevel,
        duration_sec: simDuration,
        seed: simSeed,
        run_inference: true,
        retain_sample: retainSample,
        zone_id: 'zone-a',
        device_id: 'esp32-zone-a-01',
      });
      setUploadResult(result);
      if (retainSample) {
        await loadSamples();
      }
    } catch (err: any) {
      setUploadError(err.message || 'Failed to generate synthetic impulse scenario');
    } finally {
      setGeneratingSim(false);
    }
  };

  const handleResetUpload = () => {
    setSelectedFile(null);
    setUploadResult(null);
    setUploadError(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleRunEvaluation = async () => {
    setEvaluating(true);
    try {
      const report = await api.datasetEvaluation(evalThreshold);
      setEvalReport(report);
    } catch (err) {
      console.error('Failed to run dataset evaluation', err);
    } finally {
      setEvaluating(false);
    }
  };

  const handleSeedDemoSamples = async () => {
    try {
      await api.seedDemoAudioSamples();
      await loadSamples();
      await handleRunEvaluation();
    } catch (err) {
      console.error('Failed to seed demo samples', err);
    }
  };

  const handleOpenAnnotationModal = (sample: RetainedAudioSample) => {
    setEditingSample(sample);
    setEditForm({
      label: sample.ground_truth_label,
      method: sample.verification_method || 'unverified',
      reviewer: sample.reviewer || 'Inspector',
      notes: sample.evidence_notes || '',
    });
  };

  const handleSaveAnnotation = async () => {
    if (!editingSample) return;
    setSavingAnnotation(true);
    try {
      const updated = await api.updateSampleAnnotation(editingSample.id, {
        ground_truth_label: editForm.label,
        verification_method: editForm.method,
        reviewer: editForm.reviewer,
        evidence_notes: editForm.notes,
        review_status: editForm.label !== 'UNREVIEWED' ? 'REVIEWED' : 'UNREVIEWED',
      });
      setSamples(prev => prev.map(s => (s.id === updated.id ? updated : s)));
      setEditingSample(null);
      if (evalReport) {
        await handleRunEvaluation();
      }
    } catch (err) {
      console.error('Failed to save annotation', err);
    } finally {
      setSavingAnnotation(false);
    }
  };

  const handleDeleteSample = async (id: string) => {
    if (!window.confirm(`Are you sure you want to delete retained sample ${id}?`)) return;
    try {
      await api.deleteAudioSample(id);
      setSamples(prev => prev.filter(s => s.id !== id));
      if (evalReport) {
        await handleRunEvaluation();
      }
    } catch (err) {
      console.error('Failed to delete sample', err);
    }
  };

  const filteredSamples = samples.filter(s => {
    if (sampleLabelFilter !== 'all' && s.ground_truth_label !== sampleLabelFilter) return false;
    if (sampleSourceFilter === 'public_reference' && s.input_source !== 'public_reference') return false;
    if (sampleSourceFilter === 'user_upload' && s.input_source !== 'user_upload') return false;
    if (sampleSourceFilter === 'synthetic' && !s.is_synthetic && s.input_source !== 'synthetic') return false;
    if (sampleSourceFilter === 'real' && (s.is_synthetic || s.input_source === 'synthetic')) return false;
    if (sampleSearch.trim()) {
      const q = sampleSearch.toLowerCase();
      const match =
        s.id.toLowerCase().includes(q) ||
        s.filename.toLowerCase().includes(q) ||
        (s.source_species && s.source_species.toLowerCase().includes(q)) ||
        (s.dataset_name && s.dataset_name.toLowerCase().includes(q)) ||
        (s.evidence_notes && s.evidence_notes.toLowerCase().includes(q)) ||
        (s.reviewer && s.reviewer.toLowerCase().includes(q));
      if (!match) return false;
    }
    return true;
  });

  const waveform = activeEvent?.waveform_preview ?? [0.08, 0.12, 0.35, 0.65, 0.78, 0.45, 0.22, 0.15, 0.48, 0.82, 0.61, 0.28, 0.18, 0.32, 0.14, 0.09];

  return (
    <div className="ss-page">
      <div className="ss-page-header">
        <div>
          <h1 className="ss-page-title">Acoustic Insect Monitoring & Dataset Evaluation</h1>
          <div className="ss-page-subtitle">
            Bioacoustic inference, physical ground-truth annotation, audio storage, and offline evaluation
          </div>
        </div>
        <div className="ss-page-meta">
          <span className={`ss-status-pill ${micActive ? 'live' : 'demo'}`}>
            {micActive ? <Mic size={13} /> : <MicOff size={13} />}
            {micActive ? 'I2S Mic Active' : 'Mic Offline / Inference Blocked'}
          </span>
          <span className="ss-text-muted ss-text-xs">{events.length} events · {samples.length} retained samples</span>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="ss-nav-tabs">
        <button
          className={`ss-nav-tab ${activeTab === 'live_upload' ? 'active' : ''}`}
          onClick={() => setActiveTab('live_upload')}
        >
          <Upload size={14} /> Live & Audio Upload Triage
        </button>
        <button
          className={`ss-nav-tab ${activeTab === 'dataset_library' ? 'active' : ''}`}
          onClick={() => {
            setActiveTab('dataset_library');
            loadSamples();
          }}
        >
          <Database size={14} /> Retained Dataset & Evaluation
          {samples.length > 0 && <span className="ss-badge-count">{samples.length}</span>}
        </button>
      </div>

      {activeTab === 'live_upload' && (
        <>
          {/* Prominent Experimental Disclaimer Banner */}
          <div className="ss-exp-banner ss-exp-banner-warn">
            <FlaskConical size={20} />
            <div>
              <strong>STRICT EXPERIMENTAL CLASSIFICATION NOTICE:</strong>
              The bioacoustic inference model (<em>nocturne-v1-mini</em>) has <strong>not</strong> been trained or validated
              on grain-storage insects (such as <em>Sitophilus oryzae</em> or <em>Rhyzopertha dominica</em>).
              Model anomaly scores represent raw spectral deviations, <strong>not</strong> calibrated infestation probabilities.
              Human audio review and grain trap physical inspection are mandatory prior to any treatment or quarantine.
            </div>
          </div>

          {/* Recorded Audio Ingestion & Inference Section */}
          <section className="ss-section">
            <div className="ss-section-header-row">
              <div>
                <h2 className="ss-section-title">
                  Acoustic Input & Demonstration Workflow
                </h2>
                <div className="ss-section-sub">
                  Defective INMP441 sensor fallback: Evaluate genuine USDA Bug Bytes stored-grain insect audio, run stochastic synthetic bioacoustic simulations, or inspect hardware status.
                </div>
              </div>
              <div className="ss-flex-gap">
                <span className="ss-badge ss-mono ss-text-xs">
                  Model: stratus-labs/nocturne-v1-mini
                </span>
              </div>
            </div>

            {/* Three-Way Input Selector */}
            <div className="ss-demo-mode-selector">
              {/* Option 1: Public Reference Recording (USDA Bug Bytes) */}
              <div
                id="mode-selector-reference"
                className={`ss-demo-mode-card ${demoMode === 'reference' ? 'active' : ''}`}
                onClick={() => setDemoMode('reference')}
              >
                <div className="ss-demo-mode-header">
                  <div className="ss-demo-mode-icon-title">
                    <BookOpen size={18} style={{ color: '#34d399' }} />
                    <span>Public Reference Audio</span>
                  </div>
                  <span className="ss-source-pill public_reference">USDA Bug Bytes</span>
                </div>
                <div className="ss-demo-mode-desc">
                  Genuine peer-reviewed bioacoustic recordings of stored-product insects (<em>Sitophilus oryzae</em>, <em>Plodia interpunctella</em>) from the USDA-ARS CMAVE sound library.
                </div>
                <div className="ss-demo-mode-badge-row">
                  <span className="ss-badge ss-mono ss-text-xs">U.S. Public Domain</span>
                  <span className="ss-badge ss-mono ss-text-xs">Lab Culture</span>
                </div>
              </div>

              {/* Option 2: Synthetic Simulation */}
              <div
                id="mode-selector-synthetic"
                className={`ss-demo-mode-card ${demoMode === 'synthetic' ? 'active' : ''}`}
                onClick={() => setDemoMode('synthetic')}
              >
                <div className="ss-demo-mode-header">
                  <div className="ss-demo-mode-icon-title">
                    <Sparkles size={18} style={{ color: '#c084fc' }} />
                    <span>Synthetic Simulation</span>
                  </div>
                  <span className="ss-source-pill synthetic">Simulation Engine</span>
                </div>
                <div className="ss-demo-mode-desc">
                  Stochastic Poisson click/impulse generator simulating kernel feeding activity and frequency sweeps with adjustable rates, amplitudes, and noise.
                </div>
                <div className="ss-demo-mode-badge-row">
                  <span className="ss-badge ss-mono ss-text-xs">Repeatable Seed</span>
                  <span className="ss-badge ss-mono ss-text-xs" style={{ color: 'var(--red)' }}>Excluded from Eval</span>
                </div>
              </div>

              {/* Option 3: Live Hardware Recording (Unavailable) */}
              <div
                id="mode-selector-hardware"
                className={`ss-demo-mode-card ${demoMode === 'hardware' ? 'active' : ''}`}
                onClick={() => setDemoMode('hardware')}
              >
                <div className="ss-demo-mode-header">
                  <div className="ss-demo-mode-icon-title">
                    <MicOff size={18} style={{ color: 'var(--red)' }} />
                    <span>Live Hardware Stream</span>
                  </div>
                  <span className="ss-source-pill hardware_recording" style={{ borderColor: 'rgba(239, 68, 68, 0.4)', color: 'var(--red)' }}>
                    CURRENTLY UNAVAILABLE
                  </span>
                </div>
                <div className="ss-demo-mode-desc">
                  Physical I2S INMP441 microphone node (<code>esp32-zone-a-01</code>) is offline due to a defective sensor element. Biological live measurements are not fabricated.
                </div>
                <div className="ss-demo-mode-badge-row">
                  <span className="ss-badge ss-mono ss-text-xs" style={{ color: 'var(--red)' }}>INMP441 Defective</span>
                  <span className="ss-badge ss-mono ss-text-xs">DMA Offline</span>
                </div>
              </div>
            </div>

            {/* Mode-Specific Panels */}
            {demoMode === 'reference' && (
              <div className="ss-upload-card" style={{ padding: '20px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px', marginBottom: '14px' }}>
                  <div>
                    <h3 style={{ fontSize: '15px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <BookOpen size={16} style={{ color: '#34d399' }} />
                      USDA Bug Bytes — Stored-Product Insect Pest Sound Library
                    </h3>
                    <div className="ss-text-xs ss-text-muted" style={{ marginTop: '2px' }}>
                      Authored by Dr. Richard W. Mankin (USDA-ARS CMAVE, Gainesville, FL). Authenticated laboratory recordings retained with full taxonomic provenance.
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <label className="ss-checkbox-label" style={{ fontSize: '12px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <input
                        type="checkbox"
                        checked={retainSample}
                        onChange={e => setRetainSample(e.target.checked)}
                      />
                      Retain in dataset library
                    </label>
                    <button
                      className="ss-btn ss-btn-ghost ss-btn-xs"
                      onClick={() => setDemoMode('upload')}
                      title="Upload custom WAV file"
                    >
                      <Upload size={12} /> Custom WAV Upload
                    </button>
                  </div>
                </div>

                {loadingCatalog ? (
                  <div className="ss-empty">
                    <Loader2 size={16} className="ss-spin" /> Loading reference recordings catalog…
                  </div>
                ) : refCatalog.length === 0 ? (
                  <div className="ss-empty">
                    No reference recordings catalog found.
                  </div>
                ) : (
                  <div className="ss-ref-catalog-grid">
                    {refCatalog.map(item => (
                      <div key={item.id} className="ss-ref-card" id={`ref-card-${item.id}`}>
                        <div className="ss-ref-card-header">
                          <div>
                            <div className="ss-ref-species">{item.species}</div>
                            <div className="ss-ref-common">
                              {item.common_name} · <span className="ss-mono ss-text-xs">{item.life_stage}</span>
                            </div>
                          </div>
                          <span className="ss-source-pill public_reference">
                            {item.is_locally_available ? 'LOCAL DISK' : 'REMOTE'}
                          </span>
                        </div>

                        <div className="ss-ref-details-grid">
                          <div className="ss-ref-detail-item">
                            <span className="ss-ref-detail-label">Substrate</span>
                            <span className="ss-ref-detail-val">{item.substrate}</span>
                          </div>
                          <div className="ss-ref-detail-item">
                            <span className="ss-ref-detail-label">Transducer</span>
                            <span className="ss-ref-detail-val">{item.transducer_type}</span>
                          </div>
                          <div className="ss-ref-detail-item">
                            <span className="ss-ref-detail-label">Duration / Rate</span>
                            <span className="ss-ref-detail-val">{item.duration_sec}s · {item.sample_rate.toLocaleString()} Hz</span>
                          </div>
                          <div className="ss-ref-detail-item">
                            <span className="ss-ref-detail-label">File</span>
                            <span className="ss-ref-detail-val ss-mono ss-text-xs">{item.filename}</span>
                          </div>
                        </div>

                        <div className="ss-audio-player-mini" style={{ width: '100%', marginTop: '2px' }}>
                          <audio
                            controls
                            preload="none"
                            src={api.referenceAudioUrl(item.id)}
                            style={{ width: '100%', height: '32px' }}
                          />
                        </div>

                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '4px' }}>
                          <a
                            href={item.source_url}
                            target="_blank"
                            rel="noreferrer"
                            className="ss-text-xs"
                            style={{ color: 'var(--text-muted)', display: 'inline-flex', alignItems: 'center', gap: '4px', textDecoration: 'none' }}
                          >
                            <ExternalLink size={11} /> Source Catalog
                          </a>
                          <button
                            id={`btn-import-ref-${item.id}`}
                            className="ss-btn ss-btn-primary ss-btn-xs"
                            disabled={importingRefId !== null}
                            onClick={() => handleImportReference(item.id)}
                          >
                            {importingRefId === item.id ? (
                              <>
                                <Loader2 size={12} className="ss-spin" /> Running…
                              </>
                            ) : (
                              <>
                                <Play size={12} /> Run Nocturne Inference
                              </>
                            )}
                          </button>
                        </div>

                        <div className="ss-ref-citation-box">
                          {item.citation}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {demoMode === 'synthetic' && (
              <div className="ss-upload-card" style={{ padding: '20px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px', marginBottom: '14px' }}>
                  <div>
                    <h3 style={{ fontSize: '15px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Sparkles size={16} style={{ color: '#c084fc' }} />
                      Synthetic Bioacoustic Impulse & Feeding Simulation
                    </h3>
                    <div className="ss-text-xs ss-text-muted" style={{ marginTop: '2px' }}>
                      Generates stochastic Poisson click impulse bursts (1.8–3.6 kHz decay) simulating internal grain feeding activity.
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <label className="ss-checkbox-label" style={{ fontSize: '12px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <input
                        type="checkbox"
                        checked={retainSample}
                        onChange={e => setRetainSample(e.target.checked)}
                      />
                      Retain in dataset library
                    </label>
                    <button
                      className="ss-btn ss-btn-ghost ss-btn-xs"
                      onClick={() => setDemoMode('upload')}
                      title="Upload custom WAV file"
                    >
                      <Upload size={12} /> Custom WAV Upload
                    </button>
                  </div>
                </div>

                <div className="ss-sim-grid">
                  <div className="ss-sim-param-box">
                    <div className="ss-sim-param-header">
                      <span>Impulse Rate (Clicks / Second)</span>
                      <span className="ss-sim-param-val">{simImpulseRate.toFixed(1)} Hz</span>
                    </div>
                    <input
                      id="sim-impulse-rate"
                      type="range"
                      min="1.0"
                      max="50.0"
                      step="1.0"
                      className="ss-sim-slider"
                      value={simImpulseRate}
                      onChange={e => setSimImpulseRate(parseFloat(e.target.value))}
                    />
                    <div className="ss-sim-param-hint">Models insect feeding/movement frequency in wheat kernels (1–50 Hz).</div>
                  </div>

                  <div className="ss-sim-param-box">
                    <div className="ss-sim-param-header">
                      <span>Click Amplitude (Peak Relative)</span>
                      <span className="ss-sim-param-val">{simAmplitude.toFixed(2)}</span>
                    </div>
                    <input
                      id="sim-amplitude"
                      type="range"
                      min="0.10"
                      max="1.00"
                      step="0.05"
                      className="ss-sim-slider"
                      value={simAmplitude}
                      onChange={e => setSimAmplitude(parseFloat(e.target.value))}
                    />
                    <div className="ss-sim-param-hint">Signal-to-noise ratio of insect mastication clicks.</div>
                  </div>

                  <div className="ss-sim-param-box">
                    <div className="ss-sim-param-header">
                      <span>Background Noise Level</span>
                      <span className="ss-sim-param-val">{simNoiseLevel.toFixed(3)}</span>
                    </div>
                    <input
                      id="sim-noise-level"
                      type="range"
                      min="0.00"
                      max="0.20"
                      step="0.01"
                      className="ss-sim-slider"
                      value={simNoiseLevel}
                      onChange={e => setSimNoiseLevel(parseFloat(e.target.value))}
                    />
                    <div className="ss-sim-param-hint">White Gaussian background noise simulating ambient silo draft.</div>
                  </div>

                  <div className="ss-sim-param-box">
                    <div className="ss-sim-param-header">
                      <span>Window Duration</span>
                      <span className="ss-sim-param-val">{simDuration.toFixed(1)}s</span>
                    </div>
                    <input
                      id="sim-duration"
                      type="range"
                      min="5.0"
                      max="15.0"
                      step="1.0"
                      className="ss-sim-slider"
                      value={simDuration}
                      onChange={e => setSimDuration(parseFloat(e.target.value))}
                    />
                    <div className="ss-sim-param-hint">Synthetic recording duration (standardized to 10.0s window for Nocturne).</div>
                  </div>

                  <div className="ss-sim-param-box">
                    <div className="ss-sim-param-header">
                      <span>Random Seed (Reproducibility)</span>
                      <span className="ss-sim-param-val">Seed: {simSeed}</span>
                    </div>
                    <input
                      id="sim-seed"
                      type="number"
                      className="ss-input"
                      style={{ height: '32px', fontSize: '13px' }}
                      value={simSeed}
                      onChange={e => setSimSeed(parseInt(e.target.value) || 0)}
                    />
                    <div className="ss-sim-param-hint">Exact pseudo-random seed for deterministic evaluation test cases.</div>
                  </div>
                </div>

                <div className="ss-exp-banner ss-exp-banner-warn" style={{ marginBottom: '14px', fontSize: '12px' }}>
                  <ShieldAlert size={16} />
                  <div>
                    <strong>SCIENTIFIC INTEGRITY ENFORCEMENT:</strong> All synthetic recordings are permanently tagged with <code>is_synthetic = 1</code> and <code>input_source = "synthetic"</code>. Synthetic audio is strictly excluded from scientific dataset evaluation and field metrics.
                  </div>
                </div>

                <div className="ss-upload-toolbar" style={{ marginTop: '0' }}>
                  <div className="ss-upload-actions-left" style={{ flexWrap: 'wrap', gap: '10px' }}>
                    <button
                      id="btn-run-sim-impulse"
                      className="ss-btn ss-btn-primary ss-btn-sm"
                      disabled={generatingSim}
                      onClick={handleGenerateSyntheticImpulse}
                    >
                      {generatingSim ? (
                        <>
                          <Loader2 size={13} className="ss-spin" /> Synthesizing & Running…
                        </>
                      ) : (
                        <>
                          <Sparkles size={13} /> Generate & Run Nocturne Inference
                        </>
                      )}
                    </button>

                    <button
                      id="btn-run-synthetic-chirp"
                      className="ss-btn ss-btn-outline ss-btn-sm"
                      disabled={generatingSim}
                      onClick={handleSyntheticTest}
                    >
                      <Sparkles size={13} /> Quick Test: 10s Sweep Chirp
                    </button>

                    <a
                      href={api.syntheticWavUrl({
                        impulse_rate: simImpulseRate,
                        amplitude: simAmplitude,
                        noise_level: simNoiseLevel,
                        duration_sec: simDuration,
                        seed: simSeed,
                      })}
                      className="ss-btn ss-btn-outline ss-btn-sm"
                      download={`synthetic_impulse_${simImpulseRate}hz_seed${simSeed}.wav`}
                    >
                      <Download size={13} /> Export WAV
                    </a>
                  </div>
                </div>
              </div>
            )}

            {demoMode === 'hardware' && (
              <div className="ss-upload-card" style={{ padding: '24px' }}>
                <div className="ss-alert ss-alert-critical" style={{ marginBottom: '18px' }}>
                  <AlertTriangle size={20} />
                  <div>
                    <strong style={{ fontSize: '14px' }}>PHYSICAL MICROPHONE DEFECT — HARDWARE STREAM HALTED</strong>
                    <div style={{ marginTop: '4px', fontSize: '12.5px', lineHeight: 1.45 }}>
                      The INMP441 I2S MEMS microphone element on physical sensor node <code>esp32-zone-a-01</code> is defective.
                      Physical I2S clocking and DMA buffers are functional, but the transducer capsule is unresponsive or delivering zero-energy noise.
                      In accordance with project integrity standards, live hardware recording has been blocked to prevent fabricating biological measurements or misleading silo operators.
                    </div>
                  </div>
                </div>

                <h3 style={{ fontSize: '14px', fontWeight: 700, marginBottom: '8px' }}>
                  Hardware I2S Bus Configuration (Offline Diagnostics)
                </h3>
                <div className="ss-hw-table" style={{ marginBottom: '16px' }}>
                  <div className="ss-hw-row"><span>Sensor Model</span><span>INMP441 Omnidirectional MEMS (DEFECTIVE / REPLACEMENT REQUIRED)</span></div>
                  <div className="ss-hw-row"><span>ESP32 Node Target</span><span>esp32-zone-a-01 (Zone A Silo Apex)</span></div>
                  <div className="ss-hw-row"><span>BCLK / SCK</span><span>GPIO 26</span></div>
                  <div className="ss-hw-row"><span>WS / LRCLK</span><span>GPIO 25</span></div>
                  <div className="ss-hw-row"><span>SD / DOUT</span><span>GPIO 33</span></div>
                  <div className="ss-hw-row"><span>L/R Channel Pin</span><span>GND (Mono Left Channel)</span></div>
                  <div className="ss-hw-row"><span>Sampling Rate</span><span>16,000 Hz (16-bit PCM Mono Window)</span></div>
                  <div className="ss-hw-row"><span>Live Grain Insects</span><span>None present in physical test lab (Culture rearing not permitted)</span></div>
                </div>

                <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                  <button
                    className="ss-btn ss-btn-primary ss-btn-sm"
                    onClick={() => setDemoMode('reference')}
                  >
                    <BookOpen size={13} /> Switch to Public Reference Audio (USDA Bug Bytes)
                  </button>
                  <button
                    className="ss-btn ss-btn-outline ss-btn-sm"
                    onClick={() => setDemoMode('synthetic')}
                  >
                    <Sparkles size={13} /> Switch to Synthetic Bioacoustic Simulation
                  </button>
                </div>
              </div>
            )}

            {demoMode === 'upload' && (
              <div className="ss-upload-card">
                <input
                  type="file"
                  ref={fileInputRef}
                  accept=".wav,audio/wav"
                  style={{ display: 'none' }}
                  onChange={handleFileSelect}
                />

                {!selectedFile && !uploadResult && (
                  <div
                    id="acoustic-dropzone"
                    className="ss-upload-dropzone"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <div className="ss-dropzone-icon">
                      <Upload size={22} />
                    </div>
                    <div className="ss-dropzone-text">
                      Click to browse or drop a WAV recording here
                    </div>
                    <div className="ss-dropzone-hint">
                      Standard WAV format (mono/stereo, 8–192 kHz, up to 20 MB). Auto-resampled to 16 kHz & standardized to 10.0s window.
                    </div>
                  </div>
                )}

                {selectedFile && !uploadResult && (
                  <div className="ss-file-selected-box">
                    <FileAudio size={24} style={{ color: 'var(--accent-light)' }} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 600, fontSize: '13px' }}>{selectedFile.name}</div>
                      <div className="ss-text-xs ss-text-muted">
                        {(selectedFile.size / 1024).toFixed(1)} KB · Ready for validation & inference
                      </div>
                    </div>
                    <button
                      className="ss-btn ss-btn-ghost ss-btn-xs"
                      onClick={handleResetUpload}
                      disabled={uploading}
                    >
                      <X size={14} /> Remove
                    </button>
                  </div>
                )}

                <div className="ss-upload-toolbar">
                  <div className="ss-upload-actions-left" style={{ flexWrap: 'wrap', gap: '10px' }}>
                    {selectedFile && (
                      <button
                        id="btn-run-uploaded-inference"
                        className="ss-btn ss-btn-primary ss-btn-sm"
                        disabled={uploading}
                        onClick={() => handleExecuteUpload()}
                      >
                        {uploading ? (
                          <>
                            <Loader2 size={13} className="ss-spin" /> Running Inference…
                          </>
                        ) : (
                          <>
                            <Upload size={13} /> Run Nocturne Inference
                          </>
                        )}
                      </button>
                    )}

                    <label className="ss-checkbox-label" style={{ fontSize: '12px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <input
                        type="checkbox"
                        checked={retainSample}
                        onChange={e => setRetainSample(e.target.checked)}
                      />
                      Retain WAV in dataset library
                    </label>

                    <label className="ss-checkbox-label" style={{ fontSize: '12px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <input
                        type="checkbox"
                        checked={saveToQueue}
                        onChange={e => setSaveToQueue(e.target.checked)}
                      />
                      Save to Frigate review queue
                    </label>
                  </div>

                  <div className="ss-upload-actions-right">
                    <button
                      className="ss-btn ss-btn-ghost ss-btn-xs"
                      onClick={() => setDemoMode('reference')}
                    >
                      ← Back to Reference Audio
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Upload & Validation Error Banner */}
            {uploadError && (
              <div className="ss-alert ss-alert-critical" style={{ marginTop: '14px' }}>
                <AlertTriangle size={16} />
                <div>
                  <strong>Audio Processing Rejected:</strong> {uploadError}
                </div>
              </div>
            )}

            {/* Genuine Inference Result Visualization Card */}
            {uploadResult && (
              <div className="ss-upload-result-container" id="acoustic-inference-result-box" style={{ marginTop: '20px' }}>
                <div className="ss-result-header-row">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                    <FileAudio size={16} style={{ color: 'var(--accent-light)' }} />
                    <span style={{ fontWeight: 600, fontSize: '14px' }}>
                      {uploadResult.filename ?? 'audio_sample.wav'}
                    </span>
                    {uploadResult.input_source === 'public_reference' && (
                      <span className="ss-source-pill public_reference">
                        📚 PUBLIC REFERENCE (USDA Bug Bytes)
                      </span>
                    )}
                    {uploadResult.input_source === 'synthetic' && (
                      <span className="ss-source-pill synthetic">
                        ⚡ SYNTHETIC SIMULATION (Excluded from Eval)
                      </span>
                    )}
                    {uploadResult.input_source === 'user_upload' && (
                      <span className="ss-source-pill user_upload">
                        📁 USER UPLOAD
                      </span>
                    )}
                    {uploadResult.input_source === 'hardware_recording' && (
                      <span className="ss-source-pill hardware_recording">
                        🎙️ HARDWARE RECORDING
                      </span>
                    )}
                    <span className={`ss-infer-status inf-${statusColor(uploadResult.status)}`}>
                      <span className="ss-infer-dot" />
                      {uploadResult.status}
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    {uploadResult.inference_duration_ms !== undefined && (
                      <span className="ss-badge ss-mono ss-text-xs">
                        Latency: {uploadResult.inference_duration_ms} ms (CPU)
                      </span>
                    )}
                    <span className="ss-badge ss-mono ss-text-xs">
                      {uploadResult.model_id}
                    </span>
                    <button
                      className="ss-btn ss-btn-ghost ss-btn-xs"
                      onClick={handleResetUpload}
                      title="Clear inference result"
                    >
                      <RefreshCw size={12} /> Clear
                    </button>
                  </div>
                </div>

                {uploadResult.audio_sample_id && (
                  <div className="ss-alert ss-alert-info" style={{ marginTop: '10px', padding: '8px 12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <CheckCircle2 size={15} style={{ color: 'var(--green)' }} />
                      <span>Retained in dataset library: <strong>{uploadResult.audio_sample_id}</strong></span>
                    </div>
                    <button
                      className="ss-btn ss-btn-outline ss-btn-xs"
                      onClick={() => setActiveTab('dataset_library')}
                    >
                      View in Dataset Library →
                    </button>
                  </div>
                )}

                {/* Biological Reference Metadata Card */}
                {uploadResult.source_species && (
                  <div className="ss-ref-card" style={{ marginTop: '12px', background: 'rgba(16, 185, 129, 0.05)', borderColor: 'rgba(16, 185, 129, 0.3)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: '13px', fontWeight: 700, color: '#34d399' }}>
                        Genuine Biological Reference: <em>{uploadResult.source_species}</em>
                      </span>
                      <span className="ss-badge ss-mono ss-text-xs">{uploadResult.dataset_name}</span>
                    </div>
                    <div className="ss-ref-details-grid" style={{ marginTop: '6px' }}>
                      <div className="ss-ref-detail-item">
                        <span className="ss-ref-detail-label">Transducer Type</span>
                        <span className="ss-ref-detail-val">{uploadResult.transducer_type || 'Laboratory Contact Sensor'}</span>
                      </div>
                      <div className="ss-ref-detail-item">
                        <span className="ss-ref-detail-label">Taxonomic Provenance</span>
                        <span className="ss-ref-detail-val">USDA-ARS CMAVE Verified Culture</span>
                      </div>
                    </div>
                    {uploadResult.source_citation && (
                      <div className="ss-ref-citation-box">
                        <strong>Citation:</strong> {uploadResult.source_citation}
                        {uploadResult.source_url && (
                          <div style={{ marginTop: '4px' }}>
                            <a
                              href={uploadResult.source_url}
                              target="_blank"
                              rel="noreferrer"
                              style={{ color: 'var(--accent-light)', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                            >
                              <ExternalLink size={11} /> Source Archive Link
                            </a>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* Simulation Parameters Card */}
                {uploadResult.simulation_params && (
                  <div style={{ marginTop: '12px', padding: '10px 14px', background: 'rgba(168, 85, 247, 0.06)', borderRadius: 'var(--radius-sm)', border: '1px solid rgba(168, 85, 247, 0.25)', fontSize: '12px' }}>
                    <strong style={{ color: '#c084fc' }}>Deterministic Simulation Configuration:</strong>
                    <div style={{ marginTop: '4px', display: 'flex', gap: '16px', flexWrap: 'wrap' }} className="ss-mono ss-text-xs">
                      <span>Rate: {uploadResult.simulation_params.impulse_rate} Hz</span>
                      <span>Amplitude: {uploadResult.simulation_params.amplitude}</span>
                      <span>Noise: {uploadResult.simulation_params.noise_level}</span>
                      <span>Seed: {uploadResult.simulation_params.seed}</span>
                    </div>
                  </div>
                )}

                {/* Ingestion & Standardization Details Grid */}
                <div className="ss-infer-grid" style={{ marginBottom: '14px', marginTop: '12px' }}>
                  <div className="ss-infer-field">
                    <span className="ss-infer-key">Original Duration</span>
                    <span className="ss-infer-val">
                      {uploadResult.original_duration_sec !== undefined ? `${uploadResult.original_duration_sec}s` : '10.0s'}
                      {' '}
                      <span className="ss-text-muted ss-text-xs">
                        ({uploadResult.window_mode === 'padded' ? 'Padded with silence to 10.0s' : uploadResult.window_mode === 'truncated' ? 'Truncated to 10.0s' : 'Exact 10.0s window'})
                      </span>
                    </span>
                  </div>
                  <div className="ss-infer-field">
                    <span className="ss-infer-key">Original Sample Rate</span>
                    <span className="ss-infer-val">
                      {uploadResult.original_sample_rate ? `${uploadResult.original_sample_rate.toLocaleString()} Hz` : '16,000 Hz'}
                      {' '}
                      <span className="ss-text-muted ss-text-xs">→ Resampled to 16 kHz</span>
                    </span>
                  </div>
                  <div className="ss-infer-field">
                    <span className="ss-infer-key">Original Channels</span>
                    <span className="ss-infer-val">
                      {uploadResult.original_channels === 2 ? 'Stereo (2 Ch)' : uploadResult.original_channels === 1 ? 'Mono (1 Ch)' : `${uploadResult.original_channels ?? 1} Ch`}
                      {' '}
                      <span className="ss-text-muted ss-text-xs">→ Downmixed to mono</span>
                    </span>
                  </div>
                  <div className="ss-infer-field">
                    <span className="ss-infer-key">Primary Classification</span>
                    <span className="ss-infer-val ss-prediction">
                      {uploadResult.prediction}
                    </span>
                  </div>
                </div>

                {/* Waveform Preview of Ingested Audio */}
                {uploadResult.waveform_preview && uploadResult.waveform_preview.length > 0 && (
                  <div className="ss-waveform-container">
                    <div className="ss-waveform-header">
                      <span className="ss-waveform-title">
                        <Volume2 size={14} /> Ingested 10.0s Waveform Envelope (16 RMS Energy Bars)
                      </span>
                      <span className="ss-waveform-time">160,000 samples @ 16 kHz</span>
                    </div>
                    <div className="ss-waveform-bars">
                      {uploadResult.waveform_preview.map((val, idx) => {
                        const heightPct = Math.max(10, Math.min(100, Math.round(val * 100)));
                        const isPeak = val > 0.6;
                        return (
                          <div key={idx} className="ss-wave-col" title={`Window t=${(idx * 0.6).toFixed(1)}s: amp=${val.toFixed(2)}`}>
                            <div
                              className={`ss-wave-bar ${isPeak ? 'peak' : ''}`}
                              style={{ height: `${heightPct}%` }}
                            />
                          </div>
                        );
                      })}
                    </div>
                    <div className="ss-waveform-axis">
                      <span>0.0s</span>
                      <span>2.5s</span>
                      <span>5.0s</span>
                      <span>7.5s</span>
                      <span>10.0s</span>
                    </div>
                  </div>
                )}

                {/* Spectral Frequency Peaks */}
                {uploadResult.spectrogram_peaks && uploadResult.spectrogram_peaks.length > 0 && (
                  <div className="ss-spectrum-peaks-wrap" style={{ marginTop: '10px', marginBottom: '14px' }}>
                    <span className="ss-spectrum-title">Extracted Frequency Peaks:</span>
                    <div className="ss-peaks-list">
                      {uploadResult.spectrogram_peaks.map((p, i) => (
                        <div key={i} className="ss-peak-pill">
                          <Activity size={12} />
                          <span className="ss-peak-hz">{p.frequency_hz ?? p.freq_hz} Hz</span>
                          <span className="ss-peak-db">{p.magnitude_db ?? p.db} dB</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Top 5 Model Predictions */}
                <div style={{ marginTop: '16px' }}>
                  <span className="ss-waveform-title" style={{ display: 'block', marginBottom: '6px' }}>
                    Top 5 Bioacoustic Model Predictions (Raw Activation Scores)
                  </span>
                  <div className="ss-top-preds-list">
                    {uploadResult.top_predictions.map((item, idx) => (
                      <div key={idx} className="ss-pred-card">
                        <div style={{ display: 'flex', alignItems: 'center' }}>
                          <span className="ss-pred-rank">#{idx + 1}</span>
                          <span className="ss-pred-label" title={item.label}>{item.label}</span>
                        </div>
                        <span className="ss-pred-score">
                          {item.score.toFixed(5)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Semantics & Safety Disclaimers */}
                <div className="ss-infer-semantics-note" style={{ marginTop: '14px' }}>
                  <Info size={14} />
                  <span>
                    <strong>Raw Score Notice:</strong> {uploadResult.score_semantics}
                  </span>
                </div>

                <div className="ss-exp-banner ss-exp-banner-warn" style={{ marginTop: '10px' }}>
                  <ShieldAlert size={16} />
                  <div style={{ fontSize: '11.5px' }}>
                    <strong>DOMAIN LIMITATION & VOCABULARY SAFEGUARD:</strong> {uploadResult.limitations}
                    <div style={{ marginTop: '4px', opacity: 0.9 }}>
                      Do not claim that Nocturne Mini's outdoor wildlife species vocabulary validates stored-grain insect classification. Model activation scores are uncalibrated raw features.
                    </div>
                  </div>
                </div>
              </div>
            )}
          </section>

          {/* Edge Impulse-Inspired Acoustic Sample Inspector */}
          {activeEvent && (
            <section className="ss-section">
              <div className="ss-section-header-row">
                <h2 className="ss-section-title">
                  Sample Evidence Inspector <span className="ss-section-sub">{activeEvent.audio_sample_ref ?? activeEvent.id}</span>
                </h2>
                <div className="ss-flex-gap">
                  <span className={`ss-infer-status inf-${statusColor(activeEvent.inference_status)}`}>
                    <span className="ss-infer-dot" />
                    {activeEvent.inference_status.toUpperCase()}
                  </span>
                  <SourceBadge source={activeEvent.source} />
                </div>
              </div>

              <div className="ss-audio-inspector-card">
                {/* Audio Waveform Envelope Visualizer */}
                <div className="ss-waveform-container">
                  <div className="ss-waveform-header">
                    <span className="ss-waveform-title">
                      <Volume2 size={14} /> 10-Second INMP441 Audio Envelope (16 kHz / 16-bit Mono)
                    </span>
                    <span className="ss-waveform-time">0.0s — 10.0s window</span>
                  </div>
                  <div className="ss-waveform-bars">
                    {waveform.map((val, idx) => {
                      const heightPct = Math.max(10, Math.min(100, Math.round(val * 100)));
                      const isPeak = val > 0.6;
                      return (
                        <div key={idx} className="ss-wave-col" title={`Window t=${(idx * 0.6).toFixed(1)}s: amp=${val.toFixed(2)}`}>
                          <div
                            className={`ss-wave-bar ${isPeak ? 'peak' : ''}`}
                            style={{ height: `${heightPct}%` }}
                          />
                        </div>
                      );
                    })}
                  </div>
                  <div className="ss-waveform-axis">
                    <span>0.0s</span>
                    <span>2.5s</span>
                    <span>5.0s</span>
                    <span>7.5s</span>
                    <span>10.0s</span>
                  </div>
                </div>

                {/* Spectrogram Frequency Peaks */}
                {activeEvent.spectrogram_peaks && activeEvent.spectrogram_peaks.length > 0 && (
                  <div className="ss-spectrum-peaks-wrap">
                    <span className="ss-spectrum-title">Spectral Energy Peaks:</span>
                    <div className="ss-peaks-list">
                      {activeEvent.spectrogram_peaks.map((p, i) => (
                        <div key={i} className="ss-peak-pill">
                          <Activity size={12} />
                          <span className="ss-peak-hz">{p.freq_hz} Hz</span>
                          <span className="ss-peak-db">{p.db} dB</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Model Inference Metadata Grid */}
                <div className="ss-infer-grid">
                  <div className="ss-infer-field">
                    <span className="ss-infer-key">Model Checkpoint</span>
                    <span className="ss-infer-val ss-mono">{activeEvent.model_version}</span>
                  </div>
                  <div className="ss-infer-field">
                    <span className="ss-infer-key">Prediction Class</span>
                    <span className="ss-infer-val ss-prediction">{activeEvent.prediction}</span>
                  </div>
                  <div className="ss-infer-field">
                    <span className="ss-infer-key">Anomaly / Score</span>
                    <span className="ss-infer-val">
                      {activeEvent.score !== null ? activeEvent.score.toFixed(3) : 'N/A'}
                      {' '}<span className="ss-text-muted ss-text-xs">(Raw model output)</span>
                    </span>
                  </div>
                  <div className="ss-infer-field">
                    <span className="ss-infer-key">Confidence Band</span>
                    <span className="ss-infer-val" style={{ color: bandColor(activeEvent.confidence_band) }}>
                      {activeEvent.confidence_band.toUpperCase()}
                    </span>
                  </div>
                  <div className="ss-infer-field">
                    <span className="ss-infer-key">Validation Status</span>
                    <span className={`ss-infer-val val-${activeEvent.validation_status}`}>
                      {activeEvent.validation_status.toUpperCase()}
                    </span>
                  </div>
                  {activeEvent.inference_duration_ms && (
                    <div className="ss-infer-field">
                      <span className="ss-infer-key">Inference Latency</span>
                      <span className="ss-infer-val">{activeEvent.inference_duration_ms} ms</span>
                    </div>
                  )}
                </div>

                <div className="ss-infer-semantics-note">
                  <Info size={14} />
                  <span>{activeEvent.score_semantics}</span>
                </div>

                {/* Human-in-the-Loop Validation Section */}
                <div className="ss-sample-validation-actions">
                  <div className="ss-val-status-label">
                    <strong>Auditable Human Review:</strong>{' '}
                    {activeEvent.validation_status === 'validated' && (
                      <span className="ss-color-green">
                        ✓ Validated by {activeEvent.validated_by ?? 'Inspector'}{' '}
                        {activeEvent.validated_at ? `on ${new Date(activeEvent.validated_at).toLocaleDateString()}` : ''}
                      </span>
                    )}
                    {activeEvent.validation_status === 'rejected' && (
                      <span className="ss-color-red">
                        ✗ Rejected as False Positive by {activeEvent.validated_by ?? 'Inspector'}
                      </span>
                    )}
                    {activeEvent.validation_status === 'unvalidated' && (
                      <span className="ss-color-orange">Awaiting domain expert physical or acoustic sign-off</span>
                    )}
                  </div>

                  {activeEvent.validation_notes && (
                    <div className="ss-val-existing-note">
                      <em>Inspector Note: "{activeEvent.validation_notes}"</em>
                    </div>
                  )}

                  {onValidate && (
                    <div className="ss-val-button-row">
                      {validationModal?.id === activeEvent.id ? (
                        <div className="ss-val-form">
                          <input
                            type="text"
                            className="ss-input"
                            placeholder={`Reason for ${validationModal.status}...`}
                            value={validationModal.notes}
                            onChange={e => setValidationModal({ ...validationModal, notes: e.target.value })}
                          />
                          <button
                            id={`confirm-val-${activeEvent.id}`}
                            className={`ss-btn ss-btn-sm ${validationModal.status === 'validated' ? 'ss-btn-primary' : 'ss-btn-warn'}`}
                            onClick={async () => {
                              await onValidate(activeEvent.id, validationModal.status, validationModal.notes);
                              setValidationModal(null);
                            }}
                          >
                            Confirm {validationModal.status === 'validated' ? 'Validation' : 'Rejection'}
                          </button>
                          <button className="ss-btn ss-btn-ghost ss-btn-sm" onClick={() => setValidationModal(null)}>Cancel</button>
                        </div>
                      ) : (
                        <>
                          <button
                            id={`btn-validate-${activeEvent.id}`}
                            className="ss-btn ss-btn-outline ss-btn-sm"
                            onClick={() => setValidationModal({ id: activeEvent.id, status: 'validated', notes: '' })}
                          >
                            <Check size={13} /> Validate (True Anomaly)
                          </button>
                          <button
                            id={`btn-reject-${activeEvent.id}`}
                            className="ss-btn ss-btn-ghost ss-btn-sm"
                            onClick={() => setValidationModal({ id: activeEvent.id, status: 'rejected', notes: '' })}
                          >
                            <X size={13} /> Reject (False Positive)
                          </button>
                          {onBatchReview && (activeEvent.review_status ?? 'unreviewed') === 'unreviewed' && (
                            <button
                              id={`btn-review-${activeEvent.id}`}
                              className="ss-btn ss-btn-outline ss-btn-sm"
                              style={{ marginLeft: 'auto', borderColor: 'var(--accent)' }}
                              disabled={reviewing}
                              onClick={() => handleBatchReview([activeEvent.id])}
                            >
                              <CheckCheck size={13} /> Mark Reviewed
                            </button>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </section>
          )}

          {/* Frigate-Inspired Review Queue & Filterable Feed */}
          <section className="ss-section">
            <div className="ss-section-header-row">
              <div>
                <h2 className="ss-section-title">Frigate-Style Event Review Queue</h2>
                <div className="ss-section-sub">
                  Silo bioacoustic review lifecycle: triage unreviewed audio spikes, separate alerts from ambient detections, and mark reviewed in batch.
                </div>
              </div>
              {onBatchReview && unreviewedCount > 0 && (
                <button
                  id="batch-review-all-btn"
                  className="ss-btn ss-btn-primary ss-btn-sm"
                  disabled={reviewing}
                  onClick={() => {
                    const unreviewedIds = events
                      .filter(e => (e.review_status ?? 'unreviewed') === 'unreviewed')
                      .map(e => e.id);
                    handleBatchReview(unreviewedIds);
                  }}
                >
                  <CheckCheck size={14} /> Mark All {unreviewedCount} Reviewed
                </button>
              )}
            </div>

            {/* Frigate Review Filters Toolbar */}
            <div className="ss-frigate-toolbar">
              <div className="ss-filter-subgroup">
                <span className="ss-filter-label"><Layers size={13} /> Review Queue:</span>
                {(['all', 'unreviewed', 'reviewed'] as const).map(rf => (
                  <button
                    key={rf}
                    id={`filter-review-${rf}`}
                    className={`ss-filter-btn ${reviewFilter === rf ? 'active' : ''}`}
                    onClick={() => setReviewFilter(rf)}
                  >
                    {rf === 'unreviewed' && unreviewedCount > 0 && (
                      <span className="ss-badge-count">{unreviewedCount}</span>
                    )}
                    {rf.charAt(0).toUpperCase() + rf.slice(1)}
                  </button>
                ))}
              </div>

              <div className="ss-filter-subgroup">
                <span className="ss-filter-label"><ShieldAlert size={13} /> Severity Tier:</span>
                {(['all', 'alert', 'detection'] as const).map(tf => (
                  <button
                    key={tf}
                    id={`filter-tier-${tf}`}
                    className={`ss-filter-btn ${tierFilter === tf ? 'active' : ''}`}
                    onClick={() => setTierFilter(tf)}
                  >
                    {tf === 'all' ? 'All Tiers' : tf === 'alert' ? '🔴 Alerts' : '⚪ Detections'}
                  </button>
                ))}
              </div>

              <div className="ss-filter-subgroup">
                <span className="ss-filter-label">Validation:</span>
                {(['all', 'unvalidated', 'validated', 'rejected'] as const).map(f => (
                  <button
                    key={f}
                    id={`filter-val-${f}`}
                    className={`ss-filter-btn ${valFilter === f ? 'active' : ''}`}
                    onClick={() => setValFilter(f)}
                  >
                    {f.charAt(0).toUpperCase() + f.slice(1)}
                  </button>
                ))}
              </div>
            </div>

            {filteredEvents.length === 0 ? (
              <div className="ss-empty">No acoustic samples match the active filters</div>
            ) : (
              <div className="ss-event-list">
                {filteredEvents.map(ev => (
                  <div
                    key={ev.id}
                    id={`acoustic-row-${ev.id}`}
                    className={`ss-event-row clickable ${activeEvent?.id === ev.id ? 'active-sample' : ''}`}
                    onClick={() => setInspectEventId(ev.id)}
                  >
                    <div className="ss-event-ts">
                      <Clock size={12} />
                      {new Date(ev.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </div>
                    <div className="ss-event-body">
                      <div className="ss-event-pred">
                        <span className={`ss-tier-tag tier-${ev.event_tier ?? 'detection'}`}>
                          {ev.event_tier === 'alert' ? '🔴 Bioacoustic Alert' : '⚪ Ambient Detection'}
                        </span>
                        <span className={`ss-review-tag review-${ev.review_status ?? 'unreviewed'}`}>
                          {(ev.review_status ?? 'unreviewed').toUpperCase()}
                        </span>
                        <span style={{ fontWeight: 600 }}>{ev.prediction}</span>
                        <span className={`ss-val-tag val-${ev.validation_status}`}>{ev.validation_status}</span>
                      </div>
                      <div className="ss-event-meta">
                        Score: <strong>{ev.score !== null ? ev.score.toFixed(3) : 'N/A'}</strong> ·{' '}
                        Confidence: <span style={{ color: bandColor(ev.confidence_band) }}>{ev.confidence_band}</span> ·{' '}
                        Origin: {ev.zone_id}
                        {ev.reviewed_by && (
                          <span className="ss-text-muted"> · Reviewed by {ev.reviewed_by}</span>
                        )}
                        <SourceBadge source={ev.source} />
                      </div>
                      {ev.notes && <div className="ss-event-notes">{ev.notes}</div>}
                    </div>
                    <div className="ss-event-actions-compact">
                      {(ev.review_status ?? 'unreviewed') === 'unreviewed' && onBatchReview && (
                        <button
                          className="ss-btn ss-btn-ghost ss-btn-xs"
                          title="Mark Reviewed"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleBatchReview([ev.id]);
                          }}
                        >
                          <CheckCheck size={12} /> Review
                        </button>
                      )}
                      <span className="ss-text-xs ss-text-muted">Inspect →</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Hardware & Microphone Pinout Table */}
          <section className="ss-section">
            <h2 className="ss-section-title">Hardware I2S Configuration</h2>
            <div className="ss-hw-table">
              <div className="ss-hw-row"><span>Microphone</span><span>INMP441 I2S MEMS Sensor</span></div>
              <div className="ss-hw-row"><span>BCLK / SCK</span><span>GPIO 26</span></div>
              <div className="ss-hw-row"><span>WS / LRCLK</span><span>GPIO 25</span></div>
              <div className="ss-hw-row"><span>SD / DOUT</span><span>GPIO 33</span></div>
              <div className="ss-hw-row"><span>L/R Channel</span><span>GND (Mono Left Channel)</span></div>
              <div className="ss-hw-row"><span>Sample Rate</span><span>16,000 Hz (16-bit PCM mono window)</span></div>
              <div className="ss-hw-row"><span>Processing Window</span><span>10.0 s sliding frame</span></div>
              <div className="ss-hw-row"><span>Bioacoustic Model</span><span>nocturne-v1-mini (EXPERIMENTAL — unvalidated for storage insects)</span></div>
            </div>
          </section>
        </>
      )}

      {/* ─── Retained Dataset & Offline Evaluation Tab ────────────────────────── */}
      {activeTab === 'dataset_library' && (
        <div className="ss-dataset-tab-content">
          {/* Action Toolbar */}
          <div className="ss-section-header-row" style={{ alignItems: 'flex-start', flexWrap: 'wrap', gap: '14px' }}>
            <div>
              <h2 className="ss-section-title">
                Acoustic Dataset Library & Offline Evaluation
              </h2>
              <div className="ss-section-sub">
                Retain original recordings outside SQLite, annotate independent physical observations (traps/sieves), and evaluate anomaly detection models.
              </div>
            </div>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <span className="ss-text-xs ss-text-muted">Threshold:</span>
                <input
                  type="number"
                  step="0.01"
                  min="0.0"
                  max="1.0"
                  className="ss-input"
                  style={{ width: '68px', padding: '3px 6px', fontSize: '12px' }}
                  value={evalThreshold}
                  onChange={e => setEvalThreshold(parseFloat(e.target.value) || 0.05)}
                  title="Anomaly decision score threshold for evaluation"
                />
              </div>
              <button
                id="btn-run-evaluation"
                className="ss-btn ss-btn-primary ss-btn-sm"
                onClick={handleRunEvaluation}
                disabled={evaluating}
              >
                {evaluating ? <Loader2 size={13} className="ss-spin" /> : <BarChart3 size={13} />}
                Run Evaluation
              </button>
              <a
                href={api.datasetManifestUrl('json', false)}
                target="_blank"
                rel="noreferrer"
                className="ss-btn ss-btn-outline ss-btn-sm"
                download="sealsense_dataset_manifest.json"
              >
                <Download size={13} /> Export JSON
              </a>
              <a
                href={api.datasetManifestUrl('csv', false)}
                target="_blank"
                rel="noreferrer"
                className="ss-btn ss-btn-outline ss-btn-sm"
                download="sealsense_dataset_manifest.csv"
              >
                <Download size={13} /> Export CSV
              </a>
              <button
                className="ss-btn ss-btn-ghost ss-btn-sm"
                onClick={handleSeedDemoSamples}
                title="Populate sample library with verified ground-truth test data"
              >
                <Sparkles size={13} /> Seed Demo Samples
              </button>
              <button
                className="ss-btn ss-btn-ghost ss-btn-sm"
                onClick={loadSamples}
                disabled={loadingSamples}
              >
                <RefreshCw size={13} className={loadingSamples ? 'ss-spin' : ''} />
              </button>
            </div>
          </div>

          {/* Evaluation Report Card */}
          {evalReport && (
            <div className="ss-eval-container" id="dataset-evaluation-card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '10px' }}>
                <div>
                  <h3 style={{ fontSize: '15px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <BarChart3 size={16} style={{ color: 'var(--accent-light)' }} />
                    Bioacoustic Dataset Evaluation Report
                  </h3>
                  <div className="ss-text-xs ss-text-muted" style={{ marginTop: '2px' }}>
                    Generated at {new Date(evalReport.timestamp).toLocaleString()} · Anomaly Decision Threshold: <strong>{evalReport.anomaly_threshold}</strong>
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span className="ss-badge ss-mono ss-text-xs">
                    Eligible: {evalReport.eligible_samples} / {evalReport.total_samples} samples
                  </span>
                </div>
              </div>

              {/* Vocabulary & Guardrail Notice */}
              <div className="ss-exp-banner ss-exp-banner-warn" style={{ marginTop: '14px', marginBottom: '14px' }}>
                <ShieldAlert size={18} />
                <div style={{ fontSize: '11.5px' }}>
                  <strong>TAXONOMIC VOCABULARY GUARDRAIL:</strong> {evalReport.vocabulary_alignment}
                </div>
              </div>

              {/* High-Level Counts Grid */}
              <div className="ss-eval-stats-grid">
                <div className="ss-eval-stat-box">
                  <div className="ss-eval-stat-val">{evalReport.total_samples}</div>
                  <div className="ss-eval-stat-label">Total Retained</div>
                </div>
                <div className="ss-eval-stat-box" style={{ borderColor: 'rgba(34, 197, 94, 0.4)' }}>
                  <div className="ss-eval-stat-val" style={{ color: 'var(--green)' }}>{evalReport.eligible_samples}</div>
                  <div className="ss-eval-stat-label">Eligible Real Data</div>
                </div>
                <div className="ss-eval-stat-box" style={{ borderColor: 'rgba(239, 68, 68, 0.3)' }}>
                  <div className="ss-eval-stat-val" style={{ color: 'var(--red)' }}>{evalReport.excluded_samples}</div>
                  <div className="ss-eval-stat-label">Excluded Samples</div>
                </div>
                <div className="ss-eval-stat-box">
                  <div className="ss-eval-stat-val" style={{ color: '#c084fc' }}>
                    {evalReport.exclusion_breakdown['synthetic_test_signal'] || 0}
                  </div>
                  <div className="ss-eval-stat-label">Synthetic Excluded</div>
                </div>
                <div className="ss-eval-stat-box">
                  <div className="ss-eval-stat-val" style={{ color: '#94a3b8' }}>
                    {evalReport.exclusion_breakdown['unreviewed_sample'] || 0}
                  </div>
                  <div className="ss-eval-stat-label">Unreviewed Excluded</div>
                </div>
                <div className="ss-eval-stat-box">
                  <div className="ss-eval-stat-val" style={{ color: '#facc15' }}>
                    {evalReport.exclusion_breakdown['inconclusive_observation'] || 0}
                  </div>
                  <div className="ss-eval-stat-label">Inconclusive Excluded</div>
                </div>
              </div>

              {/* Anomaly Detection Metrics (Confusion Matrix & Rates) */}
              {evalReport.anomaly_metrics ? (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '20px', marginTop: '16px' }}>
                  <div>
                    <span className="ss-waveform-title" style={{ display: 'block', marginBottom: '8px' }}>
                      Anomaly Detection Confusion Matrix (vs. Physical Traps)
                    </span>
                    <div className="ss-matrix-grid">
                      <div className="ss-matrix-cell tp">
                        <span className="ss-matrix-num">{evalReport.anomaly_metrics.true_positives}</span>
                        <span className="ss-matrix-lbl">True Positive (TP)<br />Pest Observed + High Score</span>
                      </div>
                      <div className="ss-matrix-cell fp">
                        <span className="ss-matrix-num">{evalReport.anomaly_metrics.false_positives}</span>
                        <span className="ss-matrix-lbl">False Positive (FP)<br />No Pest + High Score</span>
                      </div>
                      <div className="ss-matrix-cell fn">
                        <span className="ss-matrix-num">{evalReport.anomaly_metrics.false_negatives}</span>
                        <span className="ss-matrix-lbl">False Negative (FN)<br />Pest Observed + Low Score</span>
                      </div>
                      <div className="ss-matrix-cell tn">
                        <span className="ss-matrix-num">{evalReport.anomaly_metrics.true_negatives}</span>
                        <span className="ss-matrix-lbl">True Negative (TN)<br />No Pest + Low Score</span>
                      </div>
                    </div>
                  </div>

                  <div>
                    <span className="ss-waveform-title" style={{ display: 'block', marginBottom: '8px' }}>
                      Diagnostic Performance Rates
                    </span>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                      <div className="ss-eval-stat-box">
                        <div className="ss-eval-stat-val">
                          {evalReport.anomaly_metrics.precision !== null ? `${(evalReport.anomaly_metrics.precision * 100).toFixed(1)}%` : 'N/A'}
                        </div>
                        <div className="ss-eval-stat-label">Precision (PPV)</div>
                      </div>
                      <div className="ss-eval-stat-box">
                        <div className="ss-eval-stat-val">
                          {evalReport.anomaly_metrics.recall !== null ? `${(evalReport.anomaly_metrics.recall * 100).toFixed(1)}%` : 'N/A'}
                        </div>
                        <div className="ss-eval-stat-label">Recall (Sensitivity)</div>
                      </div>
                      <div className="ss-eval-stat-box">
                        <div className="ss-eval-stat-val">
                          {evalReport.anomaly_metrics.specificity !== null ? `${(evalReport.anomaly_metrics.specificity * 100).toFixed(1)}%` : 'N/A'}
                        </div>
                        <div className="ss-eval-stat-label">Specificity (TNR)</div>
                      </div>
                      <div className="ss-eval-stat-box">
                        <div className="ss-eval-stat-val">
                          {evalReport.anomaly_metrics.f1_score !== null ? evalReport.anomaly_metrics.f1_score.toFixed(3) : 'N/A'}
                        </div>
                        <div className="ss-eval-stat-label">F1-Score</div>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="ss-empty" style={{ margin: '14px 0' }}>
                  No eligible real-world recordings with binary physical ground-truth (TARGET_PEST_OBSERVED or NO_TARGET_PEST_OBSERVED).
                  Annotate physical observation findings on retained real samples below to compute classification metrics.
                </div>
              )}

              {/* Provenance Breakdown Tags */}
              {evalReport.provenance_breakdown && (
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '14px', paddingTop: '10px', borderTop: '1px solid var(--border-subtle)', alignItems: 'center' }}>
                  <span className="ss-text-xs ss-text-muted" style={{ fontWeight: 600 }}>Library Provenance Breakdown:</span>
                  <span className="ss-source-pill public_reference">
                    📚 USDA Bug Bytes Reference: {evalReport.provenance_breakdown.public_reference || 0}
                  </span>
                  <span className="ss-source-pill user_upload">
                    📁 User Upload: {evalReport.provenance_breakdown.user_upload || 0}
                  </span>
                  <span className="ss-source-pill synthetic">
                    ⚡ Synthetic Simulation: {evalReport.provenance_breakdown.synthetic || 0}
                  </span>
                  {evalReport.provenance_breakdown.hardware_recording !== undefined && (
                    <span className="ss-source-pill hardware_recording">
                      🎙️ Hardware: {evalReport.provenance_breakdown.hardware_recording || 0}
                    </span>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Filtering and Search Toolbar */}
          <div className="ss-frigate-toolbar" style={{ marginTop: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: 1, minWidth: '220px' }}>
              <Search size={14} style={{ color: 'var(--text-muted)' }} />
              <input
                type="text"
                className="ss-input"
                placeholder="Search by filename, sample ID, species, notes, reviewer..."
                value={sampleSearch}
                onChange={e => setSampleSearch(e.target.value)}
                style={{ height: '30px', fontSize: '12px' }}
              />
            </div>

            <div className="ss-filter-subgroup">
              <span className="ss-filter-label"><Filter size={13} /> Ground Truth:</span>
              {(['all', 'UNREVIEWED', 'TARGET_PEST_OBSERVED', 'NO_TARGET_PEST_OBSERVED', 'INCONCLUSIVE'] as const).map(lbl => (
                <button
                  key={lbl}
                  className={`ss-filter-btn ${sampleLabelFilter === lbl ? 'active' : ''}`}
                  onClick={() => setSampleLabelFilter(lbl)}
                >
                  {lbl === 'all' ? 'All Labels' : lbl.replace(/_/g, ' ')}
                </button>
              ))}
            </div>

            <div className="ss-filter-subgroup">
              <span className="ss-filter-label">Provenance Source:</span>
              {(['all', 'public_reference', 'user_upload', 'synthetic'] as const).map(src => (
                <button
                  key={src}
                  className={`ss-filter-btn ${sampleSourceFilter === src ? 'active' : ''}`}
                  onClick={() => setSampleSourceFilter(src)}
                >
                  {src === 'all' ? 'All Sources' : src === 'public_reference' ? '📚 Public Reference' : src === 'user_upload' ? '📁 User Upload' : '⚡ Synthetic'}
                </button>
              ))}
            </div>
          </div>

          {/* Retained Samples Table */}
          {loadingSamples ? (
            <div className="ss-empty">
              <Loader2 size={16} className="ss-spin" /> Loading retained audio samples…
            </div>
          ) : filteredSamples.length === 0 ? (
            <div className="ss-empty">
              No retained audio samples found. Select a USDA Bug Bytes reference recording or generate a synthetic scenario to populate the library.
            </div>
          ) : (
            <div className="ss-sample-table-card">
              <div className="ss-sample-row ss-sample-row-header">
                <div>Sample & Origin</div>
                <div>Audio Player</div>
                <div>Duration / Rate</div>
                <div>Ground-Truth Evidence</div>
                <div>Model Inference</div>
                <div>Label Status</div>
                <div style={{ textAlign: 'right' }}>Actions</div>
              </div>

              {filteredSamples.map(sample => (
                <div key={sample.id} className="ss-sample-row" id={`sample-row-${sample.id}`}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <FileAudio size={14} style={{ color: 'var(--accent-light)' }} />
                      <strong style={{ fontSize: '13px' }} title={sample.filename}>{sample.filename}</strong>
                    </div>
                    <div className="ss-text-xs ss-mono ss-text-muted" style={{ marginTop: '2px' }}>
                      ID: {sample.id} · SHA: {sample.sha256_hash.slice(0, 10)}…
                    </div>
                    <div style={{ marginTop: '4px', display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                      {sample.input_source === 'public_reference' && (
                        <span className="ss-source-pill public_reference">
                          📚 USDA Bug Bytes
                        </span>
                      )}
                      {sample.input_source === 'synthetic' && (
                        <span className="ss-source-pill synthetic">
                          ⚡ Synthetic (Excluded)
                        </span>
                      )}
                      {sample.input_source === 'user_upload' && (
                        <span className="ss-source-pill user_upload">
                          📁 User Upload
                        </span>
                      )}
                      {sample.input_source === 'hardware_recording' && (
                        <span className="ss-source-pill hardware_recording">
                          🎙️ Hardware
                        </span>
                      )}
                    </div>
                    {sample.source_species && (
                      <div className="ss-text-xs" style={{ color: '#34d399', marginTop: '3px' }}>
                        <em>{sample.source_species}</em> · <span className="ss-text-muted">{sample.transducer_type || 'contact sensor'}</span>
                      </div>
                    )}
                  </div>

                  <div className="ss-audio-player-mini">
                    <audio
                      controls
                      preload="none"
                      src={api.getAudioSampleUrl(sample.id)}
                    />
                  </div>

                  <div>
                    <div style={{ fontSize: '12px', fontWeight: 600 }}>{sample.duration_sec.toFixed(1)}s</div>
                    <div className="ss-text-xs ss-text-muted">
                      {sample.sample_rate.toLocaleString()} Hz · {sample.channels === 1 ? 'Mono' : `${sample.channels} Ch`}
                    </div>
                  </div>

                  <div>
                    <div style={{ fontSize: '12px' }}>
                      <strong>Method:</strong> <span className="ss-mono ss-text-xs">{sample.verification_method || 'unverified'}</span>
                    </div>
                    {sample.evidence_notes ? (
                      <div className="ss-text-xs ss-text-muted" style={{ fontStyle: 'italic', marginTop: '2px' }} title={sample.evidence_notes}>
                        "{sample.evidence_notes.length > 55 ? `${sample.evidence_notes.slice(0, 55)}…` : sample.evidence_notes}"
                      </div>
                    ) : (
                      <div className="ss-text-xs ss-text-muted">No evidence notes recorded</div>
                    )}
                    {sample.reviewer && (
                      <div className="ss-text-xs" style={{ color: 'var(--accent-light)', marginTop: '2px' }}>
                        By: {sample.reviewer}
                      </div>
                    )}
                  </div>

                  <div>
                    <div style={{ fontSize: '12px', fontWeight: 600 }}>{sample.prediction || 'N/A'}</div>
                    <div className="ss-text-xs ss-text-muted">
                      Score: <strong>{sample.score !== null && sample.score !== undefined ? sample.score.toFixed(4) : 'N/A'}</strong>
                    </div>
                  </div>

                  <div>
                    <span className={`ss-label-pill label-${sample.ground_truth_label}`}>
                      {sample.ground_truth_label.replace(/_/g, ' ')}
                    </span>
                  </div>

                  <div style={{ display: 'flex', gap: '6px', justifyContent: 'flex-end' }}>
                    <button
                      id={`btn-annotate-${sample.id}`}
                      className="ss-btn ss-btn-outline ss-btn-xs"
                      onClick={() => handleOpenAnnotationModal(sample)}
                      title="Annotate independent physical ground truth"
                    >
                      <Edit3 size={12} /> Annotate
                    </button>
                    <button
                      className="ss-btn ss-btn-ghost ss-btn-xs"
                      onClick={() => handleDeleteSample(sample.id)}
                      title="Delete sample from storage & database"
                      style={{ color: 'var(--red)' }}
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Ground-Truth Annotation Modal */}
          {editingSample && (
            <div className="ss-modal-overlay">
              <div className="ss-modal-box">
                <div className="ss-modal-header">
                  <div className="ss-modal-title">
                    Independent Ground-Truth Annotation
                  </div>
                  <button
                    className="ss-btn ss-btn-ghost ss-btn-xs"
                    onClick={() => setEditingSample(null)}
                  >
                    <X size={16} />
                  </button>
                </div>

                <div style={{ marginBottom: '14px', fontSize: '12px', color: 'var(--text-secondary)' }}>
                  Sample: <strong>{editingSample.filename}</strong> (<code>{editingSample.id}</code>)
                  <br />
                  <span className="ss-text-muted">
                    Record physical observation findings from grain traps, grain sieves, or lab inspections.
                    Do not equate model predictions with confirmed biological pest presence.
                  </span>
                </div>

                <div className="ss-form-group">
                  <label className="ss-form-label">Ground-Truth Observation Label</label>
                  <select
                    className="ss-select"
                    value={editForm.label}
                    onChange={e => setEditForm({ ...editForm, label: e.target.value as GroundTruthLabel })}
                  >
                    <option value="UNREVIEWED">UNREVIEWED (Awaiting independent physical inspection)</option>
                    <option value="TARGET_PEST_OBSERVED">TARGET_PEST_OBSERVED (Physical trap/sieve confirmed target insects)</option>
                    <option value="NO_TARGET_PEST_OBSERVED">NO_TARGET_PEST_OBSERVED (Physical inspection confirmed pest-free)</option>
                    <option value="INCONCLUSIVE">INCONCLUSIVE (Ambiguous physical findings / deep traps pending)</option>
                  </select>
                </div>

                <div className="ss-form-group">
                  <label className="ss-form-label">Verification Method</label>
                  <select
                    className="ss-select"
                    value={editForm.method}
                    onChange={e => setEditForm({ ...editForm, method: e.target.value as VerificationMethod })}
                  >
                    <option value="physical_trap_inspection">physical_trap_inspection (Spear probe pitfall trap)</option>
                    <option value="grain_sieve">grain_sieve (Manual grain sieve tray sample)</option>
                    <option value="visual_sample">visual_sample (Visual surface / headspace inspection)</option>
                    <option value="acoustic_expert_review">acoustic_expert_review (Entomologist audio review)</option>
                    <option value="laboratory_reared_culture">laboratory_reared_culture (USDA-ARS verified culture)</option>
                    <option value="unverified">unverified (No verified method)</option>
                  </select>
                </div>

                <div className="ss-form-group">
                  <label className="ss-form-label">Reviewer / Entomologist Name</label>
                  <input
                    type="text"
                    className="ss-input"
                    value={editForm.reviewer}
                    onChange={e => setEditForm({ ...editForm, reviewer: e.target.value })}
                    placeholder="e.g. Dr. Aris Thorne (Entomologist)"
                  />
                </div>

                <div className="ss-form-group">
                  <label className="ss-form-label">Physical Evidence & Observation Notes</label>
                  <textarea
                    className="ss-input"
                    rows={3}
                    value={editForm.notes}
                    onChange={e => setEditForm({ ...editForm, notes: e.target.value })}
                    placeholder="Record insect count, species identified, sieve mesh size, trap location..."
                    style={{ height: '70px', resize: 'vertical' }}
                  />
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '16px' }}>
                  <button
                    className="ss-btn ss-btn-ghost ss-btn-sm"
                    onClick={() => setEditingSample(null)}
                    disabled={savingAnnotation}
                  >
                    Cancel
                  </button>
                  <button
                    id="btn-save-annotation"
                    className="ss-btn ss-btn-primary ss-btn-sm"
                    onClick={handleSaveAnnotation}
                    disabled={savingAnnotation}
                  >
                    {savingAnnotation ? <Loader2 size={13} className="ss-spin" /> : <Check size={13} />}
                    Save Ground-Truth Annotation
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
