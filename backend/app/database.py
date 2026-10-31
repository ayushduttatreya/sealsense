"""
Async SQLite setup via aiosqlite.
"""
from contextlib import asynccontextmanager
import aiosqlite
import os

DB_PATH = os.environ.get("SEALSENSE_DB", "sealsense.db")

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
    rh_valid INTEGER NOT NULL DEFAULT 1
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
        ]
        for table, col, col_def in migrations:
            try:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
            except Exception:
                # Column already exists
                pass

        await db.commit()

