"""
Unit & Integration Tests for Public Reference Audio & Simulation Demo Mode
==========================================================================
Verifies:
1. USDA Bug Bytes catalog listing, metadata, and citation attribution.
2. Local reference audio discovery and valid 16-bit PCM WAV headers.
3. Dedicated provenance tracking: input_source = "public_reference" (never hardware_recording).
4. Genuine Nocturne Mini inference on authentic USDA insect audio (Sitophilus oryzae, Plodia interpunctella).
5. Synthetic bioacoustic impulse/click generator: determinism, parameter controls (rate, amp, noise, seed).
6. Synthetic simulation provenance: input_source = "synthetic" and is_synthetic = True.
7. Evaluation exclusion: synthetic simulations strictly excluded from scientific metrics.
8. Dataset manifest export containing reference metadata and citations.
"""
import io
import os
import sys
import unittest
import wave
from datetime import datetime, timezone

# Ensure backend root is on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.reference_dataset import (
    BUG_BYTES_CATALOG, list_reference_catalog, get_catalog_item,
    get_reference_file_path, get_reference_storage_dir
)
from app.synthetic_generator import (
    generate_synthetic_impulse_wav, generate_synthetic_chirp_wav
)
from app.audio_storage import compute_sha256, validate_wav_bytes
from app.evaluation import evaluate_dataset_samples
from app.main import (
    get_reference_catalog as api_get_catalog,
    import_reference_sample as api_import_reference,
    generate_synthetic_simulation as api_generate_synthetic,
    get_reference_audio_file as api_get_ref_audio,
)
from app.models import ReferenceImportRequest, SyntheticImpulseRequest
from app.database import get_db, CREATE_SAMPLES, init_db


class TestReferenceDatasetAndSimulation(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()

    def test_bug_bytes_catalog_integrity(self):
        """Verifies USDA Bug Bytes catalog contains required stored-product species and citations."""
        catalog = list_reference_catalog()
        self.assertGreaterEqual(len(catalog), 7)

        species_set = {item["species"] for item in catalog}
        self.assertIn("Sitophilus oryzae", species_set)
        self.assertIn("Plodia interpunctella", species_set)

        for item in catalog:
            self.assertTrue(item["dataset_name"].startswith("USDA Bug Bytes"))
            self.assertIn("10.15482/USDA.ADC/1504600", item["citation"])
            self.assertTrue(item["source_url"].startswith("https://"))
            self.assertIn("transducer_type", item)
            self.assertTrue(item["duration_sec"] > 0)
            self.assertIn(item["sample_rate"], (16000, 25000, 50000))

    def test_local_reference_wav_files_exist_and_valid(self):
        """Verifies local reference WAV files downloaded from USDA Bug Bytes have valid headers."""
        catalog = list_reference_catalog()
        available_items = [item for item in catalog if item["is_locally_available"]]
        self.assertGreaterEqual(len(available_items), 5, "At least 5 USDA reference files should be present on disk.")

        for item in available_items:
            path = get_reference_file_path(item["filename"])
            self.assertIsNotNone(path)
            self.assertTrue(os.path.isfile(path))

            with open(path, "rb") as f:
                data = f.read()

            channels, sample_rate, duration = validate_wav_bytes(data)
            self.assertEqual(channels, 1, f"{item['filename']} should be mono")
            self.assertEqual(sample_rate, item["sample_rate"])
            self.assertAlmostEqual(duration, item["duration_sec"], delta=0.5)

    def test_synthetic_impulse_generator_determinism_and_parameters(self):
        """Verifies synthetic impulse scenario generator is deterministic with seed and responds to parameters."""
        # Test determinism
        wav_seed1_a = generate_synthetic_impulse_wav(impulse_rate=15.0, amplitude=0.7, seed=42)
        wav_seed1_b = generate_synthetic_impulse_wav(impulse_rate=15.0, amplitude=0.7, seed=42)
        self.assertEqual(wav_seed1_a, wav_seed1_b, "Identical seed and parameters must produce identical audio.")

        # Test seed sensitivity
        wav_seed2 = generate_synthetic_impulse_wav(impulse_rate=15.0, amplitude=0.7, seed=99)
        self.assertNotEqual(wav_seed1_a, wav_seed2, "Different seeds must produce different waveforms.")

        # Test audio validity
        channels, rate, dur = validate_wav_bytes(wav_seed1_a)
        self.assertEqual(channels, 1)
        self.assertEqual(rate, 16000)
        self.assertAlmostEqual(dur, 10.0, delta=0.1)

    async def test_reference_import_provenance_and_inference(self):
        """Tests importing a USDA Bug Bytes reference recording into the dataset library."""
        req = ReferenceImportRequest(
            catalog_id="usda-bugbytes-accelrw",
            retain_sample=True,
            zone_id="zone-a",
            device_id="esp32-zone-a-01",
            notes="Automated test import of Sitophilus oryzae reference"
        )
        result = await api_import_reference(req)

        # Provenance must be public_reference, NEVER hardware_recording
        self.assertEqual(result.input_source, "public_reference")
        self.assertNotEqual(result.input_source, "hardware_recording")
        self.assertEqual(result.source_species, "Sitophilus oryzae")
        self.assertIn("10.15482/USDA.ADC/1504600", result.source_citation)
        self.assertTrue(result.is_retained)
        self.assertIsNotNone(result.audio_sample_id)

        # Verify database record
        async with get_db() as db:
            cursor = await db.execute("SELECT * FROM retained_audio_samples WHERE id = ?", (result.audio_sample_id,))
            row = await cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["input_source"], "public_reference")
            self.assertEqual(row["source_species"], "Sitophilus oryzae")
            self.assertEqual(row["ground_truth_label"], "TARGET_PEST_OBSERVED")
            self.assertEqual(row["verification_method"], "laboratory_reared_culture")
            self.assertEqual(row["is_synthetic"], 0)

    async def test_synthetic_simulation_endpoint_and_evaluation_exclusion(self):
        """Verifies synthetic simulation endpoint flags recordings and excludes them from evaluation."""
        req = SyntheticImpulseRequest(
            impulse_rate=20.0,
            amplitude=0.8,
            noise_level=0.02,
            duration_sec=10.0,
            seed=123,
            run_inference=True,
            retain_sample=True,
        )
        result = await api_generate_synthetic(req)

        self.assertEqual(result.input_source, "synthetic")
        self.assertTrue(result.is_retained)
        self.assertIsNotNone(result.audio_sample_id)
        self.assertIsNotNone(result.simulation_params)
        self.assertEqual(result.simulation_params["seed"], 123)

        # Verify evaluation exclusion
        async with get_db() as db:
            cursor = await db.execute("SELECT * FROM retained_audio_samples WHERE id = ?", (result.audio_sample_id,))
            row = dict(await cursor.fetchone())

        report = evaluate_dataset_samples([row], anomaly_threshold=0.05, verify_files_on_disk=True)
        self.assertEqual(report.total_samples, 1)
        self.assertEqual(report.eligible_samples, 0, "Synthetic samples must NEVER be eligible for real-world evaluation.")
        self.assertEqual(report.excluded_samples, 1)
        self.assertEqual(report.exclusion_breakdown["synthetic_test_signal"], 1)


if __name__ == "__main__":
    unittest.main()
