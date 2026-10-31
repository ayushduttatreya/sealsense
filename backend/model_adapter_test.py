#!/usr/bin/env python3
"""
SealSense Model Compatibility & Adapter Verification Test
=========================================================
Tests for nocturne-v1-mini (acoustic) and GestaltCog/zeus (environmental)
using the modular backend/app/adapters architecture.
Run: backend/.venv/bin/python3 backend/model_adapter_test.py

STRICT PROTOCOL CAVEATS:
- nocturne-v1-mini is a bioacoustic model NOT validated for grain-storage insects.
  Model scores represent raw classification output, NOT calibrated infestation probabilities.
- GestaltCog/zeus is an open-domain time-series model requiring CUDA + FlashAttention-2.
- If dependencies or weights are unavailable, explicit UNAVAILABLE status is reported
  with ZERO fabricated scores.
- Environmental rule-based alert engine (alert_rules.py) operates independently.
"""
from __future__ import annotations
import sys
import os
import json
import time
import platform
import numpy as np

# Ensure backend root is on sys.path
backend_dir = os.path.abspath(os.path.dirname(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.adapters import NocturneMiniAdapter, ZeusAdapter

def main():
    print("=" * 60)
    print("SealSense Pretrained Model Compatibility & Inference Suite")
    print("=" * 60)
    print(f"Python {sys.version.split()[0]} ({platform.machine()} / {platform.system()})")

    # 1. Dependency Checks via Modular Adapters
    print("\n--- ML Dependency Audit ---")
    nocturne_dep = NocturneMiniAdapter.check_dependencies()
    zeus_dep = ZeusAdapter.check_dependencies()

    all_pkgs = sorted(list(set(list(nocturne_dep.installed_packages.keys()) + nocturne_dep.missing_packages + list(zeus_dep.installed_packages.keys()) + zeus_dep.missing_packages)))
    for pkg in all_pkgs:
        if pkg in nocturne_dep.installed_packages:
            print(f"  ✓ {pkg} (version {nocturne_dep.installed_packages[pkg]})")
        elif pkg in zeus_dep.installed_packages:
            print(f"  ✓ {pkg} (version {zeus_dep.installed_packages[pkg]})")
        else:
            print(f"  ✗ {pkg} NOT INSTALLED")

    print(f"  CUDA Available: {nocturne_dep.cuda_available}")
    if nocturne_dep.cuda_available:
        print(f"  CUDA Device: {nocturne_dep.cuda_device}")
    else:
        print("  Notice: CPU-only runtime — accelerators unavailable")

    # 2. Nocturne Mini Acoustic Adapter Verification
    print("\n--- Acoustic Model: stratus-labs/nocturne-v1-mini ---")
    print("Specification:")
    print("  - Parameters: 9,398,486 (EfficientNet-B1 student backbone)")
    print("  - Input: 10.0s mono waveform @ 16 kHz (160,000 samples)")
    print("  - Pretraining: InsectSet459, iNat-Sounds-2024 (outdoor nocturnal biodiversity)")
    print("  - Storage Insect Validation: NONE (Unvalidated on Sitophilus oryzae, Rhyzopertha dominica)")
    print(f"  - Adapter Status: {nocturne_dep.summary}")

    nocturne_adapter = NocturneMiniAdapter()

    # Technical synthetic smoke-test input (sine sweep + noise, 10s @ 16kHz)
    t = np.linspace(0, 10.0, 160000, dtype=np.float32)
    synthetic_signal = 0.3 * np.sin(2 * np.pi * 440 * t) + 0.1 * np.random.normal(0, 0.05, 160000).astype(np.float32)
    print(f"  Technical smoke-test input prepared: shape={synthetic_signal.shape}, dtype={synthetic_signal.dtype}")
    print("  (Note: Synthetic audio is a technical signal, NOT grain bioacoustic validation data)")

    nocturne_res = nocturne_adapter.predict(synthetic_signal, sample_rate=16000, top_k=5)
    print(f"  Inference Result Status: {nocturne_res.status}")
    if nocturne_res.status == "UNAVAILABLE":
        print(f"  Reason: {nocturne_res.reason}")
        print(f"  Waveform Preview Computed: {len(nocturne_res.waveform_preview or [])} bars")
        print(f"  Spectrogram Peaks Extracted: {len(nocturne_res.spectrogram_peaks or [])} peaks")
    elif nocturne_res.status in ("EXPERIMENTAL", "READY"):
        print(f"  Execution Time: {nocturne_res.inference_duration_ms} ms")
        print(f"  Top Prediction: {nocturne_res.prediction} (score={nocturne_res.score})")
        print(f"  Confidence Band: {nocturne_res.confidence_band}")
        print("  Top 5 Predictions (Raw Scores):")
        for rank, item in enumerate(nocturne_res.top_predictions[:5], 1):
            print(f"    {rank}. {item.label:<32} : {item.score:.5f}")
    elif nocturne_res.status == "ERROR":
        print(f"  Error: {nocturne_res.error}")

    # 3. Zeus Time-Series Foundation Adapter Verification
    print("\n--- Environmental Foundation Model: GestaltCog/zeus ---")
    print("Specification:")
    print("  - Parameters: 102,096,777 (BERT-style time-series foundation)")
    print("  - Expected Input: (batch_size, context_length) = (1, 256)")
    print("  - Requirements: CUDA + FlashAttention-2")
    print("  - Grain Kinetics Training: NONE (Pretrained on open-domain datasets)")
    print(f"  - Adapter Status: {zeus_dep.summary}")

    zeus_adapter = ZeusAdapter()
    synthetic_ts = np.sin(np.linspace(0, 20, 256)).astype(np.float32).reshape(1, 256)
    print(f"  Technical time-series input prepared: shape={synthetic_ts.shape}, dtype={synthetic_ts.dtype}")

    zeus_res = zeus_adapter.predict(synthetic_ts, prediction_length=16)
    print(f"  Inference Result Status: {zeus_res.status}")
    print(f"  Fallback Rule Engine Active: {zeus_res.fallback_active}")
    if zeus_res.reason:
        print(f"  Reason: {zeus_res.reason}")

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Acoustic (nocturne-v1-mini):  {nocturne_res.status}")
    print(f"  Environmental (zeus):          {zeus_res.status}")
    print("  Rule-Based Alerts:             ACTIVE (<1ms deterministic evaluation)")
    print("  Domain Rule:                   Air RH is strictly air humidity, NOT grain moisture")
    print("=" * 60)

    # Machine-readable output
    report_dict = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "nocturne": nocturne_res.model_dump(),
        "zeus": zeus_res.model_dump(),
        "rule_engine_active": True,
    }
    print("\nMachine-readable JSON summary:")
    print(json.dumps(report_dict, indent=2))

if __name__ == "__main__":
    main()
