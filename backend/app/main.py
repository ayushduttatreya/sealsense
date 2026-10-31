"""
SealSense FastAPI Backend
Run with: uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations
import csv
import io
import json
import logging
import os
import wave
from contextlib import asynccontextmanager
from typing import Optional, List, Literal

from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form, status, Response
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .database import init_db, get_db, CREATE_SAMPLES
from .models import (
    EnvironmentalReading, AcousticEvent, Alert, Device, Zone,
    TelemetryPayload, AcknowledgeRequest, ClearAlertRequest,
    ValidateEventRequest, ScenarioRequest,
    TraceStep, ExecutionTrace, BatchReviewRequest,
    AggregatedBucket, AggregatedTelemetryResponse,
    RetainedAudioSample, AnnotationUpdateRequest, DatasetEvaluationReport,
    GroundTruthLabel, ReferenceAudioCatalogItem, ReferenceImportRequest,
    SyntheticImpulseRequest, LatestTelemetryResponse, TelemetryHistoryResponse,
)
from .audio_storage import (
    compute_sha256, validate_wav_bytes, generate_sample_id,
    save_audio_file, get_audio_file_path, delete_audio_file
)
from .evaluation import evaluate_dataset_samples
from .reference_dataset import (
    list_reference_catalog, get_catalog_item, get_reference_file_path
)
from .synthetic_generator import (
    generate_synthetic_impulse_wav, generate_synthetic_chirp_wav
)
from .signal_analysis import analyze_signal, analyze_wav_bytes
from .demo_data import get_demo_data, DEMO_DEVICES, BASE_ZONES
from .alert_rules import evaluate_environmental
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("sealsense")

VERSION = "0.2.0"

# ─── Current scenario state (in-memory; not persisted across restarts) ────────
_current_scenario: str = "healthy_storage"
_demo_alert_overrides: dict[str, dict] = {}
_demo_event_overrides: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    log.info("SealSense backend started — DB initialized")
    yield
    log.info("SealSense backend shutting down")


app = FastAPI(title="SealSense API", version=VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health ───────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "version": VERSION}


# ─── Devices ──────────────────────────────────────────────────────
@app.get("/api/devices", response_model=list[Device])
async def list_devices():
    """
    Returns device inventory with dynamic ThingsBoard-style inactivity checks.
    """
    now = datetime.now(timezone.utc)
    evaluated_devices = []

    for d in DEMO_DEVICES:
        dev_copy = d.model_copy()
        try:
            ls_time = datetime.fromisoformat(d.last_seen.replace("Z", "+00:00"))
            inactive = (now - ls_time).total_seconds() > d.inactivity_timeout_sec
            dev_copy.connected = not inactive and d.connected
            dev_copy.is_active = not inactive and d.connected
        except Exception:
            pass
        evaluated_devices.append(dev_copy)

    return evaluated_devices


# ─── Zones ────────────────────────────────────────────────────────
@app.get("/api/zones", response_model=list[Zone])
async def list_zones():
    _, _, _, zones = get_demo_data(_current_scenario)
    return zones


# ─── Environmental Readings ────────────────────────────────────────
@app.get("/api/readings", response_model=list[EnvironmentalReading])
async def list_readings(
    zone_id: Optional[str] = None,
    limit: int = 100,
    source: Optional[str] = None,
):
    limit_val = limit if isinstance(limit, int) else 100
    zone_id_val = zone_id if isinstance(zone_id, str) else None
    source_val = source if isinstance(source, str) else None

    async with get_db() as db:
        query = "SELECT * FROM environmental_readings"
        params: list = []
        conditions = []
        if zone_id_val:
            conditions.append("zone_id = ?")
            params.append(zone_id_val)
        if source_val:
            conditions.append("source = ?")
            params.append(source_val)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit_val)
        async with db.execute(query, params) as cur:
            rows = await cur.fetchall()

    if rows:
        return [EnvironmentalReading(**dict(r)) for r in rows]

    # Fall back to demo data
    readings, _, _, _ = get_demo_data(_current_scenario)
    if zone_id_val:
        readings = [r for r in readings if r.zone_id == zone_id_val]
    return readings[:limit_val]


def _row_to_acoustic_event(r) -> AcousticEvent:
    d = dict(r)
    if d.get("waveform_preview"):
        if isinstance(d["waveform_preview"], str):
            try:
                d["waveform_preview"] = json.loads(d["waveform_preview"])
            except Exception:
                pass
    if not d.get("waveform_preview"):
        d["waveform_preview"] = [0.08, 0.12, 0.35, 0.65, 0.78, 0.45, 0.22, 0.15, 0.48, 0.82, 0.61, 0.28, 0.18, 0.32, 0.14, 0.09]

    if d.get("spectrogram_peaks"):
        if isinstance(d["spectrogram_peaks"], str):
            try:
                d["spectrogram_peaks"] = json.loads(d["spectrogram_peaks"])
            except Exception:
                pass
    if not d.get("spectrogram_peaks"):
        d["spectrogram_peaks"] = [{"freq_hz": 4200.0, "db": -24.5}, {"freq_hz": 6800.0, "db": -31.2}]

    return AcousticEvent(**d)


# ─── Acoustic Events ──────────────────────────────────────────────
@app.get("/api/events", response_model=list[AcousticEvent])
async def list_events(
    zone_id: Optional[str] = None,
    review_status: Optional[str] = None,
    event_tier: Optional[str] = None,
    limit: int = 50,
):
    limit_val = limit if isinstance(limit, int) else 50
    zone_id_val = zone_id if isinstance(zone_id, str) else None
    review_status_val = review_status if isinstance(review_status, str) else None
    event_tier_val = event_tier if isinstance(event_tier, str) else None

    if _current_scenario != "healthy_storage":
        _, events, _, _ = get_demo_data(_current_scenario)
        result_events = []
        for e in events:
            if e.id in _demo_event_overrides:
                d = e.model_dump()
                d.update(_demo_event_overrides[e.id])
                e = AcousticEvent(**d)
            if zone_id_val and e.zone_id != zone_id_val:
                continue
            if review_status_val and e.review_status != review_status_val:
                continue
            if event_tier_val and e.event_tier != event_tier_val:
                continue
            result_events.append(e)
        return result_events[:limit_val]

    async with get_db() as db:
        query = "SELECT * FROM acoustic_events"
        params: list = []
        conditions = []
        if zone_id_val:
            conditions.append("zone_id = ?")
            params.append(zone_id_val)
        if review_status_val:
            conditions.append("review_status = ?")
            params.append(review_status_val)
        if event_tier_val:
            conditions.append("event_tier = ?")
            params.append(event_tier_val)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit_val)
        async with db.execute(query, params) as cur:
            rows = await cur.fetchall()

    if rows:
        return [_row_to_acoustic_event(r) for r in rows]

    _, events, _, _ = get_demo_data(_current_scenario)
    result_events = []
    for e in events:
        if e.id in _demo_event_overrides:
            d = e.model_dump()
            d.update(_demo_event_overrides[e.id])
            e = AcousticEvent(**d)
        if zone_id_val and e.zone_id != zone_id_val:
            continue
        if review_status_val and e.review_status != review_status_val:
            continue
        if event_tier_val and e.event_tier != event_tier_val:
            continue
        result_events.append(e)
    return result_events[:limit_val]


# ─── Alerts ───────────────────────────────────────────────────────
@app.get("/api/alerts", response_model=list[Alert])
async def list_alerts(
    category: Optional[str] = None,
    severity: Optional[str] = None,
    alarm_state: Optional[str] = None,
    limit: int = 100,
):
    limit_val = limit if isinstance(limit, int) else 100
    cat_val = category if isinstance(category, str) else None
    sev_val = severity if isinstance(severity, str) else None
    state_val = alarm_state if isinstance(alarm_state, str) else None

    async with get_db() as db:
        query = "SELECT * FROM alerts"
        params: list = []
        conditions = []
        if cat_val:
            conditions.append("category = ?")
            params.append(cat_val)
        if sev_val:
            conditions.append("severity = ?")
            params.append(sev_val)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit_val)
        async with db.execute(query, params) as cur:
            rows = await cur.fetchall()

    if rows:
        alerts = []
        for r in rows:
            d = dict(r)
            d["triggered_by"] = json.loads(d.get("triggered_by", "[]"))
            d["acknowledged"] = bool(d.get("acknowledged", 0))
            d["cleared"] = bool(d.get("cleared", 0))
            alert = Alert(**d)
            if alarm_state and alert.alarm_state != alarm_state:
                continue
            alerts.append(alert)
        return alerts[:limit_val]

    _, _, alerts, _ = get_demo_data(_current_scenario)
    result_alerts = []
    for a in alerts:
        if a.id in _demo_alert_overrides:
            d = a.model_dump()
            d.update(_demo_alert_overrides[a.id])
            a = Alert(**d)
        if cat_val and a.category != cat_val:
            continue
        if sev_val and a.severity != sev_val:
            continue
        if state_val and a.alarm_state != state_val:
            continue
        result_alerts.append(a)
    return result_alerts[:limit_val]


# ─── Telemetry Ingest & Observability ─────────────────────────────
@app.post("/api/telemetry", response_model=EnvironmentalReading)
async def ingest_telemetry(payload: TelemetryPayload):
    """Receives real telemetry from ESP32 firmware via HTTP POST or USB Serial Bridge."""
    reading = EnvironmentalReading(
        zone_id=payload.zone_id,
        device_id=payload.device_id,
        timestamp=payload.timestamp or datetime.now(timezone.utc).isoformat(),
        source=payload.source or "REAL",
        co2_ppm=payload.co2_ppm,
        temperature_c=payload.temperature_c,
        relative_humidity_pct=payload.relative_humidity_pct,
        co2_valid=payload.co2_valid,
        temp_valid=payload.temp_valid,
        rh_valid=payload.rh_valid,
        audio_rms=payload.audio_rms,
        audio_peak=payload.audio_peak,
        audio_rms_dbfs=payload.audio_rms_dbfs,
        audio_peak_dbfs=payload.audio_peak_dbfs,
        audio_valid=payload.audio_valid,
        transport=payload.transport or "usb_serial",
        firmware_version=payload.firmware_version,
    )
    async with get_db() as db:
        await db.execute(
            """INSERT INTO environmental_readings
               (id, timestamp, zone_id, device_id, source, co2_ppm,
                temperature_c, relative_humidity_pct, co2_valid, temp_valid, rh_valid,
                audio_rms, audio_peak, audio_rms_dbfs, audio_peak_dbfs, audio_valid,
                transport, firmware_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                reading.id, reading.timestamp, reading.zone_id, reading.device_id,
                reading.source, reading.co2_ppm, reading.temperature_c,
                reading.relative_humidity_pct,
                int(reading.co2_valid), int(reading.temp_valid), int(reading.rh_valid),
                reading.audio_rms, reading.audio_peak, reading.audio_rms_dbfs,
                reading.audio_peak_dbfs, int(reading.audio_valid),
                reading.transport, reading.firmware_version,
            ),
        )

        # Update in-memory device registry so the dashboard immediately sees online hardware
        now_iso = datetime.now(timezone.utc).isoformat()
        for d in DEMO_DEVICES:
            if d.id == payload.device_id:
                d.last_seen = now_iso
                d.last_activity_time = now_iso
                d.connected = True
                d.is_active = True
                if payload.firmware_version:
                    d.firmware_version = payload.firmware_version
                for s in d.sensors:
                    if s.type == "SCD41":
                        s.status = "ok" if payload.co2_valid and payload.co2_ppm is not None else "error"
                        s.last_reading = now_iso
                    elif s.type == "INMP441":
                        s.status = "ok" if payload.audio_valid else "unavailable"
                        s.last_reading = now_iso
                    elif s.type == "BUZZER":
                        s.status = "ok"

        # Retrieve recent readings for rule evaluation
        async with db.execute(
            "SELECT * FROM environmental_readings WHERE zone_id = ? ORDER BY timestamp DESC LIMIT 5",
            (reading.zone_id,)
        ) as cur:
            recent_rows = await cur.fetchall()
            recent_readings = [EnvironmentalReading(**dict(r)) for r in reversed(recent_rows)]

        new_alerts = evaluate_environmental(recent_readings, reading.zone_id, reading.device_id)
        for alrt in new_alerts:
            # ThingsBoard de-duplication: update existing active alert if already present
            async with db.execute(
                "SELECT id, severity FROM alerts WHERE zone_id = ? AND category = ? AND cleared = 0 LIMIT 1",
                (alrt.zone_id, alrt.category)
            ) as cur:
                existing = await cur.fetchone()

            if existing:
                await db.execute(
                    "UPDATE alerts SET timestamp = ?, message = ?, triggered_by = ? WHERE id = ?",
                    (alrt.timestamp, alrt.message, json.dumps(alrt.triggered_by), existing["id"])
                )
            else:
                await db.execute(
                    """INSERT INTO alerts
                       (id, timestamp, zone_id, device_id, severity, category, title, message,
                        triggered_by, acknowledged, cleared, source)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 'REAL')""",
                    (alrt.id, alrt.timestamp, alrt.zone_id, alrt.device_id, alrt.severity,
                     alrt.category, alrt.title, alrt.message, json.dumps(alrt.triggered_by))
                )

        await db.commit()

    log.info(f"Telemetry ingested from {payload.device_id} ({reading.transport}): CO2={payload.co2_ppm} ppm, Temp={payload.temperature_c}°C, Air_RH={payload.relative_humidity_pct}%, RMS={payload.audio_rms_dbfs} dBFS")
    return reading


@app.get("/api/telemetry/latest", response_model=LatestTelemetryResponse)
async def get_latest_telemetry(
    device_id: Optional[str] = None,
    zone_id: Optional[str] = None,
):
    """Returns the most recent telemetry packet from real hardware or simulated demo."""
    query = "SELECT * FROM environmental_readings"
    params = []
    conds = []
    if device_id:
        conds.append("device_id = ?")
        params.append(device_id)
    if zone_id:
        conds.append("zone_id = ?")
        params.append(zone_id)
    if conds:
        query += " WHERE " + " AND ".join(conds)
    query += " ORDER BY timestamp DESC LIMIT 1"

    async with get_db() as db:
        async with db.execute(query, params) as cur:
            row = await cur.fetchone()

    now = datetime.now(timezone.utc)
    if row:
        reading = EnvironmentalReading(**dict(row))
        try:
            ts = datetime.fromisoformat(reading.timestamp.replace("Z", "+00:00"))
            age = (now - ts).total_seconds()
        except Exception:
            age = 0.0

        status_str = "online" if age < 15 else ("stale" if age < 60 else "offline")
        return LatestTelemetryResponse(
            reading=reading,
            is_hardware=reading.source == "REAL",
            source=reading.source,
            transport=reading.transport,
            age_seconds=round(age, 1),
            device_status=status_str,
        )

    # Fallback to latest demo reading
    demo_readings, _, _, _ = get_demo_data(_current_scenario)
    if zone_id:
        demo_readings = [r for r in demo_readings if r.zone_id == zone_id]
    if demo_readings:
        latest_demo = demo_readings[-1]
        return LatestTelemetryResponse(
            reading=latest_demo,
            is_hardware=False,
            source="SIMULATED",
            transport="demo_generator",
            age_seconds=5.0,
            device_status="online",
        )

    return LatestTelemetryResponse(
        reading=None,
        is_hardware=False,
        source="SIMULATED",
        transport=None,
        age_seconds=None,
        device_status="offline",
    )


@app.get("/api/telemetry/history", response_model=TelemetryHistoryResponse)
async def get_telemetry_history(
    device_id: Optional[str] = None,
    zone_id: Optional[str] = None,
    time_range: str = Query("15m", description="Time range: 5m, 15m, 1h, 6h, 24h, all"),
    limit: int = Query(300, description="Max readings to return"),
):
    """
    Returns time-filtered, chronological telemetry readings for high-density Grafana time-series graphs.
    """
    now = datetime.now(timezone.utc)
    delta_map = {
        "5m": timedelta(minutes=5),
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "6h": timedelta(hours=6),
        "24h": timedelta(hours=24),
    }

    start_iso = None
    if time_range in delta_map:
        start_iso = (now - delta_map[time_range]).isoformat()

    query = "SELECT * FROM environmental_readings"
    params = []
    conds = []

    if start_iso:
        conds.append("timestamp >= ?")
        params.append(start_iso)
    if device_id:
        conds.append("device_id = ?")
        params.append(device_id)
    if zone_id:
        conds.append("zone_id = ?")
        params.append(zone_id)

    if conds:
        query += " WHERE " + " AND ".join(conds)

    query += " ORDER BY timestamp ASC LIMIT ?"
    params.append(limit)

    async with get_db() as db:
        async with db.execute(query, params) as cur:
            rows = await cur.fetchall()

    if rows and len(rows) > 0:
        readings = [EnvironmentalReading(**dict(r)) for r in rows]
        is_hw = any(r.source == "REAL" for r in readings)
        return TelemetryHistoryResponse(
            readings=readings,
            count=len(readings),
            device_id=device_id,
            zone_id=zone_id,
            time_range=time_range,
            source="REAL" if is_hw else "SIMULATED",
            is_hardware=is_hw,
        )

    # Fall back smoothly to demo readings for that time window
    demo_readings, _, _, _ = get_demo_data(_current_scenario)
    if zone_id:
        demo_readings = [r for r in demo_readings if r.zone_id == zone_id]
    if start_iso:
        demo_readings = [r for r in demo_readings if r.timestamp >= start_iso]

    # If demo readings are too sparse for 5m/15m, generate an interpolated dense series
    if len(demo_readings) < 5 and time_range in ("5m", "15m"):
        base_reading = demo_readings[-1] if demo_readings else None
        base_co2 = base_reading.co2_ppm if base_reading and base_reading.co2_ppm else 1826.0
        base_temp = base_reading.temperature_c if base_reading and base_reading.temperature_c else 25.4
        base_rh = base_reading.relative_humidity_pct if base_reading and base_reading.relative_humidity_pct else 68.1
        
        step_sec = 10 if time_range == "5m" else 30
        points = 30
        sim_readings = []
        for i in range(points):
            t = now - timedelta(seconds=(points - 1 - i) * step_sec)
            sim_readings.append(EnvironmentalReading(
                id=f"sim-hist-{i}",
                timestamp=t.isoformat(),
                zone_id=zone_id or "zone-a",
                device_id=device_id or "esp32-zone-a-01",
                source="SIMULATED",
                co2_ppm=round(base_co2 + (i % 5 - 2) * 3.5, 1),
                temperature_c=round(base_temp + (i % 3 - 1) * 0.1, 1),
                relative_humidity_pct=round(base_rh + (i % 4 - 2) * 0.15, 1),
                co2_valid=True,
                temp_valid=True,
                rh_valid=True,
                audio_rms=142000,
                audio_peak=265000,
                audio_rms_dbfs=round(-35.4 + (i % 4 - 2) * 0.8, 1),
                audio_peak_dbfs=round(-30.0 + (i % 3 - 1) * 1.2, 1),
                audio_valid=True,
                transport="demo_generator",
                firmware_version="2.0.0-PROTOTYPE",
            ))
        return TelemetryHistoryResponse(
            readings=sim_readings,
            count=len(sim_readings),
            device_id=device_id,
            zone_id=zone_id,
            time_range=time_range,
            source="SIMULATED",
            is_hardware=False,
        )

    return TelemetryHistoryResponse(
        readings=demo_readings,
        count=len(demo_readings),
        device_id=device_id,
        zone_id=zone_id,
        time_range=time_range,
        source="SIMULATED",
        is_hardware=False,
    )


# ─── Alert Acknowledge ────────────────────────────────────────────
@app.post("/api/alerts/{alert_id}/acknowledge", response_model=Alert)
async def acknowledge_alert(alert_id: str, req: AcknowledgeRequest):
    now = datetime.now(timezone.utc).isoformat()

    async with get_db() as db:
        async with db.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)) as cur:
            row = await cur.fetchone()

        if row:
            await db.execute(
                """UPDATE alerts SET acknowledged=1, acknowledged_at=?, acknowledged_by=?, inspection_notes=?
                   WHERE id=?""",
                (now, req.acknowledged_by, req.notes, alert_id),
            )
            await db.commit()
            async with db.execute("SELECT * FROM alerts WHERE id=?", (alert_id,)) as cur:
                row = await cur.fetchone()
            d = dict(row)
            d["triggered_by"] = json.loads(d.get("triggered_by", "[]"))
            d["acknowledged"] = bool(d.get("acknowledged", 0))
            d["cleared"] = bool(d.get("cleared", 0))
            return Alert(**d)

    # Demo alert (not in DB) — return acknowledged copy
    _, _, alerts, _ = get_demo_data(_current_scenario)
    for a in alerts:
        if a.id == alert_id:
            d = a.model_dump()
            d.update(_demo_alert_overrides.get(alert_id, {}))
            d.update({
                "acknowledged": True,
                "acknowledged_at": now,
                "acknowledged_by": req.acknowledged_by,
                "inspection_notes": req.notes,
            })
            _demo_alert_overrides[alert_id] = d
            return Alert(**d)
    raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")


# ─── Alert Clear (ThingsBoard 4-State Lifecycle) ─────────────────
@app.post("/api/alerts/{alert_id}/clear", response_model=Alert)
async def clear_alert(alert_id: str, req: ClearAlertRequest):
    now = datetime.now(timezone.utc).isoformat()

    async with get_db() as db:
        async with db.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)) as cur:
            row = await cur.fetchone()

        if row:
            await db.execute(
                """UPDATE alerts SET cleared=1, cleared_at=?, cleared_by=?, clear_notes=?
                   WHERE id=?""",
                (now, req.cleared_by, req.notes, alert_id),
            )
            await db.commit()
            async with db.execute("SELECT * FROM alerts WHERE id=?", (alert_id,)) as cur:
                row = await cur.fetchone()
            d = dict(row)
            d["triggered_by"] = json.loads(d.get("triggered_by", "[]"))
            d["acknowledged"] = bool(d.get("acknowledged", 0))
            d["cleared"] = bool(d.get("cleared", 0))
            return Alert(**d)

    # Demo alert (not in DB) — return cleared copy
    _, _, alerts, _ = get_demo_data(_current_scenario)
    for a in alerts:
        if a.id == alert_id:
            d = a.model_dump()
            d.update(_demo_alert_overrides.get(alert_id, {}))
            d.update({
                "cleared": True,
                "cleared_at": now,
                "cleared_by": req.cleared_by,
                "clear_notes": req.notes,
            })
            _demo_alert_overrides[alert_id] = d
            return Alert(**d)
    raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")


# ─── Acoustic Event Validation (Edge Impulse Human-in-the-Loop) ──
@app.post("/api/events/{event_id}/validate", response_model=AcousticEvent)
async def validate_event(event_id: str, req: ValidateEventRequest):
    now = datetime.now(timezone.utc).isoformat()
    status_val = req.get_status()
    notes_val = req.get_notes()
    validator_val = req.get_validator()

    async with get_db() as db:
        async with db.execute("SELECT * FROM acoustic_events WHERE id = ?", (event_id,)) as cur:
            row = await cur.fetchone()

        if row:
            await db.execute(
                """UPDATE acoustic_events SET validation_status=?, validation_notes=?, validated_at=?, validated_by=?
                   WHERE id=?""",
                (status_val, notes_val, now, validator_val, event_id),
            )
            await db.commit()
            async with db.execute("SELECT * FROM acoustic_events WHERE id=?", (event_id,)) as cur:
                row = await cur.fetchone()
            return _row_to_acoustic_event(row)

    # Demo event (not in DB) — return validated copy
    _, events, _, _ = get_demo_data(_current_scenario)
    for e in events:
        if e.id == event_id:
            d = e.model_dump()
            d.update(_demo_event_overrides.get(event_id, {}))
            d.update({
                "validation_status": status_val,
                "validation_notes": notes_val,
                "validated_at": now,
                "validated_by": validator_val,
            })
            _demo_event_overrides[event_id] = d
            return AcousticEvent(**d)
    raise HTTPException(status_code=404, detail=f"Acoustic event {event_id} not found")


# ─── Demo Scenario ─────────────────────────────────────────────────
@app.post("/api/demo/scenario")
async def set_demo_scenario(req: ScenarioRequest):
    global _current_scenario
    _current_scenario = req.scenario
    _demo_alert_overrides.clear()
    _demo_event_overrides.clear()
    log.info(f"Demo scenario set to: {req.scenario}")
    return {"scenario": req.scenario, "message": f"Demo scenario '{req.scenario}' activated"}


# ─── Home Assistant-Style Automation Execution Trace ────────────────
@app.get("/api/alerts/{alert_id}/trace", response_model=ExecutionTrace)
async def get_alert_trace(alert_id: str):
    """
    Exposes a deterministic step-by-step Home Assistant-style automation execution trace
    showing trigger conditions, evaluation criteria, and the resulting action graph.
    """
    alert = None
    async with get_db() as db:
        async with db.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)) as cur:
            row = await cur.fetchone()
        if row:
            d = dict(row)
            d["triggered_by"] = json.loads(d.get("triggered_by", "[]"))
            d["acknowledged"] = bool(d.get("acknowledged", 0))
            d["cleared"] = bool(d.get("cleared", 0))
            alert = Alert(**d)

    if not alert:
        _, _, alerts, _ = get_demo_data(_current_scenario)
        for a in alerts:
            if a.id == alert_id:
                d = a.model_dump()
                d.update(_demo_alert_overrides.get(alert_id, {}))
                alert = Alert(**d)
                break

    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    steps: list[TraceStep] = []
    # Step 1: Trigger
    steps.append(TraceStep(
        step_id="trigger/0",
        step_type="trigger",
        name=f"Telemetry Ingest ({alert.source})",
        status="passed",
        timestamp=alert.timestamp,
        details={
            "device_id": alert.device_id or "unknown",
            "zone_id": alert.zone_id,
            "source": alert.source,
            "message": "Real-time or simulated sensor telemetry received via ingest pipeline"
        }
    ))

    # Step 2: Condition Evaluations
    rules = alert.triggered_by if alert.triggered_by else ["threshold_breach"]
    for idx, rule in enumerate(rules):
        rule_desc = {
            "co2_trend_threshold": "CO2 rise >= 200 ppm across 3 consecutive reading intervals",
            "co2_warn_threshold": "CO2 >= 700 ppm threshold",
            "co2_critical_threshold": "CO2 >= 1200 ppm critical threshold",
            "temp_warn": "Temperature >= 25.0 °C warning threshold",
            "temp_critical": "Temperature >= 30.0 °C critical threshold",
            "rh_high": "Air relative humidity >= 70% threshold (air RH != grain moisture)",
            "rh_critical": "Air relative humidity >= 80% critical threshold (air RH != grain moisture)",
            "nocturne_v1_mini_low_confidence": "Acoustic bioacoustic anomaly score >= 0.40 (experimental, uncalibrated)",
            "nocturne_v1_mini_medium": "Acoustic bioacoustic anomaly score >= 0.50 (experimental, uncalibrated)"
        }.get(rule, f"Rule threshold condition: {rule}")

        steps.append(TraceStep(
            step_id=f"condition/{idx}",
            step_type="condition",
            name=f"Evaluate Rule Gate: {rule}",
            status="passed",
            timestamp=alert.timestamp,
            details={
                "rule": rule,
                "criteria": rule_desc,
                "result": True,
                "operator_gate": "PASSED (Triggered)"
            }
        ))

    # Step 3: Action Execution
    steps.append(TraceStep(
        step_id="action/0",
        step_type="action",
        name="Generate Actionable Environmental Alert",
        status="executed",
        timestamp=alert.timestamp,
        details={
            "alert_id": alert.id,
            "severity": alert.severity,
            "category": alert.category,
            "alarm_state": alert.alarm_state,
            "external_dispatch": "SUPPRESSED (Local dashboard alert only — no external notification spoofed)",
            "human_inspection_required": alert.severity in ("warning", "critical")
        }
    ))

    return ExecutionTrace(
        alert_id=alert.id,
        triggered_at=alert.timestamp,
        zone_id=alert.zone_id,
        device_id=alert.device_id,
        rule_id=" + ".join(rules),
        summary=f"Automation triggered by {len(rules)} condition rules: {alert.title}. Action taken: {alert.severity.upper()} alert generated in state {alert.alarm_state.upper()}.",
        steps=steps
    )


# ─── Frigate-Style Audio Event Batch Review ────────────────────────
@app.post("/api/events/batch-review")
async def batch_review_events(req: BatchReviewRequest):
    """
    Frigate-style batch review transition from unreviewed to reviewed,
    allowing operators to triage multiple bioacoustic detections simultaneously.
    """
    now = datetime.now(timezone.utc).isoformat()
    updated_count = 0

    async with get_db() as db:
        for eid in req.event_ids:
            if req.action in ("validated", "rejected"):
                await db.execute(
                    """UPDATE acoustic_events SET review_status='reviewed', reviewed_at=?, reviewed_by=?,
                       validation_status=?, validation_notes=? WHERE id=?""",
                    (now, req.reviewer, req.action, req.notes, eid)
                )
            else:
                await db.execute(
                    """UPDATE acoustic_events SET review_status='reviewed', reviewed_at=?, reviewed_by=? WHERE id=?""",
                    (now, req.reviewer, eid)
                )
            updated_count += 1
        await db.commit()

    # Apply to demo overrides as well
    for eid in req.event_ids:
        cur_ov = _demo_event_overrides.get(eid, {})
        cur_ov["review_status"] = "reviewed"
        cur_ov["reviewed_at"] = now
        cur_ov["reviewed_by"] = req.reviewer
        if req.action in ("validated", "rejected"):
            cur_ov["validation_status"] = req.action
            if req.notes:
                cur_ov["validation_notes"] = req.notes
        _demo_event_overrides[eid] = cur_ov

    return {
        "status": "success",
        "action": req.action,
        "reviewed_count": len(req.event_ids),
        "message": f"Successfully marked {len(req.event_ids)} acoustic event(s) as {req.action}"
    }


# ─── InfluxDB-Inspired Downsampling & Time-Bucket Aggregation ──────
@app.get("/api/readings/aggregate", response_model=AggregatedTelemetryResponse)
async def get_aggregated_readings(
    zone_id: Optional[str] = None,
    bucket_minutes: int = 15,
    range_hours: int = 24
):
    """
    Aggregates historical telemetry into contiguous time buckets, computing
    average, min, and max while flagging missing-data intervals (InfluxDB pattern).
    """
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(hours=range_hours)
    
    # Fetch readings in range
    readings = []
    async with get_db() as db:
        query = "SELECT * FROM environmental_readings WHERE timestamp >= ?"
        params: list = [start_time.isoformat()]
        if zone_id:
            query += " AND zone_id = ?"
            params.append(zone_id)
        query += " ORDER BY timestamp ASC"
        async with db.execute(query, params) as cur:
            rows = await cur.fetchall()
            if rows:
                readings = [EnvironmentalReading(**dict(r)) for r in rows]

    if not readings:
        demo_readings, _, _, _ = get_demo_data(_current_scenario)
        if zone_id:
            demo_readings = [r for r in demo_readings if r.zone_id == zone_id]
        readings = [r for r in demo_readings if r.timestamp >= start_time.isoformat()]
        readings.sort(key=lambda r: r.timestamp)

    buckets: list[AggregatedBucket] = []
    bucket_delta = timedelta(minutes=bucket_minutes)
    curr_start = start_time
    gap_count = 0
    total_points = len(readings)

    while curr_start < now:
        curr_end = curr_start + bucket_delta
        # Filter readings within bucket
        pts = [
            r for r in readings
            if curr_start.isoformat() <= r.timestamp < curr_end.isoformat()
        ]
        if pts:
            co2_vals = [r.co2_ppm for r in pts if r.co2_ppm is not None and r.co2_valid]
            temp_vals = [r.temperature_c for r in pts if r.temperature_c is not None and r.temp_valid]
            rh_vals = [r.relative_humidity_pct for r in pts if r.relative_humidity_pct is not None and r.rh_valid]

            buckets.append(AggregatedBucket(
                bucket_start=curr_start.isoformat(),
                bucket_end=curr_end.isoformat(),
                point_count=len(pts),
                avg_co2=round(sum(co2_vals) / len(co2_vals), 1) if co2_vals else None,
                min_co2=min(co2_vals) if co2_vals else None,
                max_co2=max(co2_vals) if co2_vals else None,
                avg_temp=round(sum(temp_vals) / len(temp_vals), 1) if temp_vals else None,
                avg_rh=round(sum(rh_vals) / len(rh_vals), 1) if rh_vals else None,
                is_gap=False
            ))
        else:
            gap_count += 1
            buckets.append(AggregatedBucket(
                bucket_start=curr_start.isoformat(),
                bucket_end=curr_end.isoformat(),
                point_count=0,
                is_gap=True
            ))
        curr_start = curr_end

    return AggregatedTelemetryResponse(
        zone_id=zone_id,
        bucket_minutes=bucket_minutes,
        range_hours=range_hours,
        total_points=total_points,
        gap_count=gap_count,
        buckets=buckets
    )


# ─── Isolated Machine Learning Adapters Status & Inference ────────
from .adapters import NocturneMiniAdapter, ZeusAdapter, AcousticInferenceResult


class AcousticInferenceRequest(BaseModel):
    audio_samples: list[float]
    sample_rate: int = 16000
    zone_id: Optional[str] = "zone-a"
    device_id: Optional[str] = "esp32-zone-a-01"


@app.get("/api/models/status")
async def get_models_status():
    """
    Returns actual runtime status and dependency readiness for ML adapters
    without triggering eager model weights loading.
    """
    return {
        "nocturne": NocturneMiniAdapter.check_dependencies().model_dump(),
        "zeus": ZeusAdapter.check_dependencies().model_dump(),
        "rule_engine_active": True,
        "active_scenario": _current_scenario,
    }


@app.post("/api/inference/acoustic", response_model=AcousticInferenceResult)
async def run_acoustic_inference(req: AcousticInferenceRequest):
    """
    Executes lazy bioacoustic inference using NocturneMiniAdapter.
    If dependencies or weights are unavailable, returns explicit UNAVAILABLE
    status while extracting physical audio waveform metrics.
    """
    adapter = NocturneMiniAdapter()
    res = adapter.predict(req.audio_samples, sample_rate=req.sample_rate)
    try:
        import numpy as np
        res.signal_analysis = analyze_signal(np.array(req.audio_samples, dtype=np.float32), sample_rate=req.sample_rate)
    except Exception as e:
        log.warning("Could not calculate signal analysis for raw array: %s", e)
    res.recording_domain = "airborne_microphone"
    return res


MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB max WAV upload


def _extract_form_val(val, default=None):
    if hasattr(val, "default"):
        return val.default if val.default is not ... else default
    return val if val is not None else default


def _is_truthy(val) -> bool:
    if isinstance(val, bool):
        return val
    if hasattr(val, "default"):
        return bool(val.default)
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes")
    return bool(val)


@app.post("/api/inference/acoustic/upload", response_model=AcousticInferenceResult)
async def upload_acoustic_recording(
    file: UploadFile = File(..., description="WAV audio recording file"),
    zone_id: Optional[str] = Form("zone-a"),
    device_id: Optional[str] = Form("esp32-zone-a-01"),
    save_event: bool = Form(False, description="Persist inference result as an acoustic event in the review queue"),
    retain_sample: bool = Form(False, description="Persist original WAV recording to audio sample storage for dataset collection"),
    is_synthetic: bool = Form(False, description="Explicit flag indicating whether the sample is a synthetic test signal"),
    input_source: Optional[str] = Form("user_upload", description="Origin of audio: user_upload, hardware_recording, or synthetic"),
    recording_domain: Optional[str] = Form(None, description="Recording domain: airborne_microphone, accelerometer, etc."),
):
    """
    Ingests, validates, resamples, and executes Nocturne Mini bioacoustic inference
    on a recorded audio file.

    Validation rules:
    - Rejects empty uploads (0 bytes) -> 400 Bad Request
    - Rejects files > 20 MB -> 413 Payload Too Large
    - Inspects file header signatures (RIFF....WAVE) -> 400 Bad Request if not genuine WAV
    - Validates sample rate (8 kHz to 192 kHz) and duration (0.1s to 180s)
    - Downmixes multichannel audio to mono
    - Resamples to 16 kHz
    - Standardizes to a 10.0s window (pads with silence if short, truncates if long)
    - Returns rich metadata (original duration, sample rate, channels, waveform preview, top 5 predictions)
    - Computes physical acoustic signal characteristics (RMS, peak amplitude, centroid, bandwidth, flatness, ZCR, band energy, impulses)
    - Optionally retains original recording on disk outside SQLite when retain_sample=True
    """
    should_retain = _is_truthy(retain_sample)
    should_save_event = _is_truthy(save_event)
    synthetic_flag = _is_truthy(is_synthetic)
    source_val = _extract_form_val(input_source, "user_upload")
    zone_val = _extract_form_val(zone_id, "zone-a")
    device_val = _extract_form_val(device_id, "esp32-zone-a-01")
    rec_dom_val = _extract_form_val(recording_domain, None)

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing filename for uploaded audio."
        )

    # Read file content safely with size limit
    contents = await file.read()
    if not contents or len(contents) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file upload: received 0 bytes."
        )

    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed upload size (20 MB). Received: {len(contents) / (1024 * 1024):.2f} MB."
        )

    # Inspect magic bytes (do NOT trust file extension alone)
    if len(contents) < 44 or contents[:4] != b"RIFF" or contents[8:12] != b"WAVE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Invalid audio format: file header does not contain standard RIFF/WAVE signatures. "
                "File extensions are not accepted as proof of format; only valid WAV files are supported."
            )
        )

    try:
        channels, sample_rate, duration_sec = validate_wav_bytes(contents)
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid audio structure: {val_err}"
        )

    source_type = "synthetic" if synthetic_flag or source_val == "synthetic" else (source_val or "user_upload")

    # Domain separation determination
    if synthetic_flag or source_type == "synthetic":
        domain_val = "synthetic_simulation"
    elif rec_dom_val:
        domain_val = rec_dom_val
    elif source_type in ("hardware_recording", "user_upload", "live_stream", "field_recording"):
        domain_val = "airborne_microphone"
    else:
        domain_val = "unknown"

    # Compute physical acoustic signal characteristics
    try:
        sig_analysis = analyze_wav_bytes(contents)
    except Exception as sig_err:
        log.warning("Could not compute signal analysis for upload: %s", sig_err)
        sig_analysis = None

    adapter = NocturneMiniAdapter()
    result = adapter.predict_wav_bytes(
        contents,
        filename=file.filename,
        input_source=source_type,
        top_k=5,
    )

    result.recording_domain = domain_val
    result.signal_analysis = sig_analysis

    if result.status == "ERROR":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error or "Audio processing error"
        )

    sample_id: Optional[str] = None

    # Persistent Audio Sample Storage for Dataset Collection
    if should_retain:
        sha256_hash = compute_sha256(contents)
        now_iso = datetime.now(timezone.utc).isoformat()
        
        async with get_db() as db:
            await db.executescript(CREATE_SAMPLES)
            # Check for existing sample with identical hash
            cursor = await db.execute("SELECT id, stored_filename FROM retained_audio_samples WHERE sha256_hash = ?", (sha256_hash,))

            existing = await cursor.fetchone()

            if existing:
                sample_id = existing["id"]
                log.info("Audio upload matches existing sample hash %s -> reusing ID %s", sha256_hash, sample_id)
            else:
                sample_id = generate_sample_id()
                try:
                    stored_fn, stored_path, file_size = save_audio_file(sample_id, contents)
                    wf_json = json.dumps(result.waveform_preview or [])
                    peaks_clean = [
                        {"freq_hz": p.get("frequency_hz", p.get("freq_hz", 0)), "db": p.get("magnitude_db", p.get("db", 0))}
                        for p in (result.spectrogram_peaks or [])
                    ]
                    peaks_json = json.dumps(peaks_clean)
                    top_preds_json = json.dumps([p.model_dump() for p in result.top_predictions])
                    sig_json = json.dumps(sig_analysis) if sig_analysis else None

                    await db.execute(
                        """
                        INSERT INTO retained_audio_samples (
                            id, filename, stored_filename, file_size_bytes, sha256_hash,
                            duration_sec, sample_rate, channels, format, timestamp,
                            recording_timestamp, zone_id, device_id, input_source,
                            is_synthetic, recording_domain, model_id, model_version, prediction, score,
                            confidence_band, top_predictions, waveform_preview, spectrogram_peaks,
                            signal_analysis, review_status, ground_truth_label, verification_method, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            sample_id,
                            file.filename,
                            stored_fn,
                            file_size,
                            sha256_hash,
                            duration_sec,
                            sample_rate,
                            channels,
                            "WAV",
                            now_iso,
                            now_iso,
                            zone_val or "zone-a",
                            device_val or "esp32-zone-a-01",
                            source_type,
                            1 if source_type == "synthetic" else 0,
                            domain_val,
                            result.model_id,
                            result.model_id,
                            result.prediction,
                            result.score,
                            result.confidence_band,
                            top_preds_json,
                            wf_json,
                            peaks_json,
                            sig_json,
                            "UNREVIEWED",
                            "UNREVIEWED",
                            "unverified",
                            now_iso,
                        ),
                    )
                    await db.commit()
                    log.info("Persisted audio sample %s into dataset library with domain %s", sample_id, domain_val)
                except Exception as store_err:
                    log.error("Failed to store audio sample on disk/DB: %s", store_err)
                    # We do not fail inference if storage encounters an issue, but log it
                    sample_id = None


        if sample_id:
            result.audio_sample_id = sample_id
            result.is_retained = True

    # Optionally persist to acoustic_events table so it appears in the Frigate review queue
    if should_save_event and result.status in ("EXPERIMENTAL", "READY"):
        try:
            async with get_db() as db:
                evt_id = f"evt-upload-{int(datetime.now(timezone.utc).timestamp())}"
                now_iso = datetime.now(timezone.utc).isoformat()
                tier = "alert" if (result.score or 0) > 0.05 else "detection"
                wf_json = json.dumps(result.waveform_preview or [])
                peaks_clean = [
                    {"freq_hz": p.get("frequency_hz", p.get("freq_hz", 0)), "db": p.get("magnitude_db", p.get("db", 0))}
                    for p in (result.spectrogram_peaks or [])
                ]
                peaks_json = json.dumps(peaks_clean)
                await db.execute(
                    """
                    INSERT OR REPLACE INTO acoustic_events
                    (id, timestamp, zone_id, device_id, source, audio_sample_ref,
                     prediction, model_version, score, score_semantics, confidence_band,
                     validation_status, inference_status, inference_duration_ms,
                     review_status, event_tier, notes, waveform_preview, spectrogram_peaks)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evt_id,
                        now_iso,
                        zone_id or "zone-a",
                        device_id or "esp32-zone-a-01",
                        "REAL" if source_type != "synthetic" else "MODEL_EXPERIMENT",
                        sample_id or file.filename,
                        result.prediction,
                        result.model_id,
                        result.score,
                        result.score_semantics,
                        result.confidence_band,
                        "unvalidated",
                        result.status.lower(),
                        result.inference_duration_ms,
                        "unreviewed",
                        tier,
                        f"Uploaded WAV ({result.original_duration_sec}s, {result.window_mode})",
                        wf_json,
                        peaks_json,
                    ),
                )
                await db.commit()
                log.info("Persisted uploaded acoustic event %s to review queue", evt_id)
        except Exception as db_err:
            log.warning("Could not persist uploaded acoustic event: %s", db_err)

    return result


def _row_to_audio_sample(row) -> RetainedAudioSample:
    d = dict(row)
    for field in ("top_predictions", "waveform_preview", "spectrogram_peaks", "signal_analysis"):
        val = d.get(field)
        if isinstance(val, str):
            try:
                d[field] = json.loads(val)
            except Exception:
                d[field] = [] if field == "top_predictions" else None
    d["is_synthetic"] = bool(d.get("is_synthetic", 0))
    d["recording_domain"] = d.get("recording_domain") or "unknown"
    return RetainedAudioSample(**d)


# ─── Retained Audio Samples Library & Annotation APIs ────────────────────────
@app.get("/api/audio-samples", response_model=List[RetainedAudioSample])
async def list_audio_samples(
    zone_id: Optional[str] = None,
    ground_truth_label: Optional[str] = None,
    review_status: Optional[str] = None,
    input_source: Optional[str] = None,
    is_synthetic: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
):
    """
    Lists retained audio samples stored in the dataset library.
    Supports filtering by zone, ground-truth label, review status, and synthetic flag.
    """
    query = "SELECT * FROM retained_audio_samples WHERE 1=1"
    params: list = []

    if zone_id:
        query += " AND zone_id = ?"
        params.append(zone_id)
    if ground_truth_label:
        query += " AND ground_truth_label = ?"
        params.append(ground_truth_label)
    if review_status:
        query += " AND review_status = ?"
        params.append(review_status)
    if input_source:
        query += " AND input_source = ?"
        params.append(input_source)
    if is_synthetic is not None:
        query += " AND is_synthetic = ?"
        params.append(1 if is_synthetic else 0)

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([max(1, min(limit, 500)), max(0, offset)])

    async with get_db() as db:
        cursor = await db.execute(query, tuple(params))
        rows = await cursor.fetchall()
        return [_row_to_audio_sample(r) for r in rows]


@app.get("/api/audio-samples/{sample_id}", response_model=RetainedAudioSample)
async def get_audio_sample(sample_id: str):
    """Retrieves metadata and annotations for a specific retained audio sample."""
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM retained_audio_samples WHERE id = ?", (sample_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Audio sample '{sample_id}' not found.")
        return _row_to_audio_sample(row)


@app.get("/api/audio-samples/{sample_id}/audio")
async def get_audio_sample_file(sample_id: str):
    """
    Streams the retained WAV audio recording for playback or download.
    Enforces strict path traversal defenses.
    """
    async with get_db() as db:
        cursor = await db.execute("SELECT stored_filename, filename FROM retained_audio_samples WHERE id = ?", (sample_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Audio sample '{sample_id}' not found in database.")

        stored_filename = row["stored_filename"]
        download_name = row["filename"] or f"{sample_id}.wav"

    path = get_audio_file_path(stored_filename)
    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file missing from storage directory on disk.")

    return FileResponse(
        path,
        media_type="audio/wav",
        filename=download_name,
        content_disposition_type="inline",
        headers={"Accept-Ranges": "bytes"}
    )


@app.patch("/api/audio-samples/{sample_id}/annotation", response_model=RetainedAudioSample)
async def update_sample_annotation(sample_id: str, body: AnnotationUpdateRequest):
    """
    Updates the independent physical ground-truth label and reviewer notes for a retained sample.
    Does NOT equate anomaly predictions with verified biological observations.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    rev_status = body.review_status or ("REVIEWED" if body.ground_truth_label != "UNREVIEWED" else "UNREVIEWED")

    async with get_db() as db:
        cursor = await db.execute("SELECT id FROM retained_audio_samples WHERE id = ?", (sample_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Audio sample '{sample_id}' not found.")

        await db.execute(
            """
            UPDATE retained_audio_samples
            SET ground_truth_label = ?,
                verification_method = ?,
                reviewer = ?,
                evidence_notes = ?,
                review_status = ?,
                reviewed_at = ?
            WHERE id = ?
            """,
            (
                body.ground_truth_label,
                body.verification_method or "unverified",
                body.reviewer or "Inspector",
                body.evidence_notes or "",
                rev_status,
                now_iso,
                sample_id,
            )
        )
        await db.commit()

        cursor = await db.execute("SELECT * FROM retained_audio_samples WHERE id = ?", (sample_id,))
        row = await cursor.fetchone()
        return _row_to_audio_sample(row)


@app.delete("/api/audio-samples/{sample_id}")
async def delete_audio_sample(sample_id: str):
    """
    Safely deletes a retained audio sample from both the database and disk storage.
    Prevents path traversal and cleans up storage.
    """
    async with get_db() as db:
        cursor = await db.execute("SELECT stored_filename FROM retained_audio_samples WHERE id = ?", (sample_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Audio sample '{sample_id}' not found.")

        stored_fn = row["stored_filename"]
        delete_audio_file(stored_fn)

        await db.execute("DELETE FROM retained_audio_samples WHERE id = ?", (sample_id,))
        await db.commit()

    return {"deleted": True, "sample_id": sample_id}


@app.get("/api/dataset/manifest")
async def export_dataset_manifest(
    format: Literal["json", "csv"] = "json",
    include_synthetic: bool = False,
):
    """
    Exports a comprehensive dataset manifest of all retained audio recordings,
    SHA-256 hashes, physical verification labels, and model prediction metadata.
    Excludes synthetic signals by default.
    """
    query = "SELECT * FROM retained_audio_samples"
    if not include_synthetic:
        query += " WHERE is_synthetic = 0"
    query += " ORDER BY created_at ASC"

    async with get_db() as db:
        cursor = await db.execute(query)
        rows = await cursor.fetchall()
        samples = [_row_to_audio_sample(r) for r in rows]

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "id", "filename", "sha256_hash", "duration_sec", "sample_rate", "channels",
            "zone_id", "device_id", "input_source", "is_synthetic", "prediction",
            "score", "ground_truth_label", "verification_method", "reviewer", "reviewed_at",
            "dataset_name", "source_species", "source_citation", "source_url", "transducer_type", "created_at"
        ])
        for s in samples:
            writer.writerow([
                s.id, s.filename, s.sha256_hash, s.duration_sec, s.sample_rate, s.channels,
                s.zone_id, s.device_id, s.input_source, int(s.is_synthetic), s.prediction or "",
                s.score if s.score is not None else "", s.ground_truth_label, s.verification_method,
                s.reviewer or "", s.reviewed_at or "",
                s.dataset_name or "", s.source_species or "", s.source_citation or "", s.source_url or "", s.transducer_type or "",
                s.created_at
            ])
        csv_data = output.getvalue()
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=sealsense_dataset_manifest.csv"}
        )

    return {
        "manifest_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_samples": len(samples),
        "synthetic_included": include_synthetic,
        "samples": [s.model_dump() for s in samples]
    }


@app.get("/api/dataset/evaluation", response_model=DatasetEvaluationReport)
async def get_dataset_evaluation(threshold: float = 0.05):
    """
    Executes the offline bioacoustic evaluation harness across all retained samples.
    Excludes synthetic and unreviewed recordings.
    """
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM retained_audio_samples ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        samples_dicts = [dict(r) for r in rows]

    return evaluate_dataset_samples(samples_dicts, anomaly_threshold=threshold, verify_files_on_disk=True)


# ─── USDA Bug Bytes Public Reference Dataset APIs ──────────────────
@app.get("/api/reference/catalog", response_model=List[ReferenceAudioCatalogItem])
async def get_reference_catalog():
    """
    Returns the catalog of authentic USDA Bug Bytes stored-product insect reference audio recordings.
    Annotates each entry with local file availability on disk.
    """
    return [ReferenceAudioCatalogItem(**item) for item in list_reference_catalog()]


@app.get("/api/reference/{catalog_id}/audio")
async def get_reference_audio_file(catalog_id: str):
    """
    Streams an authentic local USDA Bug Bytes reference WAV file for preview/playback.
    """
    item = get_catalog_item(catalog_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Reference catalog item '{catalog_id}' not found.")
    
    file_path = get_reference_file_path(item["filename"])
    if not file_path or not os.path.isfile(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reference audio file '{item['filename']}' is not present locally on disk."
        )

    return FileResponse(
        file_path,
        media_type="audio/wav",
        filename=item["filename"],
        content_disposition_type="inline",
        headers={"Accept-Ranges": "bytes"}
    )


@app.post("/api/reference/import", response_model=AcousticInferenceResult)
async def import_reference_sample(req: ReferenceImportRequest):
    """
    Imports an authentic USDA Bug Bytes stored-product insect reference recording,
    executes Nocturne Mini inference, retains the original audio on disk if requested,
    and tags it with explicit public_reference provenance (never hardware_recording).
    """
    item = get_catalog_item(req.catalog_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Reference catalog item '{req.catalog_id}' not found.")

    file_path = get_reference_file_path(item["filename"])
    if not file_path or not os.path.isfile(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reference audio file '{item['filename']}' is not locally present on disk."
        )

    with open(file_path, "rb") as f:
        wav_bytes = f.read()

    adapter = NocturneMiniAdapter()
    result = adapter.predict_wav_bytes(
        wav_bytes,
        filename=item["filename"],
        input_source="public_reference",
        top_k=5
    )

    result.input_source = "public_reference"
    result.dataset_name = item["dataset_name"]
    result.source_species = item["species"]
    result.source_citation = item["citation"]
    result.source_url = item["source_url"]
    result.transducer_type = item["transducer_type"]
    result.recording_domain = item.get("recording_domain", "unknown")

    # Compute physical acoustic signal characteristics
    try:
        sig_analysis = analyze_wav_bytes(wav_bytes)
    except Exception as sig_err:
        log.warning("Could not compute signal analysis for reference sample: %s", sig_err)
        sig_analysis = None
    result.signal_analysis = sig_analysis

    sample_id = None
    if req.retain_sample:
        sha256_hash = compute_sha256(wav_bytes)
        now_iso = datetime.now(timezone.utc).isoformat()
        channels, sample_rate, duration_sec = validate_wav_bytes(wav_bytes)

        async with get_db() as db:
            await db.executescript(CREATE_SAMPLES)
            cursor = await db.execute("SELECT id, stored_filename FROM retained_audio_samples WHERE sha256_hash = ?", (sha256_hash,))
            existing = await cursor.fetchone()

            if existing:
                sample_id = existing["id"]
                log.info("Reference upload matches existing sample hash %s -> reusing ID %s", sha256_hash, sample_id)
            else:
                sample_id = generate_sample_id()
                try:
                    stored_fn, stored_path, file_size = save_audio_file(sample_id, wav_bytes)
                    wf_json = json.dumps(result.waveform_preview or [])
                    peaks_clean = [
                        {"freq_hz": p.get("frequency_hz", p.get("freq_hz", 0)), "db": p.get("magnitude_db", p.get("db", 0))}
                        for p in (result.spectrogram_peaks or [])
                    ]
                    peaks_json = json.dumps(peaks_clean)
                    top_preds_json = json.dumps([p.model_dump() for p in result.top_predictions])
                    sig_json = json.dumps(sig_analysis) if sig_analysis else None
                    ev_notes = req.notes or f"USDA Bug Bytes reference recording of {item['species']} ({item['life_stage']}). Substrate: {item['substrate']}. Transducer: {item['transducer_type']}."

                    await db.execute(
                        """
                        INSERT INTO retained_audio_samples (
                            id, filename, stored_filename, file_size_bytes, sha256_hash,
                            duration_sec, sample_rate, channels, format, timestamp,
                            recording_timestamp, zone_id, device_id, input_source,
                            is_synthetic, recording_domain, model_id, model_version, prediction, score,
                            confidence_band, top_predictions, waveform_preview, spectrogram_peaks,
                            signal_analysis, review_status, ground_truth_label, verification_method, reviewer,
                            reviewed_at, evidence_notes, dataset_name, source_species,
                            source_citation, source_url, transducer_type, source_category, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            sample_id,
                            item["filename"],
                            stored_fn,
                            file_size,
                            sha256_hash,
                            duration_sec,
                            sample_rate,
                            channels,
                            "WAV",
                            now_iso,
                            now_iso,
                            req.zone_id,
                            req.device_id,
                            "public_reference",
                            0,
                            item.get("recording_domain", "unknown"),
                            result.model_id,
                            result.model_id,
                            result.prediction,
                            result.score,
                            result.confidence_band,
                            top_preds_json,
                            wf_json,
                            peaks_json,
                            sig_json,
                            "REVIEWED",
                            "TARGET_PEST_OBSERVED",
                            "laboratory_reared_culture",
                            "USDA-ARS CMAVE (Dr. Richard W. Mankin)",
                            now_iso,
                            ev_notes,
                            item["dataset_name"],
                            item["species"],
                            item["citation"],
                            item["source_url"],
                            item["transducer_type"],
                            item["category"],
                            now_iso,
                        ),
                    )
                    await db.commit()
                    log.info("Persisted USDA Bug Bytes reference sample %s into library with domain %s", sample_id, item.get("recording_domain"))
                except Exception as store_err:
                    log.error("Failed to store reference audio sample: %s", store_err)
                    sample_id = None

        if sample_id:
            result.audio_sample_id = sample_id
            result.is_retained = True

    return result


@app.get("/api/reference/{catalog_id}/analysis")
async def get_reference_signal_analysis(catalog_id: str):
    """
    Computes and returns physical acoustic signal characteristics
    (RMS, peak amplitude, spectral centroid, bandwidth, flatness, ZCR, band energy distribution, and transient impulse counts)
    for an authentic USDA reference recording without biological diagnosis claims.
    """
    item = get_catalog_item(catalog_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Reference catalog item '{catalog_id}' not found.")
    
    file_path = get_reference_file_path(item["filename"])
    if not file_path or not os.path.isfile(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reference audio file '{item['filename']}' is not present locally on disk."
        )

    with open(file_path, "rb") as f:
        wav_bytes = f.read()

    analysis = analyze_wav_bytes(wav_bytes)
    return {
        "catalog_id": item["id"],
        "filename": item["filename"],
        "species": item["species"],
        "common_name": item["common_name"],
        "transducer_type": item["transducer_type"],
        "recording_domain": item.get("recording_domain", "unknown"),
        "analysis": analysis,
    }


# ─── Synthetic Bioacoustic Simulation Scenario Generator APIs ─────
@app.post("/api/simulation/synthetic/generate", response_model=AcousticInferenceResult)
async def generate_synthetic_simulation(req: SyntheticImpulseRequest):
    """
    Generates synthetic bioacoustic stored-grain insect impulses (click bursts),
    optionally executes Nocturne Mini inference, and labels all outputs as SYNTHETIC SIMULATION.
    Always sets is_synthetic=True and input_source='synthetic'.
    """
    wav_bytes = generate_synthetic_impulse_wav(
        impulse_rate=req.impulse_rate,
        amplitude=req.amplitude,
        noise_level=req.noise_level,
        duration_sec=req.duration_sec,
        sample_rate=16000,
        seed=req.seed,
    )

    # Compute physical acoustic signal characteristics
    try:
        sig_analysis = analyze_wav_bytes(wav_bytes)
    except Exception as sig_err:
        log.warning("Could not compute signal analysis for synthetic simulation: %s", sig_err)
        sig_analysis = None

    adapter = NocturneMiniAdapter()
    result = adapter.predict_wav_bytes(
        wav_bytes,
        filename=f"synthetic_simulation_seed_{req.seed}_{int(req.impulse_rate)}cps.wav",
        input_source="synthetic",
        top_k=5,
    )

    result.input_source = "synthetic"
    result.recording_domain = "synthetic_simulation"
    result.signal_analysis = sig_analysis
    result.simulation_params = {
        "impulse_rate": req.impulse_rate,
        "amplitude": req.amplitude,
        "noise_level": req.noise_level,
        "duration_sec": req.duration_sec,
        "seed": req.seed,
        "generator": "poisson_kernel_chewing_bursts",
    }

    sample_id = None
    if req.retain_sample:
        sha256_hash = compute_sha256(wav_bytes)
        now_iso = datetime.now(timezone.utc).isoformat()
        channels, sample_rate, duration_sec = validate_wav_bytes(wav_bytes)

        async with get_db() as db:
            await db.executescript(CREATE_SAMPLES)
            sample_id = generate_sample_id()
            stored_fn, stored_path, file_size = save_audio_file(sample_id, wav_bytes)
            wf_json = json.dumps(result.waveform_preview or [])
            peaks_clean = [
                {"freq_hz": p.get("frequency_hz", p.get("freq_hz", 0)), "db": p.get("magnitude_db", p.get("db", 0))}
                for p in (result.spectrogram_peaks or [])
            ]
            peaks_json = json.dumps(peaks_clean)
            top_preds_json = json.dumps([p.model_dump() for p in result.top_predictions])
            sig_json = json.dumps(sig_analysis) if sig_analysis else None

            await db.execute(
                """
                INSERT INTO retained_audio_samples (
                    id, filename, stored_filename, file_size_bytes, sha256_hash,
                    duration_sec, sample_rate, channels, format, timestamp,
                    recording_timestamp, zone_id, device_id, input_source,
                    is_synthetic, recording_domain, model_id, model_version, prediction, score,
                    confidence_band, top_predictions, waveform_preview, spectrogram_peaks,
                    signal_analysis, review_status, ground_truth_label, verification_method, reviewer,
                    reviewed_at, evidence_notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sample_id,
                    f"synthetic_simulation_seed_{req.seed}.wav",
                    stored_fn,
                    file_size,
                    sha256_hash,
                    duration_sec,
                    sample_rate,
                    channels,
                    "WAV",
                    now_iso,
                    now_iso,
                    req.zone_id,
                    req.device_id,
                    "synthetic",
                    1,
                    "synthetic_simulation",
                    result.model_id,
                    result.model_id,
                    result.prediction,
                    result.score,
                    result.confidence_band,
                    top_preds_json,
                    wf_json,
                    peaks_json,
                    sig_json,
                    "REVIEWED",
                    "INCONCLUSIVE",
                    "unverified",
                    "Synthetic Simulation Generator",
                    now_iso,
                    f"Synthetic click scenario (rate={req.impulse_rate} Hz, amp={req.amplitude}, noise={req.noise_level}, seed={req.seed}). STRICTLY EXCLUDED FROM EVALUATION.",
                    now_iso,
                ),
            )
            await db.commit()

        if sample_id:
            result.audio_sample_id = sample_id
            result.is_retained = True

    return result


@app.get("/api/simulation/synthetic/wav")
async def get_synthetic_simulation_wav(
    impulse_rate: float = 12.0,
    amplitude: float = 0.6,
    noise_level: float = 0.04,
    duration_sec: float = 10.0,
    seed: int = 42,
):
    """
    Directly streams a synthetic 16 kHz WAV file with the requested parameter settings
    for browser audio playback or direct file download.
    """
    wav_bytes = generate_synthetic_impulse_wav(
        impulse_rate=impulse_rate,
        amplitude=amplitude,
        noise_level=noise_level,
        duration_sec=duration_sec,
        sample_rate=16000,
        seed=seed,
    )
    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={
            "Content-Disposition": f"inline; filename=synthetic_simulation_{int(impulse_rate)}cps_seed{seed}.wav",
            "Accept-Ranges": "bytes",
        }
    )


@app.post("/api/audio-samples/seed-demo")
async def seed_demo_audio_samples():
    """
    Seeds initial realistic sample recordings and ground-truth inspection records
    into the retained dataset library and filesystem storage for immediate demonstration.
    """
    import math

    now = datetime.now(timezone.utc)
    seeded_samples = [
        {
            "filename": "grain_probe_zone_a_weevil_cluster.wav",
            "zone_id": "zone-a",
            "device_id": "esp32-zone-a-01",
            "input_source": "user_upload",
            "is_synthetic": 0,
            "prediction": "Eunemobius carolinus",
            "score": 0.0842,
            "confidence_band": "medium",
            "ground_truth_label": "TARGET_PEST_OBSERVED",
            "verification_method": "physical_trap_inspection",
            "reviewer": "Dr. Aris Thorne (Entomologist)",
            "evidence_notes": "Spear probe sample revealed 14 live Sitophilus oryzae adults in 500g grain sample.",
            "duration_sec": 10.0,
            "freq_center": 450.0,
        },
        {
            "filename": "silo_b_ambient_aeration_quiet.wav",
            "zone_id": "zone-b",
            "device_id": "esp32-zone-b-01",
            "input_source": "user_upload",
            "is_synthetic": 0,
            "prediction": "Canis lupus",
            "score": 0.0121,
            "confidence_band": "low",
            "ground_truth_label": "NO_TARGET_PEST_OBSERVED",
            "verification_method": "grain_sieve",
            "reviewer": "Sarah Lin (QA Inspector)",
            "evidence_notes": "Sieve inspection negative across 3 headspace sample trays. Sound matches ambient aeration fan rumble.",
            "duration_sec": 10.0,
            "freq_center": 180.0,
        },
        {
            "filename": "silo_c_headspace_scratching.wav",
            "zone_id": "zone-c",
            "device_id": "esp32-zone-c-01",
            "input_source": "user_upload",
            "is_synthetic": 0,
            "prediction": "Metaplastes ornatus",
            "score": 0.0615,
            "confidence_band": "medium",
            "ground_truth_label": "INCONCLUSIVE",
            "verification_method": "visual_sample",
            "reviewer": "Marco Rossi (Silo Tech)",
            "evidence_notes": "Acoustic scratch sound audible; surface grain inspection showed no insects. Awaiting deep pit trap results.",
            "duration_sec": 10.0,
            "freq_center": 520.0,
        },
        {
            "filename": "browser_synthetic_chirp_smoke_test.wav",
            "zone_id": "zone-a",
            "device_id": "esp32-zone-a-01",
            "input_source": "synthetic",
            "is_synthetic": 1,
            "prediction": "Sclerophrys poweri",
            "score": 0.0095,
            "confidence_band": "low",
            "ground_truth_label": "UNREVIEWED",
            "verification_method": "unverified",
            "reviewer": None,
            "evidence_notes": "Generated by browser synthetic signal tool. EXCLUDED from real-world dataset metrics.",
            "duration_sec": 10.0,
            "freq_center": 600.0,
        },
        {
            "filename": "usda_bugbytes_accelrw.wav",
            "zone_id": "zone-a",
            "device_id": "esp32-zone-a-01",
            "input_source": "public_reference",
            "is_synthetic": 0,
            "prediction": "Metaplastes ornatus",
            "score": 0.0784,
            "confidence_band": "medium",
            "ground_truth_label": "TARGET_PEST_OBSERVED",
            "verification_method": "laboratory_reared_culture",
            "reviewer": "USDA-ARS CMAVE (Dr. Richard W. Mankin)",
            "evidence_notes": "Authentic USDA Bug Bytes recording of Sitophilus oryzae (Rice weevil larvae, 16-17d) feeding in wheat kernels. Contact accelerometer transducer. Not hardware sensor data.",
            "duration_sec": 10.0,
            "freq_center": 420.0,
            "dataset_name": "USDA Bug Bytes Sound Library: Stored Product Insect Pest Sounds",
            "source_species": "Sitophilus oryzae",
            "source_citation": "Mankin, R. W. (USDA-ARS CMAVE). DOI: 10.15482/USDA.ADC/1504600",
            "source_url": "https://catalog.data.gov/dataset/bug-bytes-sound-library-stored-product-insect-pest-sounds",
            "transducer_type": "Brüel & Kjær 4370 accelerometer (contact transducer)",
            "source_category": "A. Stored product insect movement and feeding sounds",
        },
    ]

    count = 0
    async with get_db() as db:
        for item in seeded_samples:
            # Check if authentic reference file exists on disk
            ref_path = get_reference_file_path(item.get("filename", "").replace("usda_bugbytes_", ""))
            if ref_path and os.path.isfile(ref_path):
                with open(ref_path, "rb") as rf:
                    wav_bytes = rf.read()
            else:
                # Generate audio bytes for this file
                sample_rate = 16000
                num_samples = int(item["duration_sec"] * sample_rate)
                buf = io.BytesIO()
                with wave.open(buf, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sample_rate)
                    raw_bytes = bytearray()
                    freq = item["freq_center"]
                    for i in range(num_samples):
                        t = i / sample_rate
                        val = 0.2 * math.sin(2 * math.pi * freq * t)
                        int_val = int(max(-32768, min(32767, val * 32767)))
                        raw_bytes.extend(int_val.to_bytes(2, "little", signed=True))
                    wf.writeframes(raw_bytes)
                wav_bytes = buf.getvalue()

            sha256_hash = compute_sha256(wav_bytes)

            cursor = await db.execute("SELECT id FROM retained_audio_samples WHERE sha256_hash = ?", (sha256_hash,))
            if await cursor.fetchone():
                continue

            sample_id = generate_sample_id()
            stored_fn, _, file_size = save_audio_file(sample_id, wav_bytes)
            wf_preview = json.dumps([0.15, 0.22, 0.38, 0.65, 0.72, 0.45, 0.31, 0.18, 0.25, 0.49, 0.61, 0.35, 0.21, 0.15, 0.12, 0.09])
            peaks_preview = json.dumps([{"freq_hz": item["freq_center"], "db": -24.5}])
            top_preds = json.dumps([{"label": item["prediction"], "score": item["score"]}])

            sig_analysis = None
            try:
                sig_analysis = analyze_wav_bytes(wav_bytes)
            except Exception as e:
                log.warning("Could not analyze seeded sample: %s", e)

            domain_val = item.get("recording_domain")
            if not domain_val:
                if item.get("is_synthetic"):
                    domain_val = "synthetic_simulation"
                elif item.get("input_source") == "public_reference":
                    domain_val = "accelerometer"
                else:
                    domain_val = "unknown"

            await db.execute(
                """
                INSERT INTO retained_audio_samples (
                    id, filename, stored_filename, file_size_bytes, sha256_hash,
                    duration_sec, sample_rate, channels, format, timestamp,
                    recording_timestamp, zone_id, device_id, input_source,
                    is_synthetic, recording_domain, model_id, model_version, prediction, score,
                    confidence_band, top_predictions, waveform_preview, spectrogram_peaks,
                    signal_analysis, review_status, ground_truth_label, verification_method, reviewer,
                    reviewed_at, evidence_notes, dataset_name, source_species,
                    source_citation, source_url, transducer_type, source_category, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sample_id,
                    item["filename"],
                    stored_fn,
                    file_size,
                    sha256_hash,
                    item["duration_sec"],
                    16000,
                    1,
                    "WAV",
                    now.isoformat(),
                    now.isoformat(),
                    item["zone_id"],
                    item["device_id"],
                    item["input_source"],
                    item["is_synthetic"],
                    domain_val,
                    "stratus-labs/nocturne-v1-mini",
                    "nocturne-v1-mini (EXPERIMENTAL)",
                    item["prediction"],
                    item["score"],
                    item["confidence_band"],
                    top_preds,
                    wf_preview,
                    peaks_preview,
                    json.dumps(sig_analysis) if sig_analysis else None,
                    "REVIEWED" if item["ground_truth_label"] != "UNREVIEWED" else "UNREVIEWED",
                    item["ground_truth_label"],
                    item["verification_method"],
                    item.get("reviewer"),
                    now.isoformat() if item.get("reviewer") else None,
                    item.get("evidence_notes"),
                    item.get("dataset_name"),
                    item.get("source_species"),
                    item.get("source_citation"),
                    item.get("source_url"),
                    item.get("transducer_type"),
                    item.get("source_category"),
                    now.isoformat(),
                ),
            )
            count += 1

        await db.commit()

    return {"seeded": count, "message": f"Successfully seeded {count} demo audio samples with physical ground-truth annotations"}




