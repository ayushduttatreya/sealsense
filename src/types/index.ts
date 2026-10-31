// ─── Source Labels ────────────────────────────────────────────────────────────
export type DataSource = 'REAL' | 'SIMULATED' | 'MODEL_EXPERIMENT';

// ─── Devices & Zones ──────────────────────────────────────────────────────────
export interface Device {
  id: string;
  name: string;
  zone_id: string;
  firmware_version: string;
  last_seen: string;
  connected: boolean;
  inactivity_timeout_sec: number;
  last_activity_time?: string;
  is_active?: boolean;
  sensors: SensorInventory[];
}

export interface SensorInventory {
  type: 'SCD41' | 'INMP441' | 'BUZZER';
  status: 'ok' | 'error' | 'unknown' | 'not_connected' | 'unavailable';
  last_reading?: string;
}

export interface Zone {
  id: string;
  name: string;
  description: string;
  device_ids: string[];
  health: 'healthy' | 'warning' | 'critical' | 'unknown';
}

// ─── Environmental Readings ────────────────────────────────────────────────────
export interface EnvironmentalReading {
  id: string;
  timestamp: string;
  zone_id: string;
  device_id: string;
  source: DataSource;
  co2_ppm: number | null;
  temperature_c: number | null;
  relative_humidity_pct: number | null;
  co2_valid: boolean;
  temp_valid: boolean;
  rh_valid: boolean;
  audio_rms?: number | null;
  audio_peak?: number | null;
  audio_rms_dbfs?: number | null;
  audio_peak_dbfs?: number | null;
  audio_valid?: boolean;
  transport?: 'usb_serial' | 'wifi' | string;
  firmware_version?: string;
}

export interface LatestTelemetryResponse {
  reading: EnvironmentalReading | null;
  is_hardware: boolean;
  source: DataSource;
  transport: string | null;
  age_seconds: number | null;
  device_status: 'online' | 'stale' | 'offline';
}

export interface TelemetryHistoryResponse {
  readings: EnvironmentalReading[];
  count: number;
  device_id: string | null;
  zone_id: string | null;
  time_range: string;
  source: DataSource;
  is_hardware: boolean;
}

// ─── Acoustic Events ──────────────────────────────────────────────────────────
export type ValidationStatus = 'unvalidated' | 'validated' | 'rejected';
export type InferenceStatus =
  | 'complete'
  | 'running'
  | 'unavailable'
  | 'experimental'
  | 'error';

export interface AcousticEvent {
  id: string;
  timestamp: string;
  zone_id: string;
  device_id: string;
  source: DataSource;
  audio_sample_ref?: string;
  prediction: string;
  model_version: string;
  score: number | null;
  score_semantics: string;
  confidence_band: 'low' | 'medium' | 'high' | 'uncertain';
  validation_status: ValidationStatus;
  inference_status: InferenceStatus;
  inference_duration_ms?: number;
  validation_notes?: string;
  validated_at?: string;
  validated_by?: string;
  waveform_preview?: number[];
  spectrogram_peaks?: { freq_hz: number; db: number }[];
  review_status?: 'unreviewed' | 'reviewed';
  event_tier?: 'alert' | 'detection';
  reviewed_at?: string;
  reviewed_by?: string;
  notes?: string;
}

export interface PredictionItem {
  label: string;
  score: number;
}

export type RecordingDomain =
  | 'airborne_microphone'
  | 'accelerometer'
  | 'piezoelectric'
  | 'pvdf'
  | 'ultrasonic_transducer'
  | 'synthetic_simulation'
  | 'unknown';

export interface SignalAnalysisResult {
  rms_energy: number;
  rms_db: number;
  peak_amplitude: number;
  peak_dbfs: number;
  spectral_centroid_hz: number;
  spectral_bandwidth_hz: number;
  spectral_flatness: number;
  zero_crossing_rate: number;
  zero_crossings_per_sec: number;
  band_energy_distribution: {
    sub_1k_pct: number;
    band_1k_4k_pct: number;
    band_4k_8k_pct: number;
    ultrasonic_8k_plus_pct: number;
    sub_1khz_pct?: number;
    band_1k_to_4k_pct?: number;
    band_4k_to_8k_pct?: number;
    ultrasonic_gt_8k_pct?: number;
  };
  transient_click_count: number;
  transient_clicks_per_sec: number;
  transient_detection_method: string;
  duration_sec: number;
  analyzed_sample_rate: number;
  method_notes?: string;
  scientific_disclaimer?: string;
}

export interface AcousticInferenceResult {
  status: 'READY' | 'UNAVAILABLE' | 'EXPERIMENTAL' | 'ERROR';
  model_id: string;
  prediction: string;
  score?: number | null;
  score_semantics: string;
  top_predictions: PredictionItem[];
  confidence_band: 'low' | 'medium' | 'high' | 'uncertain';
  inference_duration_ms?: number | null;
  audio_sample_rate: number;
  audio_duration_sec: number;
  waveform_preview?: number[] | null;
  spectrogram_peaks?: { frequency_hz?: number; freq_hz?: number; magnitude_db?: number; db?: number }[];
  limitations: string;
  error?: string | null;
  reason?: string | null;
  input_source?: 'user_upload' | 'synthetic' | 'live_stream' | 'public_reference' | 'hardware_recording';
  filename?: string | null;
  original_sample_rate?: number | null;
  original_channels?: number | null;
  original_duration_sec?: number | null;
  window_mode?: 'exact' | 'padded' | 'truncated' | null;
  audio_sample_id?: string | null;
  is_retained?: boolean;
  dataset_name?: string | null;
  source_species?: string | null;
  source_citation?: string | null;
  source_url?: string | null;
  transducer_type?: string | null;
  recording_domain?: RecordingDomain;
  simulation_params?: Record<string, any> | null;
  signal_analysis?: SignalAnalysisResult | null;
}

// ─── Retained Audio Dataset & Evaluation ──────────────────────────────────────
export type GroundTruthLabel =
  | 'UNREVIEWED'
  | 'REVIEWED'
  | 'TARGET_PEST_OBSERVED'
  | 'NO_TARGET_PEST_OBSERVED'
  | 'INCONCLUSIVE';

export type VerificationMethod =
  | 'physical_trap_inspection'
  | 'grain_sieve'
  | 'visual_sample'
  | 'acoustic_expert_review'
  | 'laboratory_reared_culture'
  | 'unverified';

export interface RetainedAudioSample {
  id: string;
  filename: string;
  stored_filename: string;
  file_size_bytes: number;
  sha256_hash: string;
  duration_sec: number;
  sample_rate: number;
  channels: number;
  format: string;
  timestamp: string;
  recording_timestamp?: string | null;
  zone_id: string;
  device_id: string;
  input_source: 'user_upload' | 'hardware_recording' | 'synthetic' | 'public_reference';
  is_synthetic: boolean;
  recording_domain?: RecordingDomain;
  model_id?: string | null;
  model_version?: string | null;
  prediction?: string | null;
  score?: number | null;
  confidence_band?: string | null;
  top_predictions: PredictionItem[];
  waveform_preview?: number[] | null;
  spectrogram_peaks?: { freq_hz?: number; db?: number }[] | null;
  signal_analysis?: SignalAnalysisResult | null;
  review_status: 'UNREVIEWED' | 'REVIEWED';
  ground_truth_label: GroundTruthLabel;
  verification_method: VerificationMethod;
  reviewer?: string | null;
  reviewed_at?: string | null;
  evidence_notes?: string | null;
  dataset_name?: string | null;
  source_species?: string | null;
  source_citation?: string | null;
  source_url?: string | null;
  transducer_type?: string | null;
  source_category?: string | null;
  created_at: string;
}

// ─── Public Reference Audio Schemas ──────────────────────────────────────────
export interface ReferenceAudioCatalogItem {
  id: string;
  filename: string;
  species: string;
  common_name: string;
  life_stage: string;
  substrate: string;
  transducer_type: string;
  recording_domain: RecordingDomain;
  frequency_range?: string | null;
  sample_width_bits?: number | null;
  sample_width_bytes?: number | null;
  laboratory_setup?: string | null;
  category: string;
  description: string;
  duration_sec: number;
  sample_rate: number;
  channels: number;
  dataset_name: string;
  citation: string;
  source_url: string;
  sha256_hash?: string | null;
  is_locally_available: boolean;
  file_size_bytes?: number | null;
  notes: string;
}

export interface ReferenceImportRequest {
  catalog_id: string;
  retain_sample?: boolean;
  zone_id?: string;
  device_id?: string;
  notes?: string | null;
}

// ─── Synthetic Bioacoustic Simulation Schemas ─────────────────────────────────
export interface SyntheticImpulseRequest {
  impulse_rate?: number;
  amplitude?: number;
  noise_level?: number;
  duration_sec?: number;
  seed?: number;
  run_inference?: boolean;
  retain_sample?: boolean;
  zone_id?: string;
  device_id?: string;
}

export interface DatasetEvaluationReport {
  timestamp: string;
  validation_readiness: string;
  target_evaluation_domain: string;
  total_samples: number;
  total_reference_recordings: number;
  total_synthetic_recordings: number;
  total_hardware_recordings: number;
  eligible_samples: number;
  excluded_samples: number;
  eligible_recording_domains: string[];
  domain_breakdown: Record<string, number>;
  transducer_breakdown: Record<string, number>;
  exclusion_breakdown: Record<string, number>;
  label_distribution: Record<string, number>;
  independent_biological_labels: Record<string, number>;
  vocabulary_alignment: string;
  anomaly_threshold: number;
  anomaly_metrics?: {
    true_positives: number;
    false_positives: number;
    true_negatives: number;
    false_negatives: number;
    precision: number | null;
    recall: number | null;
    specificity: number | null;
    f1_score: number | null;
  } | null;
  grouped_by_zone: Record<string, any>;
  provenance_breakdown?: Record<string, number>;
  limitations_notice: string;
}


// ─── Alerts ───────────────────────────────────────────────────────────────────
export type AlertSeverity = 'info' | 'warning' | 'critical';
export type AlertCategory = 'environmental' | 'acoustic' | 'combined' | 'system';
export type AlarmState = 'active_unack' | 'active_ack' | 'cleared_unack' | 'cleared_ack';

export interface Alert {
  id: string;
  timestamp: string;
  zone_id: string;
  device_id?: string;
  severity: AlertSeverity;
  category: AlertCategory;
  title: string;
  message: string;
  triggered_by: string[];
  acknowledged: boolean;
  acknowledged_at?: string;
  acknowledged_by?: string;
  inspection_notes?: string;
  cleared: boolean;
  cleared_at?: string;
  cleared_by?: string;
  clear_notes?: string;
  alarm_state?: AlarmState;
  source: DataSource;
}

// ─── Home Assistant-Style Automation Execution Trace ──────────────────────────
export interface TraceStep {
  step_id: string;
  step_type: 'trigger' | 'condition' | 'action';
  name: string;
  status: 'passed' | 'failed' | 'executed';
  timestamp: string;
  details: Record<string, any>;
}

export interface ExecutionTrace {
  alert_id: string;
  triggered_at: string;
  zone_id: string;
  device_id?: string;
  rule_id: string;
  summary: string;
  steps: TraceStep[];
}

// ─── InfluxDB-Style Aggregated Telemetry ──────────────────────────────────────
export interface AggregatedBucket {
  bucket_start: string;
  bucket_end: string;
  point_count: number;
  avg_co2: number | null;
  min_co2: number | null;
  max_co2: number | null;
  avg_temp: number | null;
  avg_rh: number | null;
  is_gap: boolean;
}

export interface AggregatedTelemetryResponse {
  zone_id: string | null;
  bucket_minutes: number;
  range_hours: number;
  total_points: number;
  gap_count: number;
  buckets: AggregatedBucket[];
}

// ─── Inspection Records ───────────────────────────────────────────────────────
export interface InspectionRecord {
  id: string;
  alert_id: string;
  zone_id: string;
  inspector: string;
  timestamp: string;
  findings: string;
  action_taken: string;
  follow_up_required: boolean;
}

// ─── Demo Scenario ────────────────────────────────────────────────────────────
export type DemoScenario =
  | 'healthy_storage'
  | 'rising_environmental_risk'
  | 'experimental_acoustic_event'
  | 'combined_warning'
  | 'return_to_normal';

export interface ScenarioInfo {
  id: DemoScenario;
  label: string;
  description: string;
  icon: string;
}
