"""
SealSense Model Adapters - Base Definitions & Schemas
=====================================================
Common types, dependency checkers, and structured inference outputs
for SealSense machine learning adapters.
"""
from __future__ import annotations
import sys
import importlib
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field

ModelStatus = Literal["READY", "UNAVAILABLE", "EXPERIMENTAL", "ERROR"]

class DependencyReport(BaseModel):
    adapter_name: str
    is_available: bool
    installed_packages: Dict[str, str] = {}
    missing_packages: List[str] = []
    cuda_available: bool = False
    cuda_device: Optional[str] = None
    installation_instructions: str = ""
    summary: str = ""


class PredictionItem(BaseModel):
    label: str
    score: float


class AcousticInferenceResult(BaseModel):
    status: ModelStatus
    model_id: str = "stratus-labs/nocturne-v1-mini"
    prediction: str = "uncertain"
    score: Optional[float] = None
    score_semantics: str = (
        "Raw model output over outdoor insect vocabulary — not a calibrated infestation probability for grain storage. "
        "Requires expert physical kernel trap inspection."
    )
    top_predictions: List[PredictionItem] = []
    confidence_band: Literal["low", "medium", "high", "uncertain"] = "uncertain"
    inference_duration_ms: Optional[int] = None
    audio_sample_rate: int = 16000
    audio_duration_sec: float = 10.0
    waveform_preview: Optional[List[float]] = None
    spectrogram_peaks: Optional[List[Dict[str, Any]]] = None
    limitations: str = (
        "Model was trained on InsectSet459 and iNat-Sounds-2024 (outdoor nocturnal Orthoptera, Cicadidae). "
        "It has NOT been validated on stored-grain pests (Sitophilus oryzae, Rhyzopertha dominica, etc.). "
        "Never use unverified scores as quarantine criteria."
    )
    error: Optional[str] = None
    reason: Optional[str] = None
    # Audio ingestion and upload metadata
    input_source: Literal["user_upload", "synthetic", "live_stream", "public_reference", "hardware_recording"] = "synthetic"
    filename: Optional[str] = None
    original_sample_rate: Optional[int] = None
    original_channels: Optional[int] = None
    original_duration_sec: Optional[float] = None
    window_mode: Optional[Literal["exact", "padded", "truncated"]] = None
    audio_sample_id: Optional[str] = None
    is_retained: bool = False
    dataset_name: Optional[str] = None
    source_species: Optional[str] = None
    source_citation: Optional[str] = None
    source_url: Optional[str] = None
    transducer_type: Optional[str] = None
    recording_domain: Literal[
        "airborne_microphone",
        "accelerometer",
        "piezoelectric",
        "pvdf",
        "ultrasonic_transducer",
        "synthetic_simulation",
        "unknown"
    ] = "unknown"
    simulation_params: Optional[dict] = None
    signal_analysis: Optional[Dict[str, Any]] = None


class ZeusInferenceResult(BaseModel):
    status: ModelStatus
    model_id: str = "GestaltCog/zeus"
    forecast: Optional[List[float]] = None
    inference_duration_ms: Optional[int] = None
    fallback_active: bool = True
    limitations: str = (
        "Foundation time-series model (ICML'26) requiring CUDA and FlashAttention-2. "
        "Not trained on bulk grain aerobic respiration kinetics, temperature gradients, or hermetic gas dynamics. "
        "Configurable deterministic rule engine (alert_rules.py) remains active ground truth."
    )
    error: Optional[str] = None
    reason: Optional[str] = None


def check_python_packages(required: List[str]) -> tuple[Dict[str, str], List[str]]:
    """Checks whether the requested python modules are importable and extracts versions."""
    installed: Dict[str, str] = {}
    missing: List[str] = []
    for pkg in required:
        try:
            mod = importlib.import_module(pkg)
            ver = getattr(mod, "__version__", "installed")
            installed[pkg] = str(ver)
        except (ImportError, ModuleNotFoundError):
            missing.append(pkg)
    return installed, missing
