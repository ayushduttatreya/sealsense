"""
Unit and Integration Tests for SealSense Acoustic Dataset Management & Evaluation
==================================================================================
Covers:
- Audio sample retention and filesystem storage
- SHA-256 duplicate detection
- Path traversal defenses & malicious ID rejection
- Waveform header validation & corrupt file rejection
- Independent physical ground-truth annotation state transitions
- Audio streaming / download endpoint
- Safe deletion of records and files
- Exclusion of synthetic test signals from evaluation
- Exclusion of unreviewed & inconclusive samples from evaluation
- Offline dataset evaluation metrics (precision, recall, specificity, F1)
- Dataset manifest export in JSON and CSV formats
- Backward compatibility when retain_sample=False
"""
from __future__ import annotations

import io
import math
import os
import shutil
import sys
import tempfile
import unittest
import wave

# Ensure backend root is on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Set temporary storage directory before importing application modules
TEST_STORAGE_DIR = tempfile.mkdtemp(prefix="sealsense_test_audio_")
os.environ["SEALSENSE_AUDIO_DIR"] = TEST_STORAGE_DIR
TEST_DB_PATH = tempfile.mktemp(prefix="sealsense_test_db_", suffix=".db")
os.environ["SEALSENSE_DB"] = TEST_DB_PATH

from fastapi import UploadFile, HTTPException
from app.database import init_db, get_db
from app.audio_storage import (
    compute_sha256, validate_wav_bytes, generate_sample_id,
    save_audio_file, get_audio_file_path, delete_audio_file,
    is_safe_filename, get_storage_dir
)
from app.models import (
    RetainedAudioSample, AnnotationUpdateRequest, DatasetEvaluationReport,
    GroundTruthLabel
)
from app.evaluation import evaluate_dataset_samples
from app.main import (
    upload_acoustic_recording, list_audio_samples, get_audio_sample,
    get_audio_sample_file, update_sample_annotation, delete_audio_sample,
    export_dataset_manifest, get_dataset_evaluation
)


def create_test_wav_bytes(duration_sec: float = 1.0, sample_rate: int = 16000, freq: float = 440.0) -> bytes:
    """Creates in-memory valid PCM 16-bit mono WAV audio bytes."""
    num_samples = int(duration_sec * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        raw = bytearray()
        for i in range(num_samples):
            t = i / sample_rate
            sample = 0.25 * math.sin(2 * math.pi * freq * t)
            ival = int(max(-32768, min(32767, sample * 32767)))
            raw.extend(ival.to_bytes(2, "little", signed=True))
        wf.writeframes(raw)
    return buf.getvalue()


class TestAudioStorageService(unittest.TestCase):
    def test_compute_sha256(self):
        data = b"RIFF....WAVE_TEST_DATA"
        h = compute_sha256(data)
        self.assertEqual(len(h), 64)
        self.assertEqual(h, compute_sha256(data))

    def test_validate_wav_bytes_valid(self):
        wav_bytes = create_test_wav_bytes(duration_sec=2.0, sample_rate=16000)
        channels, rate, dur = validate_wav_bytes(wav_bytes)
        self.assertEqual(channels, 1)
        self.assertEqual(rate, 16000)
        self.assertAlmostEqual(dur, 2.0, places=1)

    def test_validate_wav_bytes_corrupt(self):
        with self.assertRaises(ValueError) as ctx:
            validate_wav_bytes(b"NOT A WAV FILE")
        self.assertIn("WAV header", str(ctx.exception))

    def test_path_traversal_detection(self):
        self.assertFalse(is_safe_filename("../evil.wav"))
        self.assertFalse(is_safe_filename("../../etc/passwd"))
        self.assertFalse(is_safe_filename("sub/dir/audio.wav"))
        self.assertTrue(is_safe_filename("samp-123456789abc.wav"))
        self.assertTrue(is_safe_filename("field_recording_zone_a.wav"))

        with self.assertRaises(ValueError):
            save_audio_file("../traversal", b"RIFFtest")

    def test_atomic_save_and_retrieve_file(self):
        sample_id = generate_sample_id()
        data = create_test_wav_bytes(0.5, 16000)
        stored_fn, resolved_path, size = save_audio_file(sample_id, data)

        self.assertEqual(stored_fn, f"{sample_id}.wav")
        self.assertTrue(os.path.isfile(resolved_path))
        self.assertEqual(size, len(data))

        # Retrieve file path
        retrieved_path = get_audio_file_path(stored_fn)
        self.assertEqual(retrieved_path, resolved_path)

        # Delete file
        deleted = delete_audio_file(stored_fn)
        self.assertTrue(deleted)
        self.assertFalse(os.path.exists(resolved_path))
        self.assertIsNone(get_audio_file_path(stored_fn))


class TestDatasetEvaluationHarness(unittest.TestCase):
    def test_offline_evaluation_metrics(self):
        # Prepare mock database sample rows
        samples = [
            # Eligible True Positive: Pest observed & anomaly score >= 0.05
            {
                "id": "samp-001", "filename": "probe1.wav", "stored_filename": "samp-001.wav",
                "ground_truth_label": "TARGET_PEST_OBSERVED", "score": 0.082, "is_synthetic": 0,
                "zone_id": "zone-a", "input_source": "user_upload"
            },
            # Eligible True Negative: No pest observed & anomaly score < 0.05
            {
                "id": "samp-002", "filename": "probe2.wav", "stored_filename": "samp-002.wav",
                "ground_truth_label": "NO_TARGET_PEST_OBSERVED", "score": 0.012, "is_synthetic": 0,
                "zone_id": "zone-a", "input_source": "user_upload"
            },
            # Eligible False Positive: No pest observed, but score >= 0.05
            {
                "id": "samp-003", "filename": "probe3.wav", "stored_filename": "samp-003.wav",
                "ground_truth_label": "NO_TARGET_PEST_OBSERVED", "score": 0.071, "is_synthetic": 0,
                "zone_id": "zone-b", "input_source": "user_upload"
            },
            # Excluded: Synthetic test signal
            {
                "id": "samp-syn", "filename": "synth.wav", "stored_filename": "samp-syn.wav",
                "ground_truth_label": "TARGET_PEST_OBSERVED", "score": 0.09, "is_synthetic": 1,
                "zone_id": "zone-a", "input_source": "synthetic"
            },
            # Excluded: Unreviewed sample
            {
                "id": "samp-unrev", "filename": "unrev.wav", "stored_filename": "samp-unrev.wav",
                "ground_truth_label": "UNREVIEWED", "score": 0.03, "is_synthetic": 0,
                "zone_id": "zone-a", "input_source": "user_upload"
            },
            # Excluded: Inconclusive observation
            {
                "id": "samp-incon", "filename": "incon.wav", "stored_filename": "samp-incon.wav",
                "ground_truth_label": "INCONCLUSIVE", "score": 0.06, "is_synthetic": 0,
                "zone_id": "zone-c", "input_source": "user_upload"
            },
        ]

        report = evaluate_dataset_samples(samples, anomaly_threshold=0.05, verify_files_on_disk=False)

        self.assertEqual(report.total_samples, 6)
        self.assertEqual(report.eligible_samples, 3)
        self.assertEqual(report.excluded_samples, 3)
        self.assertEqual(report.exclusion_breakdown["synthetic_test_signal"], 1)
        self.assertEqual(report.exclusion_breakdown["unreviewed_sample"], 1)
        self.assertEqual(report.exclusion_breakdown["inconclusive_observation"], 1)

        metrics = report.anomaly_metrics
        self.assertIsNotNone(metrics)
        self.assertEqual(metrics.true_positives, 1)
        self.assertEqual(metrics.true_negatives, 1)
        self.assertEqual(metrics.false_positives, 1)
        self.assertEqual(metrics.false_negatives, 0)
        # Precision = TP / (TP + FP) = 1 / 2 = 0.5
        self.assertAlmostEqual(metrics.precision, 0.5, places=2)
        # Recall = TP / (TP + FN) = 1 / 1 = 1.0
        self.assertAlmostEqual(metrics.recall, 1.0, places=2)
        # Specificity = TN / (TN + FP) = 1 / 2 = 0.5
        self.assertAlmostEqual(metrics.specificity, 0.5, places=2)


class TestDatasetFastAPIEndpoints(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await init_db()

    async def test_audio_sample_retention_and_duplicate_detection(self):
        wav_bytes = create_test_wav_bytes(duration_sec=1.0, freq=300.0)
        upload1 = UploadFile(file=io.BytesIO(wav_bytes), filename="grain_silo_clip_1.wav")

        # 1. Upload with retain_sample=True
        res1 = await upload_acoustic_recording(
            file=upload1,
            zone_id="zone-a",
            device_id="esp32-zone-a-01",
            save_event=True,
            retain_sample=True,
            is_synthetic=False,
            input_source="user_upload"
        )

        self.assertTrue(res1.is_retained)
        self.assertIsNotNone(res1.audio_sample_id)
        sample_id_1 = res1.audio_sample_id

        # Retrieve sample from library
        sample = await get_audio_sample(sample_id_1)
        self.assertEqual(sample.id, sample_id_1)
        self.assertEqual(sample.filename, "grain_silo_clip_1.wav")
        self.assertEqual(sample.ground_truth_label, "UNREVIEWED")
        self.assertEqual(sample.review_status, "UNREVIEWED")

        # 2. Upload identical content -> SHA-256 duplicate detection reuses sample_id
        upload2 = UploadFile(file=io.BytesIO(wav_bytes), filename="grain_silo_clip_duplicate.wav")
        res2 = await upload_acoustic_recording(
            file=upload2,
            zone_id="zone-a",
            device_id="esp32-zone-a-01",
            retain_sample=True
        )
        self.assertEqual(res2.audio_sample_id, sample_id_1)

        # 3. Stream audio file
        file_resp = await get_audio_sample_file(sample_id_1)
        self.assertEqual(file_resp.media_type, "audio/wav")

        # 4. Update annotation (physical ground-truth from spear trap inspection)
        updated = await update_sample_annotation(
            sample_id_1,
            AnnotationUpdateRequest(
                ground_truth_label="TARGET_PEST_OBSERVED",
                verification_method="physical_trap_inspection",
                reviewer="Inspector Sarah",
                evidence_notes="Found 5 Sitophilus oryzae specimens in grain trap."
            )
        )
        self.assertEqual(updated.ground_truth_label, "TARGET_PEST_OBSERVED")
        self.assertEqual(updated.verification_method, "physical_trap_inspection")
        self.assertEqual(updated.reviewer, "Inspector Sarah")
        self.assertEqual(updated.review_status, "REVIEWED")

        # 5. Export dataset manifest
        manifest_json = await export_dataset_manifest(format="json", include_synthetic=False)
        self.assertGreaterEqual(manifest_json["total_samples"], 1)

        # 6. Delete sample
        del_res = await delete_audio_sample(sample_id_1)
        self.assertTrue(del_res["deleted"])

        with self.assertRaises(HTTPException):
            await get_audio_sample(sample_id_1)

    async def test_non_retained_upload_compatibility(self):
        wav_bytes = create_test_wav_bytes(duration_sec=0.5, freq=500.0)
        upload = UploadFile(file=io.BytesIO(wav_bytes), filename="temp_check.wav")

        # Upload with retain_sample=False (default behavior)
        res = await upload_acoustic_recording(file=upload, retain_sample=False)
        self.assertFalse(res.is_retained)
        self.assertIsNone(res.audio_sample_id)


def tearDownModule():
    # Clean up test directories
    if os.path.exists(TEST_STORAGE_DIR):
        shutil.rmtree(TEST_STORAGE_DIR, ignore_errors=True)
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except OSError:
            pass


if __name__ == "__main__":
    unittest.main()
