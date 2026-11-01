"""
SealSense Machine Learning Pipeline Test Suite
=============================================
Tests:
1. Feature extraction (22 physical features + 64-band Log-Mel spectrograms)
2. GroupKFold session isolation and dataset window slicing
3. Baseline adapter predictions on physical audio
4. Benchmark endpoint (/api/inference/acoustic/benchmark)
5. Upload integration attaching domain baseline inference
"""

import io
import os
import sys
import unittest

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import numpy as np
import scipy.io.wavfile as wavfile
from fastapi.testclient import TestClient

from app.main import app
from app.ml.features import extract_features, extract_feature_vector, extract_log_mel_spectrogram, FEATURE_NAMES
from app.ml.dataset import load_dataset, AudioSampleWindow, CLASS_NAMES
from app.adapters.baseline import GrainAcousticBaselineAdapter


class TestMLPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        # Generate a 1-second synthetic 16 kHz test audio (with transient clicks)
        sr = 16000
        t = np.linspace(0, 1.0, sr, endpoint=False)
        audio = 0.05 * np.sin(2 * np.pi * 440 * t)
        # Inject sharp transients
        for idx in [2000, 5000, 8000, 11000, 14000]:
            audio[idx : idx + 30] += 0.8 * np.sin(2 * np.pi * 3200 * t[:30])
        cls.test_audio_16k = audio.astype(np.float32)

    def test_feature_extraction_dimension_and_keys(self):
        feat_dict = extract_features(self.test_audio_16k, sample_rate=16000)
        feat_vec = extract_feature_vector(self.test_audio_16k, sample_rate=16000)
        self.assertEqual(len(feat_vec), 22, "Feature vector must contain exactly 22 physical acoustic features")
        self.assertEqual(len(FEATURE_NAMES), 22)
        self.assertIn("rms", feat_dict)
        self.assertIn("spectral_centroid_hz", feat_dict)
        self.assertIn("spectral_flatness", feat_dict)
        self.assertIn("crest_factor", feat_dict)
        self.assertIn("impulse_count", feat_dict)
        self.assertIn("impulse_rate_hz", feat_dict)
        self.assertGreater(feat_dict["impulse_count"], 0, "Synthesized transients should be detected by MAD threshold")

    def test_log_mel_spectrogram_shape(self):
        mel_spec = extract_log_mel_spectrogram(self.test_audio_16k, sample_rate=16000, n_mels=64)
        self.assertEqual(mel_spec.shape[0], 64, "Log-Mel spectrogram must have 64 frequency bins")
        self.assertEqual(mel_spec.ndim, 2, "Log-Mel spectrogram must be 2-dimensional (mels x time)")

    def test_dataset_loading_and_session_grouping(self):
        windows = load_dataset()
        self.assertGreater(len(windows), 50, "Should generate authentic dataset windows")
        sessions = set(w.session_id for w in windows)
        self.assertGreaterEqual(len(sessions), 5, "Dataset must have multiple independent sessions for GroupKFold")

        # Verify no missing labels
        valid_classes = set(CLASS_NAMES)
        for w in windows:
            self.assertIn(w.label, valid_classes)
            self.assertEqual(len(w.audio), 16000)

    def test_baseline_adapter_initialization_and_inference(self):
        adapter = GrainAcousticBaselineAdapter()
        res = adapter.predict(self.test_audio_16k, sample_rate=16000)
        self.assertEqual(res["status"], "READY")
        self.assertIn(res["prediction"], ["insect_activity", "machinery_ventilation", "grain_handling", "background_noise"])
        self.assertGreaterEqual(res["score"], 0.0)
        self.assertLessEqual(res["score"], 1.0)
        self.assertIn(res["confidence_band"], ["low", "medium", "high", "uncertain"])
        self.assertEqual(len(res["class_probabilities"]), 4)
        self.assertAlmostEqual(sum(res["class_probabilities"].values()), 1.0, places=2)

    def test_benchmark_api_endpoint(self):
        response = self.client.get("/api/inference/acoustic/benchmark")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("models", data)
        self.assertIn("random_forest", data["models"])
        self.assertIn("small_cnn", data["models"])
        self.assertIn("nocturne_mini_comparison", data)
        self.assertIn("scientific_disclaimer", data)
        self.assertIn("dataset_summary", data)

        # Verify random forest metrics structure
        rf = data["models"]["random_forest"]
        self.assertIn("macro_f1", rf)
        self.assertIn("per_class", rf)
        self.assertIn("insect_activity", rf["per_class"])
        self.assertGreater(rf["per_class"]["insect_activity"]["f1"], 0.70)
        self.assertIn("false_alarm_rate_per_hour", rf)

    def test_acoustic_upload_includes_domain_prediction(self):
        # Create in-memory 10s WAV
        sr = 16000
        samples = (self.test_audio_16k * 32767).astype(np.int16)
        samples_10s = np.tile(samples, 10)
        buf = io.BytesIO()
        wavfile.write(buf, sr, samples_10s)
        buf.seek(0)

        response = self.client.post(
            "/api/inference/acoustic/upload",
            files={"file": ("test_clicks.wav", buf.read(), "audio/wav")},
            data={"zone_id": "ZONE-A", "device_id": "ESP32-ZONE-A-01", "save_event": "false", "retain_sample": "false"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("domain_prediction", data)
        self.assertIn("domain_score", data)
        self.assertIn("domain_confidence_band", data)
        self.assertIn("domain_probabilities", data)
        self.assertEqual(data["domain_model_id"], "sealsense-rf-baseline-v1")


if __name__ == "__main__":
    unittest.main()
