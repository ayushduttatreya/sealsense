"""
Configurable rule-based alert engine.
All thresholds are documented and adjustable.
Environmental alerts state which readings/rules triggered them.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
from .models import EnvironmentalReading, Alert

# ─── Thresholds (edit these to tune) ──────────────────────────────
CO2_WARN_PPM = 700
CO2_CRITICAL_PPM = 1200
CO2_TREND_WARN_DELTA = 200      # ppm rise over last 3 readings
TEMP_WARN_C = 25
TEMP_CRITICAL_C = 30
RH_WARN_PCT = 70
RH_CRITICAL_PCT = 80


def evaluate_environmental(
    readings: List[EnvironmentalReading],
    zone_id: str,
    device_id: str,
) -> List[Alert]:
    """
    Evaluate a list of recent readings and return triggered alerts.
    Each alert includes which rule(s) triggered it.
    """
    alerts: List[Alert] = []
    if not readings:
        return alerts

    latest = readings[-1]
    co2 = latest.co2_ppm
    temp = latest.temperature_c
    rh = latest.relative_humidity_pct

    triggered: List[str] = []
    severity = "info"
    parts: List[str] = []

    # CO2 level
    if co2 is not None and latest.co2_valid:
        if co2 >= CO2_CRITICAL_PPM:
            triggered.append("co2_critical_threshold")
            severity = "critical"
            parts.append(f"CO₂ critical: {co2:.0f} ppm (threshold {CO2_CRITICAL_PPM})")
        elif co2 >= CO2_WARN_PPM:
            triggered.append("co2_warn_threshold")
            if severity == "info":
                severity = "warning"
            parts.append(f"CO₂ elevated: {co2:.0f} ppm (threshold {CO2_WARN_PPM})")

    # CO2 trend
    if len(readings) >= 3 and all(r.co2_ppm is not None and r.co2_valid for r in readings[-3:]):
        delta = readings[-1].co2_ppm - readings[-3].co2_ppm  # type: ignore[operator]
        if delta >= CO2_TREND_WARN_DELTA:
            triggered.append("co2_trend_threshold")
            if severity == "info":
                severity = "warning"
            parts.append(f"CO₂ rising: +{delta:.0f} ppm over last 3 readings")

    # Temperature
    if temp is not None and latest.temp_valid:
        if temp >= TEMP_CRITICAL_C:
            triggered.append("temp_critical")
            severity = "critical"
            parts.append(f"Temperature critical: {temp:.1f}°C (threshold {TEMP_CRITICAL_C})")
        elif temp >= TEMP_WARN_C:
            triggered.append("temp_warn")
            if severity == "info":
                severity = "warning"
            parts.append(f"Temperature elevated: {temp:.1f}°C (threshold {TEMP_WARN_C})")

    # Air RH (NOT grain moisture)
    if rh is not None and latest.rh_valid:
        if rh >= RH_CRITICAL_PCT:
            triggered.append("rh_critical")
            severity = "critical"
            parts.append(f"Air RH critical: {rh:.1f}% (threshold {RH_CRITICAL_PCT})")
        elif rh >= RH_WARN_PCT:
            triggered.append("rh_high")
            if severity == "info":
                severity = "warning"
            parts.append(f"Air RH elevated: {rh:.1f}% (threshold {RH_WARN_PCT})")

    if triggered:
        message = (
            "Environmental rule triggered. " + " | ".join(parts) +
            ". Note: air RH is air relative humidity, NOT grain moisture content."
        )
        alerts.append(Alert(
            zone_id=zone_id,
            device_id=device_id,
            severity=severity,  # type: ignore[arg-type]
            category="environmental",
            title=f"Environmental Alert — {zone_id}",
            message=message,
            triggered_by=triggered,
            source="REAL" if latest.source == "REAL" else "SIMULATED",
        ))

    return alerts
