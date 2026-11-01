"""
SealSense Stored-Grain Acoustic Baseline Model Adapter
======================================================
Domain-specific acoustic classification adapter for bulk grain monitoring.
Trained on physical features and Log-Mel spectrograms from authentic USDA Bug Bytes
stored-grain insect recordings and silo acoustic captures.

Classes:
  - insect_activity (Sitophilus oryzae, Plodia interpunctella feeding/locomotion clicks)
  - machinery_ventilation (aeration blower drone and fan harmonics)
  - grain_handling (grain shifting, pouring, friction)
  - background_noise (ambient silo acoustic noise floor)

Models:
  1. sealsense-rf-baseline-v1 (Random Forest on 22 physical acoustic features)
  2. sealsense-cnn-baseline-v1 (Lightweight 2D CNN on Log-Mel spectrograms)
"""
from __future__ import annotations

import os
import io
import wave
import time
import logging
from typing import Optional, List, Dict, Any, Union
import numpy as np
import joblib

import torch

from .base import DependencyReport, AcousticInferenceResult, PredictionItem
from ..ml.dataset import CLASS_NAMES, TARGET_SAMPLE_RATE
from ..ml.features import extract_features, extract_feature_vector, extract_log_mel_spectrogram, FEATURE_NAMES
from ..ml.models import SealSenseAcousticCNN

log = logging.getLogger("sealsense.ml.baseline")

ARTIFACTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ml", "artifacts"))
RF_MODEL_PATH = os.path.join(ARTIFACTS_DIR, "rf_baseline.joblib")
CNN_MODEL_PATH = os.path.join(ARTIFACTS_DIR, "cnn_baseline.pt")


class GrainAcousticBaselineAdapter:
    """
    Production adapter executing domain-specific stored-grain acoustic inference.
    """
    def __init__(self):
        self._rf_artifact = None
        self._cnn_model = None
        self._is_loaded = False
        self._load_error = None

    def load_models(self) -> bool:
        if self._is_loaded:
            return True

        # 1. Load Random Forest artifact
        if os.path.isfile(RF_MODEL_PATH):
            try:
                self._rf_artifact = joblib.load(RF_MODEL_PATH)
                log.info("Loaded Random Forest baseline model from %s", RF_MODEL_PATH)
            except Exception as e:
                log.warning("Could not load Random Forest model: %s", e)
                self._rf_artifact = None

        # 2. Load CNN PyTorch model
        if os.path.isfile(CNN_MODEL_PATH):
            try:
                checkpoint = torch.load(CNN_MODEL_PATH, map_location="cpu")
                cnn = SealSenseAcousticCNN(num_classes=checkpoint.get("num_classes", len(CLASS_NAMES)))
                cnn.load_state_dict(checkpoint["state_dict"])
                cnn.eval()
                self._cnn_model = cnn
                log.info("Loaded Small 2D CNN baseline model from %s", CNN_MODEL_PATH)
            except Exception as e:
                log.warning("Could not load CNN model: %s", e)
                self._cnn_model = None

        if self._rf_artifact is not None or self._cnn_model is not None:
            self._is_loaded = True
            return True
        else:
            self._load_error = "Baseline model artifacts not found. Run train_and_evaluate.py to build them."
            return False

    def predict(
        self,
        audio_data: Union[np.ndarray, List[float]],
        sample_rate: int = TARGET_SAMPLE_RATE,
        model_type: str = "rf",
    ) -> Dict[str, Any]:
        """
        Executes domain-specific acoustic classification on a mono audio array.
        """
        if not self._is_loaded:
            self.load_models()

        if not self._is_loaded:
            return {
                "status": "UNAVAILABLE",
                "model_id": "sealsense-baseline-v1",
                "error": self._load_error or "Model not loaded",
                "prediction": "unknown",
                "score": 0.0,
            }

        t0 = time.time()
        audio = np.asarray(audio_data, dtype=np.float32)
        if audio.ndim > 1:
            audio = np.mean(audio, axis=-1)

        # Resample to 16 kHz if necessary
        if sample_rate != TARGET_SAMPLE_RATE and len(audio) > 0:
            import math, scipy.signal
            gcd = math.gcd(sample_rate, TARGET_SAMPLE_RATE)
            audio = scipy.signal.resample_poly(audio, TARGET_SAMPLE_RATE // gcd, sample_rate // gcd).astype(np.float32)

        # Extract features
        physical_features = extract_features(audio, TARGET_SAMPLE_RATE)
        feat_vec = np.array([physical_features[k] for k in FEATURE_NAMES], dtype=np.float32).reshape(1, -1)

        pred_class = "background_noise"
        pred_confidence = 0.5
        class_probas = {}

        if model_type == "rf" and self._rf_artifact is not None:
            model = self._rf_artifact["model"]
            scaler = self._rf_artifact["scaler"]
            scaled_x = scaler.transform(feat_vec)
            probas = model.predict_proba(scaled_x)[0]
            classes = self._rf_artifact["classes"]

            top_idx = int(np.argmax(probas))
            pred_class = classes[top_idx]
            pred_confidence = float(probas[top_idx])
            class_probas = {classes[i]: float(round(probas[i], 4)) for i in range(len(classes))}
            active_model_id = self._rf_artifact.get("model_id", "sealsense-rf-baseline-v1")

        elif self._cnn_model is not None:
            # Extract 2D Log-Mel
            log_mel = extract_log_mel_spectrogram(audio, TARGET_SAMPLE_RATE, n_mels=64)
            tensor_x = torch.from_numpy(log_mel).unsqueeze(0).unsqueeze(0)  # (1, 1, 64, T)
            with torch.no_grad():
                probas = self._cnn_model.predict_proba(tensor_x)[0].numpy()

            top_idx = int(np.argmax(probas))
            pred_class = CLASS_NAMES[top_idx]
            pred_confidence = float(probas[top_idx])
            class_probas = {CLASS_NAMES[i]: float(round(probas[i], 4)) for i in range(len(CLASS_NAMES))}
            active_model_id = "sealsense-cnn-baseline-v1"
        else:
            active_model_id = "sealsense-rf-baseline-v1"

        duration_ms = int((time.time() - t0) * 1000)

        confidence_band = "high" if pred_confidence >= 0.8 else ("medium" if pred_confidence >= 0.5 else "low")

        return {
            "status": "READY",
            "model_id": active_model_id,
            "prediction": pred_class,
            "score": round(pred_confidence, 4),
            "confidence_band": confidence_band,
            "inference_duration_ms": max(1, duration_ms),
            "class_probabilities": class_probas,
            "physical_features": physical_features,
            "domain_guardrail": "Authentic stored-grain physical acoustic baseline model. Not correlated with generic outdoor biodiversity taxonomy.",
        }

    def predict_wav_bytes(self, wav_bytes: bytes, model_type: str = "rf") -> Dict[str, Any]:
        """Executes inference on raw WAV file bytes."""
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            sr = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)

        dtype = np.int16 if sampwidth == 2 else np.int32
        audio = np.frombuffer(raw, dtype=dtype)
        if n_channels > 1:
            audio = audio.reshape(-1, n_channels).mean(axis=-1)

        scale = 32768.0 if sampwidth == 2 else 2147483648.0
        audio = audio.astype(np.float32) / scale
        return self.predict(audio, sample_rate=sr, model_type=model_type)
