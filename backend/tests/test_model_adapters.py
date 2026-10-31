"""
Comprehensive Unit Tests for SealSense Model Adapters
=====================================================
Tests:
1. Lazy loading & non-blocking import behavior
2. Dependency audit & missing package reporting
3. Audio preprocessing (10s @ 16 kHz = 160,000 samples, mono downmix, normalization)
4. Waveform envelope preview & spectrogram peak extraction
5. Malformed input handling (empty, NaN/Inf, 3D tensor)
6. Unavailable weights and environment blockers handling
7. Zeus time-series validation & hardware constraint checks (CUDA/FlashAttention)
8. Zero score fabrication verification (truthful status)
9. FastAPI model status and inference endpoint integration
"""
from __future__ import annotations
import sys
import os
import unittest
import numpy as np

# Ensure backend root is on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.adapters import NocturneMiniAdapter, ZeusAdapter
from app.adapters.base import AcousticInferenceResult, ZeusInferenceResult, DependencyReport


class TestModelAdapters(unittest.TestCase):

    def test_lazy_loading(self):
        """Adapter instantiation must be immediate and lazy without loading weights."""
        adapter = NocturneMiniAdapter()
        self.assertFalse(adapter._is_loaded, "Model should not be loaded on instantiation")
        self.assertIsNone(adapter._model, "Model instance should be None initially")

        zeus = ZeusAdapter()
        self.assertFalse(zeus._is_loaded, "Zeus should not be loaded on instantiation")
        self.assertIsNone(zeus._model, "Zeus model instance should be None initially")

    def test_dependency_audit(self):
        """Dependency check returns structured report with missing packages and instructions."""
        nocturne_report = NocturneMiniAdapter.check_dependencies()
        self.assertIsInstance(nocturne_report, DependencyReport)
        self.assertEqual(nocturne_report.adapter_name, "stratus-labs/nocturne-v1-mini")
        self.assertIn("installed_packages", nocturne_report.model_dump())
        self.assertIn("missing_packages", nocturne_report.model_dump())

        zeus_report = ZeusAdapter.check_dependencies()
        self.assertIsInstance(zeus_report, DependencyReport)
        self.assertEqual(zeus_report.adapter_name, "GestaltCog/zeus")

    def test_audio_preprocessing_length_and_shaping(self):
        """Audio is standardized to exactly 160,000 samples (10.0s @ 16 kHz)."""
        adapter = NocturneMiniAdapter()

        # 1. Short audio (1.0s = 16,000 samples) -> padded to 160,000
        short_audio = np.ones(16000, dtype=np.float32) * 0.2
        proc, bars, peaks = adapter.preprocess_audio(short_audio, sample_rate=16000)
        self.assertEqual(len(proc), 160000, "Should pad short audio to 160,000 samples")
        self.assertEqual(len(bars), 16, "Should generate 16 waveform preview bars")
        self.assertTrue(len(peaks) > 0, "Should extract spectrogram peaks")

        # 2. Long audio (15.0s = 240,000 samples) -> truncated to 160,000
        long_audio = np.ones(240000, dtype=np.float32) * 0.1
        proc_long, _, _ = adapter.preprocess_audio(long_audio, sample_rate=16000)
        self.assertEqual(len(proc_long), 160000, "Should truncate long audio to 160,000 samples")

        # 3. Exact 10.0s audio
        exact_audio = np.zeros(160000, dtype=np.float32)
        proc_exact, _, _ = adapter.preprocess_audio(exact_audio, sample_rate=16000)
        self.assertEqual(len(proc_exact), 160000)

    def test_multichannel_downmix_to_mono(self):
        """Multichannel 2D stereo array is downmixed to 1D mono."""
        adapter = NocturneMiniAdapter()
        stereo_audio = np.random.randn(2, 20000).astype(np.float32)
        proc, _, _ = adapter.preprocess_audio(stereo_audio, sample_rate=16000)
        self.assertEqual(proc.ndim, 1, "Processed audio must be 1D mono")
        self.assertEqual(len(proc), 160000)

    def test_audio_normalization(self):
        """Audio exceeding [-1.0, 1.0] peak amplitude is normalized."""
        adapter = NocturneMiniAdapter()
        loud_audio = np.array([2.5, -3.0, 1.2, 0.0] * 4000, dtype=np.float32)
        proc, _, _ = adapter.preprocess_audio(loud_audio, sample_rate=16000)
        self.assertLessEqual(np.max(np.abs(proc)), 1.0, "Audio peak must not exceed 1.0")

    def test_malformed_audio_rejection(self):
        """Malformed inputs (empty, NaN, Inf, 3D tensor) are cleanly rejected."""
        adapter = NocturneMiniAdapter()

        # Empty array
        with self.assertRaises(ValueError):
            adapter.preprocess_audio(np.array([], dtype=np.float32))

        # NaN values
        nan_audio = np.array([0.1, np.nan, 0.3], dtype=np.float32)
        with self.assertRaises(ValueError):
            adapter.preprocess_audio(nan_audio)

        # Inf values
        inf_audio = np.array([0.1, np.inf, 0.3], dtype=np.float32)
        with self.assertRaises(ValueError):
            adapter.preprocess_audio(inf_audio)

        # 3D tensor
        tensor3d = np.zeros((2, 2, 1000), dtype=np.float32)
        with self.assertRaises(ValueError):
            adapter.preprocess_audio(tensor3d)

    def test_predict_malformed_input_returns_error_result(self):
        """predict() handles malformed input by returning an ERROR result rather than crashing."""
        adapter = NocturneMiniAdapter()
        res = adapter.predict(np.array([], dtype=np.float32))
        self.assertEqual(res.status, "ERROR")
        self.assertIn("Malformed audio input", res.error)

    def test_nocturne_unavailable_dependencies_handling(self):
        """When ML dependencies are absent, returns UNAVAILABLE without fabricated scores."""
        adapter = NocturneMiniAdapter()
        synthetic_signal = np.sin(np.linspace(0, 100, 160000)).astype(np.float32)
        res = adapter.predict(synthetic_signal, sample_rate=16000)

        self.assertIsInstance(res, AcousticInferenceResult)
        if not adapter.check_dependencies().is_available:
            self.assertEqual(res.status, "UNAVAILABLE")
            self.assertIsNone(res.score, "Must NEVER fabricate prediction score when model is unavailable")
            self.assertEqual(len(res.top_predictions), 0)
            self.assertIsNotNone(res.waveform_preview, "Should extract physical waveform preview even if model is unavailable")
            self.assertEqual(len(res.waveform_preview), 16)

    def test_nocturne_genuine_inference(self):
        """When ML dependencies and weights are available, verifies genuine model forward pass and predictions."""
        adapter = NocturneMiniAdapter()
        if not adapter.check_dependencies().is_available:
            self.skipTest("ML dependencies not installed in test environment")

        # 10.0s synthetic chirp signal
        t = np.linspace(0, 10.0, 160000, dtype=np.float32)
        synthetic_audio = 0.2 * np.sin(2 * np.pi * 440 * t)
        res = adapter.predict(synthetic_audio, sample_rate=16000, top_k=5)

        self.assertIsInstance(res, AcousticInferenceResult)
        self.assertEqual(res.status, "EXPERIMENTAL")
        self.assertIsNotNone(res.score)
        self.assertIsInstance(res.score, float)
        self.assertEqual(len(res.top_predictions), 5)
        self.assertGreater(res.inference_duration_ms, 0)
        self.assertEqual(res.model_id, "stratus-labs/nocturne-v1-mini")
        self.assertIn(res.confidence_band, ("low", "medium", "high"))

    def test_zeus_input_validation(self):
        """Zeus input sequence validation handles 1D, 2D, and rejects invalid shapes/values."""
        adapter = ZeusAdapter()

        # Valid 1D -> reshaped to (1, N)
        valid_1d = np.ones(256, dtype=np.float32)
        shaped = adapter.validate_input(valid_1d)
        self.assertEqual(shaped.shape, (1, 256))

        # Valid 2D
        valid_2d = np.ones((2, 256), dtype=np.float32)
        shaped_2d = adapter.validate_input(valid_2d)
        self.assertEqual(shaped_2d.shape, (2, 256))

        # Empty
        with self.assertRaises(ValueError):
            adapter.validate_input(np.array([], dtype=np.float32))

        # NaN
        with self.assertRaises(ValueError):
            adapter.validate_input(np.array([1.0, np.nan, 2.0], dtype=np.float32))

        # 3D
        with self.assertRaises(ValueError):
            adapter.validate_input(np.zeros((1, 2, 3), dtype=np.float32))

    def test_zeus_predict_hardware_blocker_handling(self):
        """Zeus reports honest UNAVAILABLE status and keeps rule-based fallback active."""
        adapter = ZeusAdapter()
        ts_data = np.ones(256, dtype=np.float32)
        res = adapter.predict(ts_data)

        self.assertIsInstance(res, ZeusInferenceResult)
        self.assertEqual(res.status, "UNAVAILABLE")
        self.assertTrue(res.fallback_active, "Fallback rule engine must remain active")
        self.assertIsNone(res.forecast, "Must NOT fabricate forecast values when model is blocked")
        self.assertIn("FlashAttention", res.limitations)

    def test_wav_ingestion_exact_padded_truncated(self):
        """WAV ingestion correctly downmixes, resamples, and shapes windows to 10.0s."""
        import io
        import soundfile as sf
        adapter = NocturneMiniAdapter()

        # 1. Exact 10.0s mono 16 kHz
        buf_exact = io.BytesIO()
        t10 = np.linspace(0, 10.0, 160000, dtype=np.float32)
        sig10 = 0.2 * np.sin(2 * np.pi * 440 * t10)
        sf.write(buf_exact, sig10, 16000, format="WAV")
        audio, meta = adapter.ingest_wav_bytes(buf_exact.getvalue())
        self.assertEqual(len(audio), 160000)
        self.assertEqual(meta["window_mode"], "exact")
        self.assertEqual(meta["original_sample_rate"], 16000)
        self.assertEqual(meta["original_channels"], 1)

        # 2. Short 2.0s stereo 44.1 kHz -> padded
        buf_short = io.BytesIO()
        t2 = np.linspace(0, 2.0, 44100 * 2, dtype=np.float32)
        stereo_sig = np.column_stack([0.3 * np.sin(2 * np.pi * 300 * t2), 0.3 * np.cos(2 * np.pi * 300 * t2)])
        sf.write(buf_short, stereo_sig, 44100, format="WAV")
        audio_short, meta_short = adapter.ingest_wav_bytes(buf_short.getvalue())
        self.assertEqual(len(audio_short), 160000)
        self.assertEqual(meta_short["window_mode"], "padded")
        self.assertEqual(meta_short["original_channels"], 2)
        self.assertEqual(meta_short["original_sample_rate"], 44100)
        self.assertAlmostEqual(meta_short["original_duration_sec"], 2.0, delta=0.1)

        # 3. Long 15.0s mono 48 kHz -> truncated
        buf_long = io.BytesIO()
        t15 = np.linspace(0, 15.0, 48000 * 15, dtype=np.float32)
        sf.write(buf_long, 0.1 * np.sin(2 * np.pi * 500 * t15), 48000, format="WAV")
        audio_long, meta_long = adapter.ingest_wav_bytes(buf_long.getvalue())
        self.assertEqual(len(audio_long), 160000)
        self.assertEqual(meta_long["window_mode"], "truncated")
        self.assertAlmostEqual(meta_long["original_duration_sec"], 15.0, delta=0.1)

    def test_wav_ingestion_rejection_rules(self):
        """WAV ingestion strictly rejects non-WAV headers, empty payloads, and corrupt bytes."""
        adapter = NocturneMiniAdapter()

        # Empty payload
        with self.assertRaises(ValueError) as ctx:
            adapter.ingest_wav_bytes(b"")
        self.assertIn("Empty audio upload", str(ctx.exception))

        # Too small (< 44 bytes)
        with self.assertRaises(ValueError) as ctx:
            adapter.ingest_wav_bytes(b"RIFFshort")
        self.assertIn("smaller than a 44-byte", str(ctx.exception))

        # Fake non-WAV content (even if called sound.wav)
        fake_wav = b"THIS_IS_DEFINITELY_NOT_A_VALID_WAV_FILE_HEADER_CONTENTS_AT_ALL_12345678"
        with self.assertRaises(ValueError) as ctx:
            adapter.ingest_wav_bytes(fake_wav)
        self.assertIn("does not contain standard RIFF/WAVE signatures", str(ctx.exception))

        # Valid header but corrupt/truncated audio data
        corrupt_wav = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00GARBAGE"
        with self.assertRaises(ValueError) as ctx:
            adapter.ingest_wav_bytes(corrupt_wav)
        self.assertTrue(any(term in str(ctx.exception) for term in ("Corrupt", "too short", "unreadable", "Minimum required duration")))

    def test_predict_wav_bytes_genuine_execution(self):
        """predict_wav_bytes executes end-to-end model inference and returns rich metadata."""
        import io
        import soundfile as sf
        adapter = NocturneMiniAdapter()
        buf = io.BytesIO()
        t = np.linspace(0, 3.0, 16000 * 3, dtype=np.float32)
        sf.write(buf, 0.25 * np.sin(2 * np.pi * 440 * t), 16000, format="WAV")

        res = adapter.predict_wav_bytes(buf.getvalue(), filename="test_chirp.wav", top_k=5)
        self.assertIsInstance(res, AcousticInferenceResult)
        if adapter.check_dependencies().is_available:
            self.assertEqual(res.status, "EXPERIMENTAL")
            self.assertEqual(res.filename, "test_chirp.wav")
            self.assertEqual(res.original_sample_rate, 16000)
            self.assertEqual(res.window_mode, "padded")
            self.assertIsNotNone(res.score)
            self.assertEqual(len(res.top_predictions), 5)


class TestFastAPIEndpoints(unittest.IsolatedAsyncioTestCase):
    """Verifies that ML adapter status, inference, and audio upload are cleanly accessible via FastAPI handlers."""

    async def test_get_models_status_endpoint(self):
        from app.main import get_models_status
        status = await get_models_status()
        self.assertIn("nocturne", status)
        self.assertIn("zeus", status)
        self.assertTrue(status["rule_engine_active"])
        self.assertEqual(status["nocturne"]["adapter_name"], "stratus-labs/nocturne-v1-mini")
        self.assertEqual(status["zeus"]["adapter_name"], "GestaltCog/zeus")

    async def test_run_acoustic_inference_endpoint(self):
        from app.main import run_acoustic_inference, AcousticInferenceRequest
        dummy_audio = [0.1 * float(np.sin(x)) for x in range(16000)]
        req = AcousticInferenceRequest(audio_samples=dummy_audio, sample_rate=16000)
        res = await run_acoustic_inference(req)
        self.assertIn(res.status, ("UNAVAILABLE", "EXPERIMENTAL", "READY"))
        self.assertIsNotNone(res.waveform_preview)
        self.assertEqual(len(res.waveform_preview), 16)

    async def test_upload_acoustic_recording_endpoint(self):
        import io
        import soundfile as sf
        from fastapi import UploadFile, HTTPException
        from app.main import upload_acoustic_recording

        # 1. Valid 2.0s WAV upload
        buf = io.BytesIO()
        t = np.linspace(0, 2.0, 16000 * 2, dtype=np.float32)
        sf.write(buf, 0.2 * np.sin(2 * np.pi * 440 * t), 16000, format="WAV")
        raw_bytes = buf.getvalue()

        upload_file = UploadFile(
            file=io.BytesIO(raw_bytes),
            filename="field_recording.wav",
            headers={"content-type": "audio/wav"}
        )
        res = await upload_acoustic_recording(upload_file, zone_id="zone-a", device_id="esp32-zone-a-01")
        self.assertIn(res.status, ("EXPERIMENTAL", "UNAVAILABLE"))
        self.assertEqual(res.filename, "field_recording.wav")
        self.assertEqual(res.original_sample_rate, 16000)
        self.assertEqual(res.window_mode, "padded")
        self.assertIsNotNone(res.waveform_preview)

        # 2. Reject fake non-WAV upload
        fake_file = UploadFile(
            file=io.BytesIO(b"NOT A WAV FILE CONTENT AT ALL JUST SOME TEXT"),
            filename="fake.wav"
        )
        with self.assertRaises(HTTPException) as ctx:
            await upload_acoustic_recording(fake_file)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("does not contain standard RIFF/WAVE signatures", ctx.exception.detail)

        # 3. Reject empty upload
        empty_file = UploadFile(
            file=io.BytesIO(b""),
            filename="empty.wav"
        )
        with self.assertRaises(HTTPException) as ctx:
            await upload_acoustic_recording(empty_file)
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()

