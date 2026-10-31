"""
Zeus Time-Series Foundation Model Adapter
=========================================
Adapter for GestaltCog/zeus:
- Foundation time-series model (102M parameters, ICML'26, arxiv:2607.01918).
- Architecture: BERT-style deep transformer for context sequences.
- Hardware requirements: CUDA + FlashAttention-2 (explicit requirement in official model card).
- Domain limitations: Pretrained on synthetic and open-domain datasets (Salesforce/GiftEvalPretrain).
  Zero training on bulk grain aerobic respiration, temperature gradients, or hermetic gas dynamics.
- Fail-safe design: Configurable rule-based alert engine (alert_rules.py) remains active and authoritative.
"""
from __future__ import annotations
import os
import time
import logging
from typing import Optional, List, Union
import numpy as np

from .base import (
    DependencyReport,
    ZeusInferenceResult,
    check_python_packages,
)

log = logging.getLogger("sealsense.zeus")

REQUIRED_PACKAGES = ["torch", "transformers"]
STANDARD_CONTEXT_LENGTH = 256


class ZeusAdapter:
    """
    Adapter for the Zeus foundation time-series model.
    Enforces honest dependency checks and blocks premature edge/CPU deployment.
    """
    def __init__(self, model_id: str = "GestaltCog/zeus"):
        self.model_id = model_id
        self._model = None
        self._is_loaded = False
        self._load_error: Optional[str] = None

    @classmethod
    def check_dependencies(cls) -> DependencyReport:
        """
        Evaluates whether PyTorch, Transformers, CUDA, and FlashAttention-2 are available.
        """
        installed, missing = check_python_packages(REQUIRED_PACKAGES)

        cuda_avail = False
        cuda_name = None
        has_flash_attn = False

        if "torch" in installed:
            try:
                import torch
                cuda_avail = torch.cuda.is_available()
                if cuda_avail:
                    cuda_name = torch.cuda.get_device_name(0)
            except Exception:
                pass

        try:
            import flash_attn
            has_flash_attn = True
        except (ImportError, ModuleNotFoundError):
            has_flash_attn = False

        blockers = []
        if missing:
            blockers.append(f"Missing packages: {', '.join(missing)}")
        if not cuda_avail:
            blockers.append("CUDA acceleration unavailable (Zeus requires GPU for real-time inference)")
        if not has_flash_attn:
            blockers.append("FlashAttention-2 not installed (required by official model configuration)")

        is_ready = len(missing) == 0 and cuda_avail and has_flash_attn

        instructions = (
            "Zeus requires CUDA and FlashAttention-2. On edge hardware or CPU servers, "
            "it is blocked by design. The deterministic rule engine (alert_rules.py) "
            "runs independently with <1ms latency and zero hardware accelerators."
        )

        return DependencyReport(
            adapter_name="GestaltCog/zeus",
            is_available=is_ready,
            installed_packages=installed,
            missing_packages=missing,
            cuda_available=cuda_avail,
            cuda_device=cuda_name,
            installation_instructions=instructions,
            summary="Blocked: " + "; ".join(blockers) if blockers else "Ready for GPU inference",
        )

    def validate_input(self, series_data: Union[np.ndarray, List[float]]) -> np.ndarray:
        """
        Validates time-series input format.
        Expects 1D sequence of numbers or 2D (batch, context_length).
        """
        if not isinstance(series_data, np.ndarray):
            series_data = np.asarray(series_data, dtype=np.float32)

        if series_data.size == 0:
            raise ValueError("Time-series input sequence cannot be empty.")

        if not np.all(np.isfinite(series_data)):
            raise ValueError("Time-series sequence contains NaN or Infinite values.")

        if series_data.ndim == 1:
            series_data = series_data.reshape(1, -1)
        elif series_data.ndim != 2:
            raise ValueError(f"Expected 1D or 2D time series sequence, received {series_data.ndim}D.")

        return series_data

    def predict(
        self,
        series_data: Union[np.ndarray, List[float]],
        prediction_length: int = 16,
    ) -> ZeusInferenceResult:
        """
        Attempts inference on the time-series sequence.
        Since Zeus requires FlashAttention-2 and CUDA, honest UNAVAILABLE status is reported
        when hardware/dependency blockers exist, while the rule engine continues uninterrupted.
        """
        t0 = time.time()

        try:
            valid_series = self.validate_input(series_data)
        except ValueError as ve:
            return ZeusInferenceResult(
                status="ERROR",
                error=f"Malformed time-series input: {str(ve)}",
                inference_duration_ms=int((time.time() - t0) * 1000),
                fallback_active=True,
            )

        dep_report = self.check_dependencies()
        if not dep_report.is_available:
            return ZeusInferenceResult(
                status="UNAVAILABLE",
                reason=dep_report.summary,
                inference_duration_ms=int((time.time() - t0) * 1000),
                fallback_active=True,
            )

        # In the rare event that CUDA, FlashAttention-2, and PyTorch are present:
        try:
            import torch
            from transformers import AutoModel
            if not self._is_loaded:
                model = AutoModel.from_pretrained(
                    self.model_id,
                    trust_remote_code=True,
                    attn_implementation="flash_attention_2",
                    device_map="cuda",
                )
                self._model = model.eval()
                self._is_loaded = True

            with torch.no_grad():
                tensor_in = torch.from_numpy(valid_series).to("cuda")
                out = self._model.generate(tensor_in, prediction_length=prediction_length)
                forecast = out.cpu().numpy().flatten().tolist()

            return ZeusInferenceResult(
                status="EXPERIMENTAL",
                forecast=[round(float(x), 3) for x in forecast],
                inference_duration_ms=int((time.time() - t0) * 1000),
                fallback_active=False,
            )

        except Exception as e:
            return ZeusInferenceResult(
                status="ERROR",
                error=f"Zeus inference failed: {str(e)}",
                inference_duration_ms=int((time.time() - t0) * 1000),
                fallback_active=True,
            )
