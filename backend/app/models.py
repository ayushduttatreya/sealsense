"""
Pydantic schemas and SQLite table definitions for SealSense backend.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Literal, List
from pydantic import BaseModel, Field, field_validator, model_validator
import uuid

DataSource = Literal["REAL", "SIMULATED", "MODEL_EXPERIMENT"]
InferenceStatus = Literal["complete", "running", "unavailable", "experimental", "error"]
ValidationStatus = Literal["unvalidated", "validated", "rejected"]
AlertSeverity = Literal["info", "warning", "critical"]
AlertCategory = Literal["environmental", "acoustic", "combined", "system"]
ZoneHealth = Literal["healthy", "warning", "critical", "unknown"]
SensorStatus = Literal["ok", "error", "unknown", "not_connected", "unavailable"]
ConfidenceBand = Literal["low", "medium", "high", "uncertain"]

AlarmState = Literal["active_unack", "active_ack", "cleared_unack", "cleared_ack"]

def new_id() -> str:
    return str(uuid.uuid4())[:8]

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Sensor Inventory ─────────────────────────────────────────────
class SensorInventory(BaseModel):
    type: Literal["SCD41", "INMP441", "BUZZER"]
    status: SensorStatus = "unknown"
    last_reading: Optional[str] = None


# ─── Device ───────────────────────────────────────────────────────
class Device(BaseModel):
    id: str
    name: str
    zone_id: str
    firmware_version: str
    last_seen: str
    connected: bool
    inactivity_timeout_sec: int = 300
    last_activity_time: Optional[str] = None
    is_active: bool = True
    sensors: List[SensorInventory] = []


# ─── Zone ─────────────────────────────────────────────────────────
class Zone(BaseModel):
    id: str
    name: str
    description: str
    device_ids: List[str] = []
    health: ZoneHealth = "unknown"


# ─── Environmental Reading ─────────────────────────────────────────
class EnvironmentalReading(BaseModel):
    id: str = Field(default_factory=new_id)
    timestamp: str = Field(default_factory=now_iso)
    zone_id: str
    device_id: str
    source: DataSource
    co2_ppm: Optional[float] = None
    temperature_c: Optional[float] = None
    # IMPORTANT: This is air relative humidity, NOT grain moisture content
    relative_humidity_pct: Optional[float] = None
    co2_valid: bool = True
    temp_valid: bool = True
    rh_valid: bool = True
    audio_rms: Optional[float] = None
    audio_peak: Optional[int] = None
    audio_rms_dbfs: Optional[float] = None
    audio_peak_dbfs: Optional[float] = None
    audio_valid: bool = True
    transport: Optional[str] = "wifi"
    firmware_version: Optional[str] = None

    @field_validator("co2_ppm")
    @classmethod
    def co2_range(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (0 <= v <= 40000):
            raise ValueError(f"co2_ppm {v} out of plausible range [0, 40000]")
        return v

    @field_validator("temperature_c")
    @classmethod
    def temp_range(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (-40 <= v <= 85):
            raise ValueError(f"temperature_c {v} out of plausible range [-40, 85]")
        return v

    @field_validator("relative_humidity_pct")
    @classmethod
    def rh_range(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (0 <= v <= 100):
            raise ValueError(f"relative_humidity_pct {v} out of range [0, 100]")
        return v


class TelemetryPayload(BaseModel):
    """POST /api/telemetry — firmware or serial bridge sends this."""
    device_id: str
    zone_id: str
    timestamp: str
    co2_ppm: Optional[float] = None
    temperature_c: Optional[float] = None
    relative_humidity_pct: Optional[float] = None
    co2_valid: bool = True
    temp_valid: bool = True
    rh_valid: bool = True
    audio_rms: Optional[float] = None
    audio_peak: Optional[int] = None
    audio_rms_dbfs: Optional[float] = None
    audio_peak_dbfs: Optional[float] = None
    audio_valid: bool = True
    transport: Optional[str] = "usb_serial"
    firmware_version: Optional[str] = None
    source: Optional[DataSource] = "REAL"


class LatestTelemetryResponse(BaseModel):
    reading: Optional[EnvironmentalReading] = None
    is_hardware: bool = False
    source: DataSource = "SIMULATED"
    transport: Optional[str] = None
    age_seconds: Optional[float] = None
    device_status: str = "offline"  # "online" | "stale" | "offline"


class TelemetryHistoryResponse(BaseModel):
    readings: list[EnvironmentalReading]
    count: int
    device_id: Optional[str] = None
    zone_id: Optional[str] = None
    time_range: str
    source: DataSource
    is_hardware: bool


# ─── Acoustic Event ────────────────────────────────────────────────
class AcousticEvent(BaseModel):
    id: str = Field(default_factory=new_id)
    timestamp: str = Field(default_factory=now_iso)
    zone_id: str
    device_id: str
    source: DataSource = "MODEL_EXPERIMENT"
    audio_sample_ref: Optional[str] = None
    prediction: str = "uncertain"
    model_version: str = "nocturne-v1-mini (EXPERIMENTAL)"
    score: Optional[float] = None
    score_semantics: str = (
        "Raw model output — not a calibrated infestation probability. "
        "Requires expert validation against labelled grain-insect recordings."
    )
    confidence_band: ConfidenceBand = "uncertain"
    validation_status: ValidationStatus = "unvalidated"
    inference_status: InferenceStatus = "unavailable"
    inference_duration_ms: Optional[int] = None
    validation_notes: Optional[str] = None
    validated_at: Optional[str] = None
    validated_by: Optional[str] = None
    waveform_preview: Optional[List[float]] = None
    spectrogram_peaks: Optional[List[dict]] = None
    review_status: Literal["unreviewed", "reviewed"] = "unreviewed"
    event_tier: Literal["alert", "detection"] = "detection"
    reviewed_at: Optional[str] = None
    reviewed_by: Optional[str] = None
    notes: Optional[str] = None


# ─── Alert ────────────────────────────────────────────────────────
class Alert(BaseModel):
    id: str = Field(default_factory=new_id)
    timestamp: str = Field(default_factory=now_iso)
    zone_id: str
    device_id: Optional[str] = None
    severity: AlertSeverity
    category: AlertCategory
    title: str
    message: str
    triggered_by: List[str] = []
    acknowledged: bool = False
    acknowledged_at: Optional[str] = None
    acknowledged_by: Optional[str] = None
    inspection_notes: Optional[str] = None
    cleared: bool = False
    cleared_at: Optional[str] = None
    cleared_by: Optional[str] = None
    clear_notes: Optional[str] = None
    alarm_state: AlarmState = "active_unack"
    source: DataSource = "SIMULATED"

    @model_validator(mode="after")
    def compute_alarm_state(self) -> "Alert":
        if not self.cleared and not self.acknowledged:
            self.alarm_state = "active_unack"
        elif not self.cleared and self.acknowledged:
            self.alarm_state = "active_ack"
        elif self.cleared and not self.acknowledged:
            self.alarm_state = "cleared_unack"
        else:
            self.alarm_state = "cleared_ack"
        return self


class AcknowledgeRequest(BaseModel):
    notes: str = ""
    acknowledged_by: str = "Operator"


class ClearAlertRequest(BaseModel):
    notes: str = ""
    cleared_by: str = "Operator"


class ValidateEventRequest(BaseModel):
    status: Optional[ValidationStatus] = None
    validation_status: Optional[ValidationStatus] = None
    notes: str = ""
    validation_notes: Optional[str] = None
    validator: str = "Inspector"
    validated_by: Optional[str] = None

    def get_status(self) -> ValidationStatus:
        return self.status or self.validation_status or "validated"

    def get_notes(self) -> str:
        return self.validation_notes or self.notes or ""

    def get_validator(self) -> str:
        return self.validated_by or self.validator or "Inspector"


# ─── Demo Scenario ─────────────────────────────────────────────────
DemoScenario = Literal[
    "healthy_storage",
    "rising_environmental_risk",
    "experimental_acoustic_event",
    "combined_warning",
    "return_to_normal",
]


class ScenarioRequest(BaseModel):
    scenario: DemoScenario


# ─── Home Assistant-Style Automation Execution Trace ────────────────
class TraceStep(BaseModel):
    step_id: str
    step_type: Literal["trigger", "condition", "action"]
    name: str
    status: Literal["passed", "failed", "executed"]
    timestamp: str
    details: dict = {}


class ExecutionTrace(BaseModel):
    alert_id: str
    triggered_at: str
    zone_id: str
    device_id: Optional[str] = None
    rule_id: str
    summary: str
    steps: List[TraceStep] = []


# ─── Frigate-Style Audio Event Batch Review ────────────────────────
class BatchReviewRequest(BaseModel):
    event_ids: List[str]
    action: Literal["reviewed", "validated", "rejected"] = "reviewed"
    reviewer: str = "Operator"
    notes: str = ""


# ─── InfluxDB-Inspired Downsampling & Time-Bucket Aggregation ──────
class AggregatedBucket(BaseModel):
    bucket_start: str
    bucket_end: str
    point_count: int
    avg_co2: Optional[float] = None
    min_co2: Optional[float] = None
    max_co2: Optional[float] = None
    avg_temp: Optional[float] = None
    avg_rh: Optional[float] = None
    is_gap: bool = False


class AggregatedTelemetryResponse(BaseModel):
    zone_id: Optional[str] = None
    bucket_minutes: int
    range_hours: int
    total_points: int
    gap_count: int
    buckets: List[AggregatedBucket]


# ─── Retained Audio Samples & Ground-Truth Annotation ───────────────
RecordingDomain = Literal[
    "airborne_microphone",
    "accelerometer",
    "piezoelectric",
    "pvdf",
    "ultrasonic_transducer",
    "synthetic_simulation",
    "unknown",
]

GroundTruthLabel = Literal[
    "UNREVIEWED",
    "REVIEWED",
    "TARGET_PEST_OBSERVED",
    "NO_TARGET_PEST_OBSERVED",
    "INCONCLUSIVE",
]

VerificationMethod = Literal[
    "physical_trap_inspection",
    "grain_sieve",
    "visual_sample",
    "acoustic_expert_review",
    "laboratory_reared_culture",
    "unverified",
]


class RetainedAudioSample(BaseModel):
    id: str
    filename: str
    stored_filename: str
    file_size_bytes: int
    sha256_hash: str
    duration_sec: float
    sample_rate: int
    channels: int
    format: str = "WAV"
    timestamp: str
    recording_timestamp: Optional[str] = None
    zone_id: str = "zone-a"
    device_id: str = "esp32-zone-a-01"
    input_source: Literal["user_upload", "hardware_recording", "synthetic", "public_reference"] = "user_upload"
    is_synthetic: bool = False
    recording_domain: RecordingDomain = "unknown"
    model_id: Optional[str] = "stratus-labs/nocturne-v1-mini"
    model_version: Optional[str] = None
    prediction: Optional[str] = None
    score: Optional[float] = None
    confidence_band: Optional[str] = None
    top_predictions: List[dict] = []
    waveform_preview: Optional[List[float]] = None
    spectrogram_peaks: Optional[List[dict]] = None
    signal_analysis: Optional[dict] = None
    review_status: Literal["UNREVIEWED", "REVIEWED"] = "UNREVIEWED"
    ground_truth_label: GroundTruthLabel = "UNREVIEWED"
    verification_method: VerificationMethod = "unverified"
    reviewer: Optional[str] = None
    reviewed_at: Optional[str] = None
    evidence_notes: Optional[str] = None
    dataset_name: Optional[str] = None
    source_species: Optional[str] = None
    source_citation: Optional[str] = None
    source_url: Optional[str] = None
    transducer_type: Optional[str] = None
    source_category: Optional[str] = None
    created_at: str


class AnnotationUpdateRequest(BaseModel):
    ground_truth_label: GroundTruthLabel
    verification_method: Optional[VerificationMethod] = "unverified"
    reviewer: Optional[str] = "Inspector"
    evidence_notes: Optional[str] = ""
    review_status: Optional[Literal["UNREVIEWED", "REVIEWED"]] = None


# ─── Public Reference Dataset Schemas ──────────────────────────────
class ReferenceAudioCatalogItem(BaseModel):
    id: str
    filename: str
    species: str
    common_name: str
    life_stage: str
    substrate: str
    transducer_type: str
    recording_domain: RecordingDomain = "unknown"
    frequency_range: Optional[str] = None
    sample_width_bits: Optional[int] = 16
    sample_width_bytes: Optional[int] = 2
    laboratory_setup: Optional[str] = None
    category: str
    description: str
    duration_sec: float
    sample_rate: int
    channels: int
    dataset_name: str
    citation: str
    source_url: str
    sha256_hash: Optional[str] = None
    is_locally_available: bool = False
    file_size_bytes: Optional[int] = None
    notes: str


class ReferenceImportRequest(BaseModel):
    catalog_id: str
    retain_sample: bool = True
    zone_id: str = "zone-a"
    device_id: str = "esp32-zone-a-01"
    notes: Optional[str] = None


# ─── Synthetic Bioacoustic Simulation Schemas ─────────────────────
class SyntheticImpulseRequest(BaseModel):
    impulse_rate: float = 12.0
    amplitude: float = 0.6
    noise_level: float = 0.04
    duration_sec: float = 10.0
    seed: int = 42
    run_inference: bool = True
    retain_sample: bool = False
    zone_id: str = "zone-a"
    device_id: str = "esp32-zone-a-01"


# ─── Offline Dataset Evaluation Report ─────────────────────────────
class EvaluationConfusionMatrix(BaseModel):
    true_positives: int = 0
    false_positives: int = 0
    true_negatives: int = 0
    false_negatives: int = 0
    precision: Optional[float] = None
    recall: Optional[float] = None
    specificity: Optional[float] = None
    f1_score: Optional[float] = None


class DatasetEvaluationReport(BaseModel):
    timestamp: str
    validation_readiness: str = "INSUFFICIENT VALIDATION DATA"
    target_evaluation_domain: str = "airborne_microphone"
    total_samples: int
    total_reference_recordings: int = 0
    total_synthetic_recordings: int = 0
    total_hardware_recordings: int = 0
    eligible_samples: int
    excluded_samples: int
    eligible_recording_domains: List[str] = ["airborne_microphone"]
    domain_breakdown: dict[str, int] = {}
    transducer_breakdown: dict[str, int] = {}
    exclusion_breakdown: dict[str, int]
    label_distribution: dict[str, int]
    independent_biological_labels: dict[str, int] = {}
    vocabulary_alignment: str
    anomaly_threshold: float = 0.05
    anomaly_metrics: Optional[EvaluationConfusionMatrix] = None
    grouped_by_zone: dict[str, dict] = {}
    provenance_breakdown: dict[str, int] = {}
    limitations_notice: str


