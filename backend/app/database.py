"""
Async SQLite setup via aiosqlite.
"""
from contextlib import asynccontextmanager
import aiosqlite
import os

DEFAULT_DB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "sealsense.db")
)
DB_PATH = os.environ.get("SEALSENSE_DB", DEFAULT_DB_PATH)

CREATE_READINGS = """
CREATE TABLE IF NOT EXISTS environmental_readings (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    zone_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'REAL',
    co2_ppm REAL,
    temperature_c REAL,
    relative_humidity_pct REAL,
    co2_valid INTEGER NOT NULL DEFAULT 1,
    temp_valid INTEGER NOT NULL DEFAULT 1,
    rh_valid INTEGER NOT NULL DEFAULT 1,
    audio_rms REAL,
    audio_peak INTEGER,
    audio_rms_dbfs REAL,
    audio_peak_dbfs REAL,
    audio_valid INTEGER NOT NULL DEFAULT 1,
    transport TEXT NOT NULL DEFAULT 'wifi',
    firmware_version TEXT
)
"""

CREATE_EVENTS = """
CREATE TABLE IF NOT EXISTS acoustic_events (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    zone_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'MODEL_EXPERIMENT',
    audio_sample_ref TEXT,
    prediction TEXT NOT NULL DEFAULT 'uncertain',
    model_version TEXT NOT NULL,
    score REAL,
    score_semantics TEXT NOT NULL,
    confidence_band TEXT NOT NULL DEFAULT 'uncertain',
    validation_status TEXT NOT NULL DEFAULT 'unvalidated',
    inference_status TEXT NOT NULL DEFAULT 'unavailable',
    inference_duration_ms INTEGER,
    notes TEXT
)
"""

CREATE_ALERTS = """
CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    zone_id TEXT NOT NULL,
    device_id TEXT,
    severity TEXT NOT NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    triggered_by TEXT NOT NULL DEFAULT '[]',
    acknowledged INTEGER NOT NULL DEFAULT 0,
    acknowledged_at TEXT,
    acknowledged_by TEXT,
    inspection_notes TEXT,
    cleared INTEGER NOT NULL DEFAULT 0,
    cleared_at TEXT,
    cleared_by TEXT,
    clear_notes TEXT,
    source TEXT NOT NULL DEFAULT 'SIMULATED'
)
"""

CREATE_SAMPLES = """
CREATE TABLE IF NOT EXISTS retained_audio_samples (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    stored_filename TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    sha256_hash TEXT NOT NULL,
    duration_sec REAL NOT NULL,
    sample_rate INTEGER NOT NULL,
    channels INTEGER NOT NULL,
    format TEXT NOT NULL DEFAULT 'WAV',
    timestamp TEXT NOT NULL,
    recording_timestamp TEXT,
    zone_id TEXT NOT NULL DEFAULT 'zone-a',
    device_id TEXT NOT NULL DEFAULT 'esp32-zone-a-01',
    input_source TEXT NOT NULL DEFAULT 'user_upload',
    is_synthetic INTEGER NOT NULL DEFAULT 0,
    model_id TEXT,
    model_version TEXT,
    prediction TEXT,
    score REAL,
    confidence_band TEXT,
    top_predictions TEXT,
    waveform_preview TEXT,
    spectrogram_peaks TEXT,
    review_status TEXT NOT NULL DEFAULT 'UNREVIEWED',
    ground_truth_label TEXT NOT NULL DEFAULT 'UNREVIEWED',
    verification_method TEXT DEFAULT 'unverified',
    reviewer TEXT,
    reviewed_at TEXT,
    evidence_notes TEXT,
    dataset_name TEXT,
    source_species TEXT,
    source_citation TEXT,
    source_url TEXT,
    transducer_type TEXT,
    source_category TEXT,
    recording_domain TEXT NOT NULL DEFAULT 'unknown',
    signal_analysis TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_retained_audio_hash ON retained_audio_samples(sha256_hash);
CREATE INDEX IF NOT EXISTS idx_retained_audio_label ON retained_audio_samples(ground_truth_label);
CREATE INDEX IF NOT EXISTS idx_retained_audio_synthetic ON retained_audio_samples(is_synthetic);
CREATE INDEX IF NOT EXISTS idx_retained_audio_source ON retained_audio_samples(input_source);
"""


@asynccontextmanager
async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_READINGS)
        await db.execute(CREATE_EVENTS)
        await db.execute(CREATE_ALERTS)
        await db.executescript(CREATE_SAMPLES)
        
        # Safe migrations for existing SQLite database files
        migrations = [
            ("alerts", "cleared", "INTEGER NOT NULL DEFAULT 0"),
            ("alerts", "cleared_at", "TEXT"),
            ("alerts", "cleared_by", "TEXT"),
            ("alerts", "clear_notes", "TEXT"),
            ("acoustic_events", "validation_notes", "TEXT"),
            ("acoustic_events", "validated_at", "TEXT"),
            ("acoustic_events", "validated_by", "TEXT"),
            ("acoustic_events", "review_status", "TEXT NOT NULL DEFAULT 'unreviewed'"),
            ("acoustic_events", "event_tier", "TEXT NOT NULL DEFAULT 'detection'"),
            ("acoustic_events", "reviewed_at", "TEXT"),
            ("acoustic_events", "reviewed_by", "TEXT"),
            ("acoustic_events", "waveform_preview", "TEXT"),
            ("acoustic_events", "spectrogram_peaks", "TEXT"),
            ("retained_audio_samples", "dataset_name", "TEXT"),
            ("retained_audio_samples", "source_species", "TEXT"),
            ("retained_audio_samples", "source_citation", "TEXT"),
            ("retained_audio_samples", "source_url", "TEXT"),
            ("retained_audio_samples", "transducer_type", "TEXT"),
            ("retained_audio_samples", "source_category", "TEXT"),
            ("retained_audio_samples", "recording_domain", "TEXT NOT NULL DEFAULT 'unknown'"),
            ("retained_audio_samples", "signal_analysis", "TEXT"),
            ("environmental_readings", "audio_rms", "REAL"),
            ("environmental_readings", "audio_peak", "INTEGER"),
            ("environmental_readings", "audio_rms_dbfs", "REAL"),
            ("environmental_readings", "audio_peak_dbfs", "REAL"),
            ("environmental_readings", "audio_valid", "INTEGER NOT NULL DEFAULT 1"),
            ("environmental_readings", "transport", "TEXT NOT NULL DEFAULT 'wifi'"),
            ("environmental_readings", "firmware_version", "TEXT"),
        ]
        for table, col, col_def in migrations:
            try:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
            except Exception:
                # Column already exists
                pass

        try:
            await db.execute("CREATE INDEX IF NOT EXISTS idx_retained_audio_domain ON retained_audio_samples(recording_domain)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_readings_device_time ON environmental_readings(device_id, timestamp)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_readings_zone_time ON environmental_readings(zone_id, timestamp)")
        except Exception:
            pass

        await db.commit()

