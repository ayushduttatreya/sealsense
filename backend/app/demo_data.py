"""
Deterministic demo scenario data generator.
Data is always labelled SIMULATED or MODEL_EXPERIMENT — never mixed with real hardware series.
"""
from __future__ import annotations
import json
import math
from datetime import datetime, timedelta, timezone
from typing import List, Tuple
from .models import (
    EnvironmentalReading, AcousticEvent, Alert, Zone, Device, SensorInventory
)

DEMO_DEVICES: List[Device] = [
    Device(
        id="esp32-zone-a-01", name="Zone A Node 1", zone_id="zone-a",
        firmware_version="1.2.0",
        last_seen=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        connected=True,
        inactivity_timeout_sec=300,
        last_activity_time=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        is_active=True,
        sensors=[
            SensorInventory(type="SCD41", status="ok",
                last_reading=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()),
            SensorInventory(type="INMP441", status="ok",
                last_reading=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()),
            SensorInventory(type="BUZZER", status="ok"),
        ],
    ),
    Device(
        id="esp32-zone-b-01", name="Zone B Node 1", zone_id="zone-b",
        firmware_version="1.2.0",
        last_seen=(datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat(),
        connected=True,
        inactivity_timeout_sec=300,
        last_activity_time=(datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat(),
        is_active=True,
        sensors=[
            SensorInventory(type="SCD41", status="ok"),
            SensorInventory(type="INMP441", status="ok"),
            SensorInventory(type="BUZZER", status="ok"),
        ],
    ),
    Device(
        id="esp32-zone-c-01", name="Zone C Node 1", zone_id="zone-c",
        firmware_version="1.1.3",
        last_seen=(datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat(),
        connected=False,
        inactivity_timeout_sec=300,
        last_activity_time=(datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat(),
        is_active=False,
        sensors=[
            SensorInventory(type="SCD41", status="unknown"),
            SensorInventory(type="INMP441", status="unknown"),
            SensorInventory(type="BUZZER", status="unknown"),
        ],
    ),
]

BASE_ZONES: List[Zone] = [
    Zone(id="zone-a", name="Zone A — Silo 1", description="Primary wheat storage",
         device_ids=["esp32-zone-a-01"], health="healthy"),
    Zone(id="zone-b", name="Zone B — Silo 2", description="Barley storage",
         device_ids=["esp32-zone-b-01"], health="healthy"),
    Zone(id="zone-c", name="Zone C — Silo 3", description="Corn storage (offline)",
         device_ids=["esp32-zone-c-01"], health="unknown"),
]

def ts(offset_min: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=offset_min)).isoformat()

def _readings_healthy(n=24) -> List[EnvironmentalReading]:
    out = []
    for i in range(n):
        phase = i / n * 2 * math.pi
        out.append(EnvironmentalReading(
            zone_id="zone-a", device_id="esp32-zone-a-01",
            timestamp=ts((n - i) * 15), source="SIMULATED",
            co2_ppm=415 + 10 * math.sin(phase),
            temperature_c=round(18.0 + 0.5 * math.sin(phase), 1),
            relative_humidity_pct=round(56 + 3 * math.cos(phase), 1),
        ))
    return out

def _readings_rising(n=24) -> List[EnvironmentalReading]:
    out = []
    for i in range(n):
        out.append(EnvironmentalReading(
            zone_id="zone-a", device_id="esp32-zone-a-01",
            timestamp=ts((n - i) * 15), source="SIMULATED",
            co2_ppm=round(450 + i * 30, 1),
            temperature_c=round(19.0 + i * 0.15, 1),
            relative_humidity_pct=round(62 + i * 0.5, 1),
        ))
    return out

def _readings_combined(n=24) -> List[EnvironmentalReading]:
    out = []
    for i in range(n):
        out.append(EnvironmentalReading(
            zone_id="zone-b", device_id="esp32-zone-b-01",
            timestamp=ts((n - i) * 15), source="SIMULATED",
            co2_ppm=round(600 + i * 25, 1),
            temperature_c=round(22.0 + i * 0.2, 1),
            relative_humidity_pct=round(72 + i * 0.8, 1),
        ))
    return out

def _readings_normal(n=24) -> List[EnvironmentalReading]:
    out = []
    for i in range(n):
        out.append(EnvironmentalReading(
            zone_id="zone-b", device_id="esp32-zone-b-01",
            timestamp=ts((n - i) * 15), source="SIMULATED",
            co2_ppm=round(500 - i * 5, 1),
            temperature_c=round(20.5 - i * 0.1, 1),
            relative_humidity_pct=round(65 - i * 0.3, 1),
        ))
    return out

def _acoustic_unavailable() -> AcousticEvent:
    return AcousticEvent(
        id="evt-ambient-01",
        zone_id="zone-a", device_id="esp32-zone-a-01",
        source="MODEL_EXPERIMENT",
        audio_sample_ref="sample-wheat-ambient-001.wav",
        prediction="ambient",
        model_version="nocturne-v1-mini (EXPERIMENTAL)",
        inference_status="unavailable",
        waveform_preview=[0.05, 0.08, 0.06, 0.07, 0.04, 0.06, 0.05, 0.04, 0.06, 0.05, 0.07, 0.06],
        spectrogram_peaks=[{"freq_hz": 440, "db": -42.0}, {"freq_hz": 880, "db": -48.5}],
        review_status="reviewed",
        event_tier="detection",
        notes="Model compatibility test pending. Audio capture working; inference blocked.",
    )

def _acoustic_experimental(score=0.42, zone="zone-a", device="esp32-zone-a-01") -> AcousticEvent:
    # Synthetic waveform envelope points simulating 10-second INMP441 audio window
    wave = [0.08, 0.12, 0.35, 0.65, 0.78, 0.45, 0.22, 0.15, 0.48, 0.82, 0.61, 0.28, 0.18, 0.32, 0.14, 0.09]
    tier = "alert" if score >= 0.50 else "detection"
    return AcousticEvent(
        id=f"evt-{zone}-{device}",
        zone_id=zone, device_id=device,
        source="MODEL_EXPERIMENT",
        audio_sample_ref=f"clip-{zone}-{device}-16k.wav",
        prediction="uncertain — possible_insect_activity" if score >= 0.50 else "ambient — low_confidence_anomaly",
        model_version="nocturne-v1-mini (EXPERIMENTAL)",
        score=score,
        score_semantics=(
            f"EXPERIMENTAL: Raw model confidence {score:.2f} ({'high' if score >= 0.6 else 'medium' if score >= 0.45 else 'low'}). "
            "Not validated against grain-insect recordings. "
            "Cannot distinguish storage insects from ambient noise. "
            "NOT a calibrated infestation probability."
        ),
        confidence_band="high" if score >= 0.65 else "medium" if score >= 0.45 else "low",
        validation_status="unvalidated",
        review_status="unreviewed",
        event_tier=tier,
        inference_status="experimental",
        inference_duration_ms=48,
        waveform_preview=wave,
        spectrogram_peaks=[
            {"freq_hz": 1250, "db": -16.2},
            {"freq_hz": 2400, "db": -22.4},
            {"freq_hz": 3800, "db": -28.1},
        ],
        notes="nocturne-v1-mini output. Human review required before any action.",
    )


def get_demo_data(scenario: str) -> Tuple[List[EnvironmentalReading], List[AcousticEvent], List[Alert], List[Zone]]:
    if scenario == "healthy_storage":
        zones = [z.model_copy(update={"health": "healthy" if z.id != "zone-c" else "unknown"}) for z in BASE_ZONES]
        return _readings_healthy(), [_acoustic_unavailable()], [], zones

    elif scenario == "rising_environmental_risk":
        zones = [z.model_copy(update={"health": {"zone-a": "warning", "zone-c": "unknown"}.get(z.id, "healthy")}) for z in BASE_ZONES]
        alerts = [Alert(
            id="alrt-001", timestamp=ts(5), zone_id="zone-a", device_id="esp32-zone-a-01",
            severity="warning", category="environmental",
            title="CO₂ Trending Up — Zone A",
            message="CO₂ exceeded 700 ppm and rising. Air RH elevated >70%. Rules: co2_trend_threshold, rh_high. Note: air RH is NOT grain moisture content.",
            triggered_by=["co2_trend_threshold", "rh_high"],
            acknowledged=False,
            cleared=False,
            source="SIMULATED",
        )]
        return _readings_rising(), [_acoustic_unavailable()], alerts, zones

    elif scenario == "experimental_acoustic_event":
        alerts = [Alert(
            id="alrt-002", timestamp=ts(0), zone_id="zone-a",
            severity="info", category="acoustic",
            title="⚗️ EXPERIMENTAL Acoustic Anomaly — Zone A",
            message="Model flagged audio anomaly (score=0.42, low confidence). NOT confirmed. EXPERIMENTAL output — no calibrated infestation probability. Review audio evidence before any action.",
            triggered_by=["nocturne_v1_mini_low_confidence"],
            acknowledged=False,
            cleared=False,
            source="MODEL_EXPERIMENT",
        )]
        events = [
            _acoustic_experimental(0.68, "zone-a", "esp32-zone-a-01"),  # Alert tier (sustained chatter)
            _acoustic_experimental(0.38, "zone-a", "esp32-zone-a-02"),  # Detection tier (ambient cue)
        ]
        return _readings_healthy(), events, alerts, BASE_ZONES

    elif scenario == "combined_warning":
        zones = [z.model_copy(update={"health": {"zone-b": "critical", "zone-c": "unknown"}.get(z.id, "healthy")}) for z in BASE_ZONES]
        alerts = [Alert(
            id="alrt-003", timestamp=ts(2), zone_id="zone-b", device_id="esp32-zone-b-01",
            severity="critical", category="combined",
            title="🔴 Combined Risk — Zone B — Inspection Required",
            message="HIGH CO₂ (>1000 ppm) + elevated Air RH (>80%) + EXPERIMENTAL acoustic anomaly (score=0.55). Contributing rules: co2_critical_threshold, rh_critical, nocturne_v1_mini_medium. Inspection required. Do NOT claim confirmed infestation from model score alone.",
            triggered_by=["co2_critical_threshold", "rh_critical", "nocturne_v1_mini_medium"],
            acknowledged=False,
            cleared=False,
            source="SIMULATED",
        )]
        events = [
            _acoustic_experimental(0.74, "zone-b", "esp32-zone-b-01"),  # Alert tier
            _acoustic_experimental(0.32, "zone-a", "esp32-zone-a-01"),  # Detection tier
        ]
        return _readings_combined(), events, alerts, zones

    elif scenario == "return_to_normal":
        alert1 = Alert(
            id="alrt-003", timestamp=ts(120), zone_id="zone-b",
            severity="critical", category="combined",
            title="🔴 Combined Risk — Zone B — RESOLVED",
            message="Post-inspection: ventilation applied. Conditions normalizing.",
            triggered_by=["co2_critical_threshold", "rh_critical"],
            acknowledged=True,
            acknowledged_at=ts(60),
            acknowledged_by="Site Inspector",
            inspection_notes="Inspected Zone B. Ventilation fan opened. No visible infestation found. Conditions improving.",
            cleared=True,
            cleared_at=ts(40),
            cleared_by="Automated Environmental Rule (CO2 < 550 ppm)",
            clear_notes="CO2 dropped to 480 ppm and RH returned to 62%.",
            source="SIMULATED",
        )
        # Demonstrating CLEARED_UNACK (condition resolved by ventilation, but operator has not acknowledged yet)
        alert2 = Alert(
            id="alrt-004", timestamp=ts(90), zone_id="zone-a",
            severity="warning", category="environmental",
            title="CO₂ Spike — Zone A — Auto-Cleared",
            message="Temporary CO₂ spike cleared after purge cycle. Awaiting operator acknowledgment.",
            triggered_by=["co2_trend_threshold"],
            acknowledged=False,
            cleared=True,
            cleared_at=ts(15),
            cleared_by="Environmental Rule Engine",
            clear_notes="Readings stabilized below 500 ppm.",
            source="SIMULATED",
        )
        return _readings_normal(), [_acoustic_unavailable()], [alert1, alert2], BASE_ZONES

    return [], [], [], BASE_ZONES

