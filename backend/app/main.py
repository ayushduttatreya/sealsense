"""
SealSense FastAPI Backend
Run with: uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations
import json
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .database import init_db, get_db
from .models import (
    EnvironmentalReading, AcousticEvent, Alert, Device, Zone,
    TelemetryPayload, AcknowledgeRequest, ClearAlertRequest,
    ValidateEventRequest, ScenarioRequest,
    TraceStep, ExecutionTrace, BatchReviewRequest,
    AggregatedBucket, AggregatedTelemetryResponse,
)
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
        events = []
        for r in rows:
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

            events.append(AcousticEvent(**d))
        return events

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


# ─── Telemetry Ingest ─────────────────────────────────────────────
@app.post("/api/telemetry", response_model=EnvironmentalReading)
async def ingest_telemetry(payload: TelemetryPayload):
    """Receives real telemetry from ESP32 firmware via HTTP POST and applies ThingsBoard-style deduplicating alert rules."""
    reading = EnvironmentalReading(
        zone_id=payload.zone_id,
        device_id=payload.device_id,
        timestamp=payload.timestamp,
        source="REAL",
        co2_ppm=payload.co2_ppm,
        temperature_c=payload.temperature_c,
        relative_humidity_pct=payload.relative_humidity_pct,
        co2_valid=payload.co2_valid,
        temp_valid=payload.temp_valid,
        rh_valid=payload.rh_valid,
    )
    async with get_db() as db:
        await db.execute(
            """INSERT INTO environmental_readings
               (id, timestamp, zone_id, device_id, source, co2_ppm,
                temperature_c, relative_humidity_pct, co2_valid, temp_valid, rh_valid)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (reading.id, reading.timestamp, reading.zone_id, reading.device_id,
             reading.source, reading.co2_ppm, reading.temperature_c,
             reading.relative_humidity_pct,
             int(reading.co2_valid), int(reading.temp_valid), int(reading.rh_valid)),
        )

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
                # Update existing active alert
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

    log.info(f"Telemetry received from {payload.device_id}: CO2={payload.co2_ppm} RH={payload.relative_humidity_pct}")
    return reading


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
            return AcousticEvent(**dict(row))

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
    return adapter.predict(req.audio_samples, sample_rate=req.sample_rate)


MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB max WAV upload


@app.post("/api/inference/acoustic/upload", response_model=AcousticInferenceResult)
async def upload_acoustic_recording(
    file: UploadFile = File(..., description="WAV audio recording file"),
    zone_id: Optional[str] = Form("zone-a"),
    device_id: Optional[str] = Form("esp32-zone-a-01"),
    save_event: bool = Form(False, description="Persist inference result as an acoustic event in the review queue"),
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
    """
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

    adapter = NocturneMiniAdapter()
    result = adapter.predict_wav_bytes(
        contents,
        filename=file.filename,
        input_source="user_upload",
        top_k=5,
    )

    if result.status == "ERROR":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error or "Audio processing error"
        )

    # Optionally persist to acoustic_events table so it appears in the Frigate review queue
    if save_event and result.status in ("EXPERIMENTAL", "READY"):
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
                        "REAL",
                        file.filename,
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
                        f"User uploaded WAV ({result.original_duration_sec}s, {result.window_mode})",
                        wf_json,
                        peaks_json,
                    ),
                )
                await db.commit()
                log.info("Persisted uploaded acoustic event %s to review queue", evt_id)
        except Exception as db_err:
            log.warning("Could not persist uploaded acoustic event: %s", db_err)

    return result


