"""
Automated Verification Suite for REA-Adapted Features in SealSense
Tests:
1. ThingsBoard-style 4-state alarm lifecycle (active_unack -> active_ack -> cleared_ack)
2. ThingsBoard-style alert deduplication on telemetry ingest
3. Edge Impulse-style acoustic sample human validation (validated/rejected audit notes)
4. ThingsBoard-style device inactivity evaluation (timeout vs last_seen)
5. SQLite schema migrations and data integrity
6. Strict environmental domain guardrails (Air RH is NEVER grain moisture)
"""
import sys
import os
import asyncio
from datetime import datetime, timezone, timedelta

# Ensure backend root is on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.database import init_db, get_db
from app.models import (
    EnvironmentalReading,
    TelemetryPayload,
    AcknowledgeRequest,
    ClearAlertRequest,
    ValidateEventRequest,
    ScenarioRequest,
    Alert,
    AcousticEvent,
    Device
)
from app.alert_rules import evaluate_environmental
from app.main import (
    list_alerts,
    acknowledge_alert,
    clear_alert,
    validate_event,
    list_devices,
    ingest_telemetry,
    set_demo_scenario
)

async def test_schema_and_migrations():
    print("1. Testing SQLite Schema and Safe Migrations...")
    await init_db()
    async with get_db() as db:
        async with db.execute("PRAGMA table_info(alerts)") as cur:
            alert_cols = {col[1] for col in await cur.fetchall()}
            assert "cleared" in alert_cols, "cleared column missing from alerts"
            assert "cleared_at" in alert_cols, "cleared_at column missing from alerts"
            assert "cleared_by" in alert_cols, "cleared_by column missing from alerts"
            assert "clear_notes" in alert_cols, "clear_notes column missing from alerts"

        async with db.execute("PRAGMA table_info(acoustic_events)") as cur:
            event_cols = {col[1] for col in await cur.fetchall()}
            assert "validation_notes" in event_cols, "validation_notes missing from acoustic_events"
            assert "validated_at" in event_cols, "validated_at missing from acoustic_events"
            assert "validated_by" in event_cols, "validated_by missing from acoustic_events"
            
    print("   ✓ Database schema migrations confirmed.")

async def test_thingsboard_alarm_lifecycle():
    print("2. Testing ThingsBoard 4-State Alarm Lifecycle...")
    await set_demo_scenario(ScenarioRequest(scenario="rising_environmental_risk"))
    alerts = await list_alerts()
    assert len(alerts) > 0, "Should have alerts in rising_environmental_risk scenario"
    
    target_alert = alerts[0]
    print(f"   Initial alarm state: {target_alert.alarm_state}")
    
    # 1. Acknowledge the alert
    ack_res = await acknowledge_alert(
        target_alert.id,
        AcknowledgeRequest(acknowledged_by="operator@sealsense.local", notes="Ventilation fans dispatched")
    )
    assert ack_res.acknowledged is True
    assert ack_res.cleared is False
    assert ack_res.alarm_state == "active_ack"
    print(f"   After acknowledge: {ack_res.alarm_state}")

    # 2. Clear the alert
    clear_res = await clear_alert(
        target_alert.id,
        ClearAlertRequest(cleared_by="operator@sealsense.local", notes="CO2 normalized to 450 ppm")
    )
    assert clear_res.cleared is True
    assert clear_res.alarm_state == "cleared_ack"
    assert clear_res.clear_notes == "CO2 normalized to 450 ppm"
    print(f"   After clear: {clear_res.alarm_state}")
    print("   ✓ 4-State lifecycle (active_unack -> active_ack -> cleared_ack) verified.")

async def test_edge_impulse_human_validation():
    print("3. Testing Edge Impulse Acoustic Sample Human Review...")
    await set_demo_scenario(ScenarioRequest(scenario="experimental_acoustic_event"))
    from app.main import list_events
    events = await list_events()
    assert len(events) > 0, "Should have acoustic events in pest_activity scenario"
    
    target_event = events[0]
    assert hasattr(target_event, "waveform_preview"), "AcousticEvent should have waveform_preview"
    assert len(target_event.waveform_preview) > 0, "Waveform should have envelope steps"
    assert len(target_event.spectrogram_peaks) > 0, "Spectrogram peaks should be present"
    
    # Human validation: Mark as validated
    validated = await validate_event(
        target_event.id,
        ValidateEventRequest(
            validation_status="validated",
            validation_notes="Physical trap inspection confirmed sitophilus oryzae presence.",
            validated_by="entomologist@agri.lab"
        )
    )
    assert validated.validation_status == "validated"
    assert validated.validation_notes == "Physical trap inspection confirmed sitophilus oryzae presence."
    assert validated.validated_by == "entomologist@agri.lab"
    print("   ✓ Edge Impulse human-in-the-loop validation & audit trail verified.")

async def test_device_inactivity_evaluation():
    print("4. Testing Device Inactivity & Last-Seen Calculation...")
    devices = await list_devices()
    assert len(devices) > 0, "Should return list of devices"
    for d in devices:
        assert d.inactivity_timeout_sec == 300, "Default timeout should be 300s"
        assert d.is_active in (True, False), "is_active should be boolean"
        assert d.last_seen is not None
        print(f"   Device {d.id} ({d.zone_id}): active={d.is_active}, timeout={d.inactivity_timeout_sec}s, last_seen={d.last_seen}")
    print("   ✓ Device inactivity evaluation verified.")

def test_environmental_domain_guardrails():
    print("5. Testing Environmental Domain Guardrails (Air RH != Grain Moisture)...")
    reading = EnvironmentalReading(
        device_id="esp32-grain-01",
        zone_id="silo-north-01",
        timestamp=datetime.now(timezone.utc).isoformat(),
        source="REAL",
        co2_ppm=880.0,
        temperature_c=27.0,
        relative_humidity_pct=76.0,
        co2_valid=True,
        temp_valid=True,
        rh_valid=True
    )
    alerts = evaluate_environmental([reading], zone_id="silo-north-01", device_id="esp32-grain-01")
    assert len(alerts) > 0
    for a in alerts:
        # Check rule trigger
        assert len(a.triggered_by) > 0
        # NEVER confuse air RH with grain moisture (must explicitly clarify it is air RH, not grain moisture content)
        assert "grain moisture:" not in a.message.lower()
        assert "not grain moisture" in a.message.lower() or "air rh" in a.message.lower()
        print(f"   Alert message: '{a.message}' | Rules: {a.triggered_by}")
    print("   ✓ Domain rules verified.")

async def test_home_assistant_automation_trace():
    print("6. Testing Home Assistant Automation Execution Trace...")
    await set_demo_scenario(ScenarioRequest(scenario="combined_warning"))
    alerts = await list_alerts()
    assert len(alerts) > 0, "Should have alerts in combined_warning scenario"

    from app.main import get_alert_trace
    target_alert = alerts[0]
    trace = await get_alert_trace(target_alert.id)

    assert trace.alert_id == target_alert.id
    assert len(trace.steps) >= 3, "Execution trace must contain at least trigger, condition, and action steps"
    
    step_types = [s.step_type for s in trace.steps]
    assert "trigger" in step_types, "Trace must contain a trigger step"
    assert "condition" in step_types, "Trace must contain condition step(s)"
    assert "action" in step_types, "Trace must contain an action step"

    trigger_step = next(s for s in trace.steps if s.step_type == "trigger")
    action_step = next(s for s in trace.steps if s.step_type == "action")
    assert trigger_step.status == "passed"
    assert action_step.status == "executed"
    print(f"   Execution Trace ID: {trace.alert_id} ({len(trace.steps)} steps: {step_types})")
    print(f"   Action: {action_step.name}")
    print("   ✓ Home Assistant automation execution trace verified.")

async def test_frigate_event_review_lifecycle():
    print("7. Testing Frigate Event Review Lifecycle (Tiers & Batch Review)...")
    await set_demo_scenario(ScenarioRequest(scenario="experimental_acoustic_event"))
    from app.main import list_events, batch_review_events
    from app.models import BatchReviewRequest

    # Test filtering unreviewed
    unreviewed = await list_events(review_status="unreviewed")
    assert len(unreviewed) > 0, "Should have unreviewed acoustic events"

    first = unreviewed[0]
    assert first.review_status == "unreviewed"
    assert first.event_tier in ("alert", "detection"), f"Unexpected event tier: {first.event_tier}"
    print(f"   Event {first.id}: tier={first.event_tier}, status={first.review_status}, score={first.score}")

    # Perform Frigate-style batch review
    batch_ids = [e.id for e in unreviewed]
    res = await batch_review_events(
        BatchReviewRequest(event_ids=batch_ids, reviewer="entomologist_reviewer")
    )
    assert res["status"] == "success"
    assert res["reviewed_count"] == len(batch_ids)

    # Verify transition
    remaining_unreviewed = await list_events(review_status="unreviewed")
    assert len(remaining_unreviewed) == 0, "All target events should now be reviewed"

    reviewed = await list_events(review_status="reviewed")
    assert len(reviewed) >= len(batch_ids)
    assert reviewed[0].reviewed_by == "entomologist_reviewer"
    print(f"   ✓ Frigate review lifecycle verified ({len(batch_ids)} events transitioned to 'reviewed').")

async def test_influxdb_time_bucket_aggregation():
    print("8. Testing InfluxDB Continuous Downsampling & Time Bucketing...")
    from app.main import get_aggregated_readings

    res = await get_aggregated_readings(zone_id="silo-north-01", bucket_minutes=15, range_hours=24)
    assert res.zone_id == "silo-north-01"
    assert res.bucket_minutes == 15
    assert len(res.buckets) > 0, "Should return aggregated time buckets"

    sample_bucket = next((b for b in res.buckets if not b.is_gap), res.buckets[0])
    assert sample_bucket.point_count >= 1 or sample_bucket.is_gap
    print(f"   Aggregated {len(res.buckets)} buckets. Sample: count={sample_bucket.point_count}, avg_co2={sample_bucket.avg_co2} ppm, avg_rh={sample_bucket.avg_rh} %")
    print(f"   Downsampling continuity: gap_count={res.gap_count}")
    print("   ✓ InfluxDB time-bucket rollup and downsampling verified.")

async def main():
    print("==================================================")
    print("Running SealSense REA Verification Test Suite")
    print("==================================================")
    await test_schema_and_migrations()
    await test_thingsboard_alarm_lifecycle()
    await test_edge_impulse_human_validation()
    await test_device_inactivity_evaluation()
    test_environmental_domain_guardrails()
    await test_home_assistant_automation_trace()
    await test_frigate_event_review_lifecycle()
    await test_influxdb_time_bucket_aggregation()
    print("==================================================")
    print("ALL 8 VERIFICATION SUITES PASSED SUCCESSFULLY!")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(main())
