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
  status: 'ok' | 'error' | 'unknown';
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

export interface AcousticInferenceResult {
  status: 'READY' | 'UNAVAILABLE' | 'EXPERIMENTAL' | 'ERROR';
  model_id: string;
  prediction: string;
  score: number | null;
  score_semantics: string;
  top_predictions: PredictionItem[];
  confidence_band: 'low' | 'medium' | 'high' | 'uncertain';
  inference_duration_ms?: number;
  audio_sample_rate: number;
  audio_duration_sec: number;
  waveform_preview?: number[];
  spectrogram_peaks?: { frequency_hz?: number; freq_hz?: number; magnitude_db?: number; db?: number }[];
  limitations: string;
  error?: string | null;
  reason?: string | null;
  input_source?: 'user_upload' | 'synthetic' | 'live_stream';
  filename?: string | null;
  original_sample_rate?: number | null;
  original_channels?: number | null;
  original_duration_sec?: number | null;
  window_mode?: 'exact' | 'padded' | 'truncated' | null;
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
