"""
USDA Bug Bytes Public Reference Dataset Management for SealSense
=================================================================
Manages metadata, cataloging, discovery, and ingestion of authentic
publicly sourced stored-product insect acoustic recordings from the
USDA ARS Bug Bytes sound library (Richard W. Mankin et al.).

Reference:
- Dataset: Bug Bytes Sound Library: Stored Product Insect Pest Sounds
- Compiler: Dr. Richard W. Mankin, USDA-ARS CMAVE (Gainesville, FL)
- DOI: 10.15482/USDA.ADC/1504600
- Data.gov: https://catalog.data.gov/dataset/bug-bytes-sound-library-stored-product-insect-pest-sounds
- License: U.S. Public Domain (https://www.usa.gov/publicdomain/label/1.0/)

CRITICAL SAFEGUARDS:
1. Public reference recordings use provenance `input_source = "public_reference"`.
   They are NEVER labeled as `hardware_recording`.
2. Transducers in reference recordings (contact accelerometers, PVDF film, ultrasonic sensors)
   differ from silo microphone sensors. They must not be conflated with field measurements.
3. Nocturne Mini's outdoor wildlife vocabulary is NOT automatically mapped to reference species.
"""
from __future__ import annotations

import hashlib
import logging
import os
import wave
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

log = logging.getLogger("sealsense.reference_dataset")

DEFAULT_REF_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "reference_datasets", "bug_bytes")
)

DATASET_NAME = "USDA Bug Bytes Sound Library: Stored Product Insect Pest Sounds"
DATASET_CITATION = (
    "Mankin, R. W. (USDA-ARS CMAVE, Gainesville, FL). Bug Bytes Sound Library: "
    "Stored Product Insect Pest Sounds. DOI: 10.15482/USDA.ADC/1504600"
)
DATASET_URL = "https://catalog.data.gov/dataset/bug-bytes-sound-library-stored-product-insect-pest-sounds"
DATASET_LICENSE = "U.S. Public Domain (https://www.usa.gov/publicdomain/label/1.0/)"

# Supported Recording Domains for Acoustic Ingestion & Sensor Separation
VALID_RECORDING_DOMAINS = (
    "airborne_microphone",
    "accelerometer",
    "piezoelectric",
    "pvdf",
    "ultrasonic_transducer",
    "synthetic_simulation",
    "unknown",
)

# Authoritative USDA Bug Bytes Stored-Product Insect Catalog
BUG_BYTES_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "usda-bugbytes-accelrw",
        "filename": "accelrw.wav",
        "species": "Sitophilus oryzae",
        "common_name": "Rice weevil",
        "life_stage": "Larvae (16-17 days old)",
        "substrate": "Wheat kernels (soft red winter wheat)",
        "transducer_type": "Brüel & Kjær 4370 accelerometer (contact transducer)",
        "recording_domain": "accelerometer",
        "category": "A. Stored product insect movement and feeding sounds",
        "description": "Sitophilus oryzae larvae (16-17 d old) moving and feeding inside wheat kernels, recorded with a contact accelerometer in an acoustic isolation chamber.",
        "duration_sec": 10.0,
        "sample_rate": 25000,
        "channels": 1,
        "sample_width_bits": 16,
        "sample_width_bytes": 2,
        "frequency_range": "100 Hz - 12,500 Hz (Nyquist limit)",
        "laboratory_setup": "Acoustic isolation chamber; Brüel & Kjær 4370 charge accelerometer secured to wheat grain container via mounting stud; 100 Hz high-pass filter.",
        "dataset_name": DATASET_NAME,
        "citation": DATASET_CITATION,
        "source_url": DATASET_URL,
        "sha256_hash": "82ebb8bbd990fb49cf3888282b19a31c2b697fab3e1a46e6edd507b3504e5161",
        "notes": "Authentic laboratory recording using contact accelerometer mounted on kernel chamber. Contact vibration mechanics differ fundamentally from airborne silo microphones.",
    },
    {
        "id": "usda-bugbytes-pvdfrw1",
        "filename": "pvdfrw1.wav",
        "species": "Sitophilus oryzae",
        "common_name": "Rice weevil",
        "life_stage": "Larvae (17-18 days old)",
        "substrate": "Wheat kernels (soft red winter wheat)",
        "transducer_type": "PVDF piezoelectric film sensor",
        "recording_domain": "pvdf",
        "category": "A. Stored product insect movement and feeding sounds",
        "description": "Sitophilus oryzae larvae (17-18 d old) inside wheat kernels, recorded with a flexible polyvinylidene fluoride (PVDF) film vibration sensor.",
        "duration_sec": 10.0,
        "sample_rate": 25000,
        "channels": 1,
        "sample_width_bits": 16,
        "sample_width_bytes": 2,
        "frequency_range": "100 Hz - 12,500 Hz (Nyquist limit)",
        "laboratory_setup": "PVDF polymer piezoelectric film wrapped conformally around cylindrical grain sample holder; charge amplifier interface.",
        "dataset_name": DATASET_NAME,
        "citation": DATASET_CITATION,
        "source_url": DATASET_URL,
        "sha256_hash": "31c70733aa57036e1b2e5647b708f4677798ba3f259594a8b7532d220ba75ac0",
        "notes": "PVDF film sensor wrapped around wheat grain sample container. Measures surface strain and vibration.",
    },
    {
        "id": "usda-bugbytes-piezorw1",
        "filename": "piezorw1.wav",
        "species": "Sitophilus oryzae",
        "common_name": "Rice weevil",
        "life_stage": "Larvae (16-17 days old)",
        "substrate": "Wheat kernels (soft red winter wheat)",
        "transducer_type": "Piezoelectric ceramic disk sensor",
        "recording_domain": "piezoelectric",
        "category": "A. Stored product insect movement and feeding sounds",
        "description": "Sitophilus oryzae larvae (16-17 d old) in wheat kernels, recorded with a piezoelectric ceramic disk acoustic transducer.",
        "duration_sec": 10.0,
        "sample_rate": 25000,
        "channels": 1,
        "sample_width_bits": 16,
        "sample_width_bytes": 2,
        "frequency_range": "200 Hz - 12,500 Hz (Nyquist limit)",
        "laboratory_setup": "Lead zirconate titanate (PZT) ceramic disc bonded to bottom of aluminum grain specimen chamber in sound isolation box.",
        "dataset_name": DATASET_NAME,
        "citation": DATASET_CITATION,
        "source_url": DATASET_URL,
        "sha256_hash": "0f4aaa8e1a532bb341336deb491844ff5a25957ec76a6ce8bfe665b3d6f7ca63",
        "notes": "Piezoelectric element coupled to grain holding cup. Resonant ceramic acoustic sensor.",
    },
    {
        "id": "usda-bugbytes-w30khzrw1",
        "filename": "w30khzrw1.wav",
        "species": "Sitophilus oryzae",
        "common_name": "Rice weevil",
        "life_stage": "Larvae (17-18 days old)",
        "substrate": "Wheat kernels (soft red winter wheat)",
        "transducer_type": "30 kHz ultrasonic contact sensor",
        "recording_domain": "ultrasonic_transducer",
        "category": "A. Stored product insect movement and feeding sounds",
        "description": "High-frequency ultrasonic acoustic recording of Sitophilus oryzae larvae in wheat kernels sampled at 50 kHz.",
        "duration_sec": 10.0,
        "sample_rate": 50000,
        "channels": 1,
        "sample_width_bits": 16,
        "sample_width_bytes": 2,
        "frequency_range": "15,000 Hz - 25,000 Hz (Nyquist cutoff, 30 kHz peak resonance)",
        "laboratory_setup": "Resonant 30 kHz acoustic emission transducer acoustically coupled to kernel chamber via high-vacuum grease; bandpass filtered 10–50 kHz.",
        "dataset_name": DATASET_NAME,
        "citation": DATASET_CITATION,
        "source_url": DATASET_URL,
        "sha256_hash": "af262fcbba3a5380cd93f371b71452669f8e93fbccfdda10756faf0db68272a0",
        "notes": "Ultrasonic contact probe detecting high-frequency structural acoustic emissions from larval feeding.",
    },
    {
        "id": "usda-bugbytes-w40khzrw1",
        "filename": "w40khzrw1.wav",
        "species": "Sitophilus oryzae",
        "common_name": "Rice weevil",
        "life_stage": "Larvae (16-17 days old)",
        "substrate": "Wheat kernels (soft red winter wheat)",
        "transducer_type": "40 kHz ultrasonic contact sensor",
        "recording_domain": "ultrasonic_transducer",
        "category": "A. Stored product insect movement and feeding sounds",
        "description": "High-frequency 40 kHz ultrasonic acoustic recording of Sitophilus oryzae larvae feeding in wheat kernels sampled at 50 kHz.",
        "duration_sec": 10.0,
        "sample_rate": 50000,
        "channels": 1,
        "sample_width_bits": 16,
        "sample_width_bytes": 2,
        "frequency_range": "20,000 Hz - 25,000 Hz (Nyquist cutoff, 40 kHz peak resonance)",
        "laboratory_setup": "Resonant 40 kHz piezoelectric contact sensor coupled to wheat sample; preamplified with 40 dB gain; anti-aliasing filtered at 25 kHz.",
        "dataset_name": DATASET_NAME,
        "citation": DATASET_CITATION,
        "source_url": DATASET_URL,
        "sha256_hash": "377716771b26b687ad86ee4cc8b91d66c2d8c835d526a8e628f1cadadc008a45",
        "notes": "40 kHz resonant acoustic probe detecting early-instar grain burrowing impulses.",
    },
    {
        "id": "usda-bugbytes-dfaccs11",
        "filename": "dfaccs11.wav",
        "species": "Plodia interpunctella",
        "common_name": "Indian meal moth",
        "life_stage": "Larvae (multiple feeding)",
        "substrate": "Dry grain / dog food medium",
        "transducer_type": "Brüel & Kjær accelerometer",
        "recording_domain": "accelerometer",
        "category": "A. Stored product insect movement and feeding sounds",
        "description": "Plodia interpunctella larvae moving and feeding in dry cereal food medium, 30s continuous recording with accelerometer.",
        "duration_sec": 30.0,
        "sample_rate": 25000,
        "channels": 1,
        "sample_width_bits": 16,
        "sample_width_bytes": 2,
        "frequency_range": "100 Hz - 12,500 Hz (Nyquist limit)",
        "laboratory_setup": "Plastic culture cup with dry grain food medium; Brüel & Kjær accelerometer attached to exterior base in sound-damped enclosure.",
        "dataset_name": DATASET_NAME,
        "citation": DATASET_CITATION,
        "source_url": DATASET_URL,
        "sha256_hash": "d363a9b9b67026a520604cbbfc64a156b6f5b83962831d29300336666174889c",
        "notes": "External feeding and locomotion by Indianmeal moth larvae on dry grain substrate.",
    },
    {
        "id": "usda-bugbytes-piezimm1",
        "filename": "piezimm1.wav",
        "species": "Plodia interpunctella",
        "common_name": "Indian meal moth",
        "life_stage": "Single larva (crawling/feeding)",
        "substrate": "Dry grain / dog food medium",
        "transducer_type": "Piezoelectric ceramic disk sensor",
        "recording_domain": "piezoelectric",
        "category": "A. Stored product insect movement and feeding sounds",
        "description": "Individual Plodia interpunctella larva moving on dry food surface recorded with piezo disk transducer.",
        "duration_sec": 10.0,
        "sample_rate": 25000,
        "channels": 1,
        "sample_width_bits": 16,
        "sample_width_bytes": 2,
        "frequency_range": "200 Hz - 12,500 Hz (Nyquist limit)",
        "laboratory_setup": "Single larva placed in 30 mm petri dish with ceramic piezoelectric disk bottom in acoustic booth.",
        "dataset_name": DATASET_NAME,
        "citation": DATASET_CITATION,
        "source_url": DATASET_URL,
        "sha256_hash": "c7665fc1f8d17793450c68e466cc86488662bfbf9ad16f6b206845c9d070b7f3",
        "notes": "Single-larva acoustic profile showing low-amplitude crawling and chewing impulses.",
    },
    {
        "id": "usda-bugbytes-zeamais-ref",
        "filename": "zeamais_ref.wav",
        "species": "Sitophilus zeamais",
        "common_name": "Maize weevil",
        "life_stage": "Larvae & adults",
        "substrate": "Maize / corn kernels",
        "transducer_type": "Piezoelectric acoustic probe",
        "recording_domain": "piezoelectric",
        "category": "A. Stored product insect movement and feeding sounds",
        "description": "Sitophilus zeamais larvae and adults feeding inside whole maize kernels. Documented in USDA ARS / Data.gov Bug Bytes inventory.",
        "duration_sec": 10.0,
        "sample_rate": 16000,
        "channels": 1,
        "sample_width_bits": 16,
        "sample_width_bytes": 2,
        "frequency_range": "200 Hz - 8,000 Hz",
        "laboratory_setup": "Maize grain column with inserted piezoelectric probe in isolation box.",
        "dataset_name": DATASET_NAME,
        "citation": DATASET_CITATION,
        "source_url": DATASET_URL,
        "sha256_hash": None,
        "notes": "Reference inventory entry for Maize weevil. Recorded in corn grain mass.",
    },
    {
        "id": "usda-bugbytes-truncatus-ref",
        "filename": "truncatus_ref.wav",
        "species": "Prostephanus truncatus",
        "common_name": "Larger grain borer",
        "life_stage": "Larvae & adults",
        "substrate": "Maize / corn kernels",
        "transducer_type": "Acoustic emission sensor",
        "recording_domain": "ultrasonic_transducer",
        "category": "A. Stored product insect movement and feeding sounds",
        "description": "Prostephanus truncatus larvae and adults tunneling in maize kernels. High-intensity boring impulses.",
        "duration_sec": 10.0,
        "sample_rate": 16000,
        "channels": 1,
        "sample_width_bits": 16,
        "sample_width_bytes": 2,
        "frequency_range": "1,000 Hz - 8,000 Hz",
        "laboratory_setup": "Acoustic emission sensor clamped to grain cylinder.",
        "dataset_name": DATASET_NAME,
        "citation": DATASET_CITATION,
        "source_url": DATASET_URL,
        "sha256_hash": None,
        "notes": "Reference inventory entry for Larger grain borer. High-damage stored-grain borer pest.",
    },
]


def get_reference_storage_dir() -> str:
    """Returns directory path where USDA Bug Bytes reference WAV files reside."""
    ref_dir = os.environ.get("SEALSENSE_REFERENCE_AUDIO_DIR", DEFAULT_REF_DIR)
    os.makedirs(ref_dir, exist_ok=True)
    return ref_dir


def get_reference_file_path(filename: str) -> Optional[str]:
    """Resolves local absolute path to a reference WAV file if it exists."""
    ref_dir = get_reference_storage_dir()
    path = os.path.join(ref_dir, filename)
    if os.path.isfile(path):
        return path
    return None


def list_reference_catalog() -> List[Dict[str, Any]]:
    """
    Returns the complete catalog of USDA Bug Bytes reference recordings,
    annotating whether each recording is locally available on disk.
    """
    catalog = []
    for item in BUG_BYTES_CATALOG:
        entry = dict(item)
        local_path = get_reference_file_path(item["filename"])
        entry["is_locally_available"] = bool(local_path)
        if local_path:
            try:
                with open(local_path, "rb") as f:
                    content = f.read()
                entry["file_size_bytes"] = len(content)
                if not entry.get("sha256_hash"):
                    entry["sha256_hash"] = hashlib.sha256(content).hexdigest()
            except Exception as e:
                log.warning("Could not inspect local reference file %s: %e", local_path, e)
        catalog.append(entry)
    return catalog


def get_catalog_item(catalog_id_or_filename: str) -> Optional[Dict[str, Any]]:
    """Finds a catalog item by either ID or filename."""
    for item in BUG_BYTES_CATALOG:
        if item["id"] == catalog_id_or_filename or item["filename"] == catalog_id_or_filename:
            entry = dict(item)
            local_path = get_reference_file_path(item["filename"])
            entry["is_locally_available"] = bool(local_path)
            return entry
    return None
