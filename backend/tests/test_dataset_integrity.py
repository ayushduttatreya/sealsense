"""
Unit & Integration Tests: Dataset Integrity, Signal Analysis & Evaluation Safeguards
=====================================================================================
Covers:
1. Transducer metadata preservation: ensures transducer types, frequency ranges, and
   laboratory setups are retained and never lost through 16 kHz resampling.
2. Recording-domain validation: tests domains ("airborne_microphone", "accelerometer",
   "piezoelectric", "pvdf", "ultrasonic_transducer", "synthetic_simulation", "unknown").
3. Evaluation exclusion of incompatible references: ensures contact sensors are excluded
   from airborne microphone classifier validation sets.
4. Synthetic data exclusion: verifies all synthetic simulations are barred from scientific evaluation.
5. Signal feature calculations: verifies RMS, Peak, Centroid, Bandwidth, Flatness, ZCR,
   Band-energy distribution, and Hilbert/MAD transient click detection.
6. Reproducible simulation: tests deterministic seed behavior.
7. Existing inference compatibility: verifies Nocturne Mini inference integration.
"""
from __future__ import annotations

import io
import math
import os
import sys
import tempfile
import unittest
import numpy as np

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.reference_dataset import (
    BUG_BYTES_CATALOG, list_reference_catalog, get_catalog_item,
    get_reference_file_path
)
from app.signal_analysis import analyze_signal, analyze_wav_bytes
from app.evaluation import evaluate_dataset_samples
from app.synthetic_generator import generate_synthetic_impulse_wav
from app.adapters.nocturne import NocturneMiniAdapter
from app.audio_storage import validate_wav_bytes, compute_sha256
from app.database import init_db, get_db, CREATE_SAMPLES


class TestDatasetIntegrityAndSignalAnalysis(unittest.TestCase):

    def test_transducer_metadata_preservation(self):
        """Verifies that public reference recordings retain exact transducer, frequency, and setup metadata."""
        catalog = list_reference_catalog()
        self.assertGreaterEqual(len(catalog), 7)

        for item in catalog:
            # Verified fields
            self.assertIn("transducer_type", item)
            self.assertIn("recording_domain", item)
            self.assertIn("frequency_range", item)
            self.assertIn("laboratory_setup", item)
            if item.get("is_locally_available"):
                self.assertIsNotNone(item.get("sha256_hash"))
                self.assertEqual(len(item["sha256_hash"]), 64)

            # Transducer to domain consistency
            domain = item["recording_domain"]
            transducer = item["transducer_type"].lower()
            if "accelerometer" in transducer:
                self.assertEqual(domain, "accelerometer")
            elif "pvdf" in transducer:
                self.assertEqual(domain, "pvdf")
            elif "piezo" in transducer:
                self.assertEqual(domain, "piezoelectric")
            elif "ultrasonic" in transducer:
                self.assertEqual(domain, "ultrasonic_transducer")

    def test_recording_domain_validation(self):
        """Validates allowable recording domain values and classification."""
        valid_domains = {
            "airborne_microphone",
            "accelerometer",
            "piezoelectric",
            "pvdf",
            "ultrasonic_transducer",
            "synthetic_simulation",
            "unknown",
        }
        for item in list_reference_catalog():
            self.assertIn(item["recording_domain"], valid_domains)

    def test_evaluation_exclusion_of_incompatible_references(self):
        """Verifies that sensor-incompatible contact references are excluded from airborne microphone evaluations."""
        # Simulated laboratory recordings of confirmed pests via contact sensors
        samples = [
            {
                "id": "ref-accel-1",
                "filename": "accelrw.wav",
                "input_source": "public_reference",
                "recording_domain": "accelerometer",
                "transducer_type": "Brüel & Kjær 4370 Accelerometer",
                "ground_truth_label": "TARGET_PEST_OBSERVED",
                "score": 0.089,
                "is_synthetic": 0,
            },
            {
                "id": "ref-pvdf-1",
                "filename": "pvdfrw1.wav",
                "input_source": "public_reference",
                "recording_domain": "pvdf",
                "transducer_type": "PVDF Piezoelectric Film Sensor",
                "ground_truth_label": "TARGET_PEST_OBSERVED",
                "score": 0.076,
                "is_synthetic": 0,
            },
            {
                "id": "ref-piezo-1",
                "filename": "piezorw1.wav",
                "input_source": "public_reference",
                "recording_domain": "piezoelectric",
                "transducer_type": "Piezoelectric Disk Transducer",
                "ground_truth_label": "TARGET_PEST_OBSERVED",
                "score": 0.091,
                "is_synthetic": 0,
            },
            {
                "id": "ref-ultra-1",
                "filename": "w30khzrw1.wav",
                "input_source": "public_reference",
                "recording_domain": "ultrasonic_transducer",
                "transducer_type": "Ultrasonic Sensor (30 kHz Peak)",
                "ground_truth_label": "TARGET_PEST_OBSERVED",
                "score": 0.045,
                "is_synthetic": 0,
            },
        ]

        report = evaluate_dataset_samples(
            samples,
            anomaly_threshold=0.05,
            verify_files_on_disk=False,
            target_domain="airborne_microphone",
        )

        # All 4 samples have valid biological provenance, but 0 are eligible for airborne mic validation
        self.assertEqual(report.total_samples, 4)
        self.assertEqual(report.eligible_samples, 0)
        self.assertEqual(report.excluded_samples, 4)
        self.assertEqual(report.exclusion_breakdown["sensor_domain_incompatible"], 4)
        self.assertEqual(report.validation_readiness, "INSUFFICIENT VALIDATION DATA")
        self.assertIsNone(report.anomaly_metrics, "Metrics must be suppressed when valid evaluation set is insufficient")

    def test_synthetic_data_exclusion(self):
        """Verifies that all synthetic simulation signals are barred from scientific performance metrics."""
        samples = [
            {
                "id": "sim-001",
                "filename": "synthetic_sim_42.wav",
                "input_source": "synthetic",
                "recording_domain": "synthetic_simulation",
                "is_synthetic": 1,
                "ground_truth_label": "TARGET_PEST_OBSERVED",
                "score": 0.12,
            },
            {
                "id": "sim-002",
                "filename": "synthetic_chirp.wav",
                "input_source": "synthetic",
                "recording_domain": "synthetic_simulation",
                "is_synthetic": 1,
                "ground_truth_label": "NO_TARGET_PEST_OBSERVED",
                "score": 0.02,
            },
        ]

        report = evaluate_dataset_samples(
            samples,
            anomaly_threshold=0.05,
            verify_files_on_disk=False,
            target_domain="airborne_microphone",
        )

        self.assertEqual(report.total_samples, 2)
        self.assertEqual(report.eligible_samples, 0)
        self.assertEqual(report.excluded_samples, 2)
        self.assertEqual(report.exclusion_breakdown["synthetic_simulation"], 2)
        self.assertEqual(report.validation_readiness, "INSUFFICIENT VALIDATION DATA")

    def test_signal_feature_calculations(self):
        """Verifies physical acoustic signal analysis calculation correctness."""
        # 1. Pure sine wave at 1000 Hz, duration 1.0s, amplitude 0.5
        sample_rate = 16000
        duration = 1.0
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False, dtype=np.float32)
        sine_audio = (0.5 * np.sin(2 * np.pi * 1000.0 * t)).astype(np.float32)

        res = analyze_signal(sine_audio, sample_rate)

        # RMS should be approx 0.5 / sqrt(2) = 0.3535
        expected_rms = 0.5 / math.sqrt(2)
        self.assertAlmostEqual(res["rms_energy"], expected_rms, places=2)
        self.assertAlmostEqual(res["peak_amplitude"], 0.5, places=2)

        # Spectral centroid should be close to 1000 Hz
        self.assertAlmostEqual(res["spectral_centroid_hz"], 1000.0, delta=100.0)

        # Spectral flatness for pure tone is very low (< 0.05)
        self.assertLess(res["spectral_flatness"], 0.05)

        # Zero-crossing rate for 1000 Hz in 16 kHz: 2000 crossings/sec -> 0.125
        self.assertAlmostEqual(res["zero_crossing_rate"], 0.125, delta=0.02)
        self.assertAlmostEqual(res["zero_crossings_per_sec"], 2000.0, delta=200.0)

        # Band energy distribution: 1k-4k band should contain most energy
        bands = res["band_energy_distribution"]
        self.assertGreater(bands["band_1k_4k_pct"], 80.0)

        # 2. Synthetic impulses (bursts)
        impulse_audio = np.zeros(sample_rate, dtype=np.float32)
        # Add 10 clear high-frequency spikes
        for click_pos in range(1000, 15000, 1400):
            impulse_audio[click_pos : click_pos + 10] = 0.8 * np.sin(2 * np.pi * 2500.0 * np.arange(10) / sample_rate)

        res_impulse = analyze_signal(impulse_audio, sample_rate)
        self.assertGreaterEqual(res_impulse["transient_click_count"], 8)
        self.assertAlmostEqual(res_impulse["transient_clicks_per_sec"], 10.0, delta=3.0)

    def test_reproducible_simulation(self):
        """Verifies synthetic simulation repeatability using fixed seeds."""
        wav1 = generate_synthetic_impulse_wav(impulse_rate=14.0, amplitude=0.6, noise_level=0.02, duration_sec=5.0, seed=101)
        wav2 = generate_synthetic_impulse_wav(impulse_rate=14.0, amplitude=0.6, noise_level=0.02, duration_sec=5.0, seed=101)
        wav3 = generate_synthetic_impulse_wav(impulse_rate=14.0, amplitude=0.6, noise_level=0.02, duration_sec=5.0, seed=202)

        self.assertEqual(wav1, wav2, "Same seed must yield identical WAV bytes")
        self.assertNotEqual(wav1, wav3, "Different seed must yield different WAV bytes")

        # Verify WAV validity and physical signal analysis on generated simulation
        ch, rate, dur = validate_wav_bytes(wav1)
        self.assertEqual(ch, 1)
        self.assertEqual(rate, 16000)
        self.assertAlmostEqual(dur, 5.0, places=1)

        analysis = analyze_wav_bytes(wav1)
        self.assertGreater(analysis["transient_click_count"], 20)
        self.assertGreater(analysis["rms_energy"], 0.0)

    def test_existing_inference_compatibility(self):
        """Verifies that Nocturne Mini adapter continues to operate and attaches signal metadata."""
        adapter = NocturneMiniAdapter()
        # Generate short 2s audio
        wav_bytes = generate_synthetic_impulse_wav(impulse_rate=10.0, amplitude=0.5, duration_sec=2.0, seed=42)
        res = adapter.predict_wav_bytes(wav_bytes, filename="test_inference.wav")

        self.assertIn(res.status, ("READY", "EXPERIMENTAL"))
        self.assertEqual(len(res.top_predictions), 5)
        self.assertIsNotNone(res.waveform_preview)
        self.assertEqual(res.audio_sample_rate, 16000)
        self.assertEqual(res.audio_duration_sec, 10.0)  # Standardized to 10s window


if __name__ == "__main__":
    unittest.main()
