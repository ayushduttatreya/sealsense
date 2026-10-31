import { useState, useRef } from 'react';
import {
  Mic, MicOff, FlaskConical, Clock, Info, Check, X,
  Activity, Volume2, CheckCheck, ShieldAlert, Layers,
  Upload, FileAudio, AlertTriangle, Sparkles, Loader2, RefreshCw
} from 'lucide-react';
import { SourceBadge } from '../components/SourceBadge';
import { api } from '../lib/api';
import type { AcousticEvent, ValidationStatus, AcousticInferenceResult } from '../types';

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
  const [valFilter, setValFilter] = useState<ValidationStatus | 'all'>('all');
  const [reviewFilter, setReviewFilter] = useState<'all' | 'unreviewed' | 'reviewed'>('all');
  const [tierFilter, setTierFilter] = useState<'all' | 'alert' | 'detection'>('all');
  const [inspectEventId, setInspectEventId] = useState<string>(events[events.length - 1]?.id ?? '');
  const [validationModal, setValidationModal] = useState<{ id: string; status: 'validated' | 'rejected'; notes: string } | null>(null);
  const [reviewing, setReviewing] = useState<boolean>(false);

  // Recorded Audio Ingestion State
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState<boolean>(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadResult, setUploadResult] = useState<AcousticInferenceResult | null>(null);
  const [saveToQueue, setSaveToQueue] = useState<boolean>(false);
  const [isSyntheticTest, setIsSyntheticTest] = useState<boolean>(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const activeEvent = events.find(e => e.id === inspectEventId) ?? events[events.length - 1];
  const micActive = activeEvent?.inference_status !== 'unavailable';

  const unreviewedCount = events.filter(e => (e.review_status ?? 'unreviewed') === 'unreviewed').length;

  const filteredEvents = events.filter(e => {
    if (valFilter !== 'all' && e.validation_status !== valFilter) return false;
    if (reviewFilter !== 'all' && (e.review_status ?? 'unreviewed') !== reviewFilter) return false;
    if (tierFilter !== 'all' && (e.event_tier ?? 'detection') !== tierFilter) return false;
    return true;
  });

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
    setIsSyntheticTest(false);
  };

  const handleExecuteUpload = async (fileToUpload?: File | Blob, filename?: string, synthetic = false) => {
    const targetFile = fileToUpload ?? selectedFile;
    if (!targetFile) return;

    const name = filename ?? (targetFile instanceof File ? targetFile.name : 'audio_recording.wav');
    setUploading(true);
    setUploadError(null);
    setIsSyntheticTest(synthetic);

    try {
      const result = await api.uploadAcousticRecording(
        targetFile,
        name,
        'zone-a',
        'esp32-zone-a-01',
        saveToQueue
      );
      setUploadResult(result);
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

  const handleResetUpload = () => {
    setSelectedFile(null);
    setUploadResult(null);
    setUploadError(null);
    setIsSyntheticTest(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const waveform = activeEvent?.waveform_preview ?? [0.08, 0.12, 0.35, 0.65, 0.78, 0.45, 0.22, 0.15, 0.48, 0.82, 0.61, 0.28, 0.18, 0.32, 0.14, 0.09];

  return (
    <div className="ss-page">
      <div className="ss-page-header">
        <div>
          <h1 className="ss-page-title">Acoustic Insect Monitoring</h1>
          <div className="ss-page-subtitle">
            Edge Impulse pattern: 16 kHz INMP441 bioacoustic feature inspection & human-in-the-loop validation
          </div>
        </div>
        <div className="ss-page-meta">
          <span className={`ss-status-pill ${micActive ? 'live' : 'demo'}`}>
            {micActive ? <Mic size={13} /> : <MicOff size={13} />}
            {micActive ? 'I2S Mic Active' : 'Mic Offline / Inference Blocked'}
          </span>
          <span className="ss-text-muted ss-text-xs">{events.length} samples</span>
        </div>
      </div>

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
              Recorded Audio Ingestion & Inference
            </h2>
            <div className="ss-section-sub">
              Upload field WAV audio or test synthetic signals through the Nocturne Mini model forward path.
            </div>
          </div>
          <div className="ss-flex-gap">
            <span className="ss-badge ss-mono ss-text-xs">
              Model: stratus-labs/nocturne-v1-mini
            </span>
          </div>
        </div>

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
            <div className="ss-upload-actions-left">
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

              <button
                id="btn-run-synthetic-test"
                className="ss-btn ss-btn-outline ss-btn-sm"
                disabled={uploading}
                onClick={handleSyntheticTest}
              >
                {uploading && isSyntheticTest ? (
                  <>
                    <Loader2 size={13} className="ss-spin" /> Synthesizing & Running…
                  </>
                ) : (
                  <>
                    <Sparkles size={13} /> Quick Test: 10s Synthetic Chirp
                  </>
                )}
              </button>

              <label className="ss-checkbox-label" style={{ fontSize: '12px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <input
                  type="checkbox"
                  checked={saveToQueue}
                  onChange={e => setSaveToQueue(e.target.checked)}
                />
                Save as event in Frigate review queue
              </label>
            </div>

            {(selectedFile || uploadResult) && (
              <div className="ss-upload-actions-right">
                <button
                  className="ss-btn ss-btn-ghost ss-btn-xs"
                  onClick={handleResetUpload}
                  disabled={uploading}
                >
                  <RefreshCw size={12} /> Clear / New Test
                </button>
              </div>
            )}
          </div>

          {/* Upload & Validation Error Banner */}
          {uploadError && (
            <div className="ss-alert ss-alert-critical" style={{ marginTop: '14px' }}>
              <AlertTriangle size={16} />
              <div>
                <strong>Audio Upload Rejected:</strong> {uploadError}
              </div>
            </div>
          )}

          {/* Genuine Inference Result Visualization */}
          {uploadResult && (
            <div className="ss-upload-result-container" id="acoustic-inference-result-box">
              <div className="ss-result-header-row">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                  <FileAudio size={16} style={{ color: 'var(--accent-light)' }} />
                  <span style={{ fontWeight: 600, fontSize: '14px' }}>
                    {uploadResult.filename ?? 'audio_sample.wav'}
                  </span>
                  <span className={`ss-source-pill ${isSyntheticTest || uploadResult.input_source === 'synthetic' ? 'synthetic' : 'user_upload'}`}>
                    {isSyntheticTest || uploadResult.input_source === 'synthetic' ? '⚡ SYNTHETIC TEST SIGNAL' : '📁 USER UPLOAD'}
                  </span>
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
                </div>
              </div>

              {/* Ingestion & Standardization Details Grid */}
              <div className="ss-infer-grid" style={{ marginBottom: '14px' }}>
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
                  <strong>DOMAIN LIMITATION:</strong> {uploadResult.limitations}
                </div>
              </div>
            </div>
          )}
        </div>
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

            {/* Spectrogram Frequency Peaks (Edge Impulse Style) */}
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
    </div>
  );
}

