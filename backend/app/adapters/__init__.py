"""
SealSense Model Adapters
========================
Provides isolated, lazy-loaded adapters for bioacoustic and time-series models:
- NocturneMiniAdapter (stratus-labs/nocturne-v1-mini)
- ZeusAdapter (GestaltCog/zeus)
"""
from .base import (
    ModelStatus,
    DependencyReport,
    AcousticInferenceResult,
    ZeusInferenceResult,
    PredictionItem,
)
from .nocturne import NocturneMiniAdapter
from .zeus import ZeusAdapter

__all__ = [
    "ModelStatus",
    "DependencyReport",
    "AcousticInferenceResult",
    "ZeusInferenceResult",
    "PredictionItem",
    "NocturneMiniAdapter",
    "ZeusAdapter",
]
