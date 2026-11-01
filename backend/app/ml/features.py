"""
SealSense Acoustic Feature Extraction Pipeline
==============================================
Extracts physical acoustic, spectral, temporal, and time-frequency features
for stored-grain acoustic anomaly detection and classification.

Features:
- Time-domain: RMS, Peak, Crest factor, Zero-Crossing Rate (ZCR)
- Statistical: Kurtosis, Skewness (measuring impulsive clickiness)
- Frequency-domain: Spectral Centroid, Bandwidth, Flatness, Rolloff (85% & 95%)
- Energy Sub-bands: Sub-1kHz, 1k-4kHz, 4k-8kHz, >8kHz
- Transient/Impulse: High-pass filtered (>800 Hz) click count and impulse density
- Time-frequency: Log-Mel spectrograms for CNN architectures
"""
from __future__ import annotations

from typing import Dict, Any, List, Tuple
import numpy as np
import scipy.signal
import scipy.stats

FEATURE_NAMES = [
    "rms",
    "rms_dbfs",
    "peak",
    "peak_dbfs",
    "crest_factor",
    "zcr",
    "zcr_rate_hz",
    "kurtosis",
    "skewness",
    "spectral_centroid_hz",
    "spectral_bandwidth_hz",
    "spectral_flatness",
    "spectral_rolloff_85_hz",
    "spectral_rolloff_95_hz",
    "band_energy_sub1k",
    "band_energy_1k_4k",
    "band_energy_4k_8k",
    "band_energy_above8k",
    "impulse_count",
    "impulse_rate_hz",
    "spectral_kurtosis",
    "spectral_skewness",
]


def extract_features(audio: np.ndarray, sample_rate: int = 16000) -> Dict[str, float]:
    """
    Computes a comprehensive dictionary of physical acoustic features from a mono 1D waveform.
    """
    if not isinstance(audio, np.ndarray):
        audio = np.asarray(audio, dtype=np.float32)

    if audio.ndim > 1:
        audio = np.mean(audio, axis=-1)

    n_samples = len(audio)
    if n_samples == 0:
        return {k: 0.0 for k in FEATURE_NAMES}

    duration_sec = float(n_samples / sample_rate) if sample_rate > 0 else 0.0

    # 1. Temporal Energy
    rms = float(np.sqrt(np.mean(audio**2)))
    rms_dbfs = float(20.0 * np.log10(rms + 1e-12))
    peak = float(np.max(np.abs(audio)))
    peak_dbfs = float(20.0 * np.log10(peak + 1e-12))
    crest_factor = float(peak / (rms + 1e-9))

    # 2. Time-Domain Moments & ZCR
    sign_changes = np.abs(np.diff(np.signbit(audio)))
    zcr = float(np.mean(sign_changes)) if len(sign_changes) > 0 else 0.0
    zcr_rate_hz = float(zcr * sample_rate)

    kurt = float(scipy.stats.kurtosis(audio)) if n_samples > 3 else 0.0
    skew = float(scipy.stats.skew(audio)) if n_samples > 2 else 0.0

    # 3. Spectral Moments & Rolloff
    # Real FFT
    X = np.abs(np.fft.rfft(audio))
    freqs = np.fft.rfftfreq(n_samples, 1.0 / sample_rate)
    sum_X = float(np.sum(X)) + 1e-12

    # Centroid & Bandwidth
    centroid = float(np.sum(freqs * X) / sum_X)
    bandwidth = float(np.sqrt(np.sum(((freqs - centroid) ** 2) * X) / sum_X))

    # Spectral flatness (Wiener entropy)
    power = X**2 + 1e-12
    geo_mean = float(np.exp(np.mean(np.log(power))))
    arith_mean = float(np.mean(power))
    flatness = float(geo_mean / (arith_mean + 1e-12))
    flatness = max(0.0, min(1.0, flatness))

    # Spectral rolloff
    cum_energy = np.cumsum(power)
    total_energy = cum_energy[-1]
    idx_85 = np.searchsorted(cum_energy, 0.85 * total_energy)
    idx_95 = np.searchsorted(cum_energy, 0.95 * total_energy)
    rolloff_85 = float(freqs[min(idx_85, len(freqs) - 1)])
    rolloff_95 = float(freqs[min(idx_95, len(freqs) - 1)])

    # Spectral distribution shape
    spec_kurt = float(scipy.stats.kurtosis(X)) if len(X) > 3 else 0.0
    spec_skew = float(scipy.stats.skew(X)) if len(X) > 2 else 0.0

    # 4. Energy Bands
    m_sub1k = (freqs < 1000.0)
    m_1k_4k = (freqs >= 1000.0) & (freqs < 4000.0)
    m_4k_8k = (freqs >= 4000.0) & (freqs < 8000.0)
    m_above8k = (freqs >= 8000.0)

    e_sub1k = float(np.sum(power[m_sub1k]) / total_energy) if np.any(m_sub1k) else 0.0
    e_1k_4k = float(np.sum(power[m_1k_4k]) / total_energy) if np.any(m_1k_4k) else 0.0
    e_4k_8k = float(np.sum(power[m_4k_8k]) / total_energy) if np.any(m_4k_8k) else 0.0
    e_above8k = float(np.sum(power[m_above8k]) / total_energy) if np.any(m_above8k) else 0.0

    # 5. Impulse / Transient Detection (Adaptive MAD thresholding on 800Hz HPF envelope)
    impulse_count = 0
    try:
        if sample_rate > 1600:
            sos = scipy.signal.butter(4, 800.0, btype="highpass", fs=sample_rate, output="sos")
            hp_audio = scipy.signal.sosfilt(sos, audio)
            analytic_env = np.abs(scipy.signal.hilbert(hp_audio))

            med = float(np.median(analytic_env))
            mad = float(np.median(np.abs(analytic_env - med))) + 1e-9
            threshold = med + (5.0 * 1.4826 * mad)

            peaks, _ = scipy.signal.find_peaks(
                analytic_env,
                height=threshold,
                distance=max(1, int(sample_rate * 0.008)),  # 8ms refractory dead-time
            )
            impulse_count = int(len(peaks))
    except Exception:
        impulse_count = 0

    impulse_rate_hz = float(impulse_count / duration_sec) if duration_sec > 0 else 0.0

    return {
        "rms": float(rms),
        "rms_dbfs": float(rms_dbfs),
        "peak": float(peak),
        "peak_dbfs": float(peak_dbfs),
        "crest_factor": float(crest_factor),
        "zcr": float(zcr),
        "zcr_rate_hz": float(zcr_rate_hz),
        "kurtosis": float(kurt),
        "skewness": float(skew),
        "spectral_centroid_hz": float(centroid),
        "spectral_bandwidth_hz": float(bandwidth),
        "spectral_flatness": float(flatness),
        "spectral_rolloff_85_hz": float(rolloff_85),
        "spectral_rolloff_95_hz": float(rolloff_95),
        "band_energy_sub1k": float(e_sub1k),
        "band_energy_1k_4k": float(e_1k_4k),
        "band_energy_4k_8k": float(e_4k_8k),
        "band_energy_above8k": float(e_above8k),
        "impulse_count": float(impulse_count),
        "impulse_rate_hz": float(impulse_rate_hz),
        "spectral_kurtosis": float(spec_kurt),
        "spectral_skewness": float(spec_skew),
    }


def extract_feature_vector(audio: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
    """Extracts a 1D numpy array of ordered features matching FEATURE_NAMES."""
    feat_dict = extract_features(audio, sample_rate)
    return np.array([feat_dict[k] for k in FEATURE_NAMES], dtype=np.float32)


def extract_log_mel_spectrogram(
    audio: np.ndarray,
    sample_rate: int = 16000,
    n_mels: int = 64,
    n_fft: int = 512,
    hop_length: int = 160,
) -> np.ndarray:
    """
    Computes a 2D Log-Mel spectrogram array (n_mels, time_frames) normalized to zero mean & unit variance.
    """
    import torch
    import torchaudio.transforms as T

    if not isinstance(audio, np.ndarray):
        audio = np.asarray(audio, dtype=np.float32)

    tensor_audio = torch.from_numpy(audio.astype(np.float32)).unsqueeze(0)

    mel_transform = T.MelSpectrogram(
        sample_rate=sample_rate,
        n_fft=n_fft,
        win_length=n_fft,
        hop_length=hop_length,
        n_mels=n_mels,
        power=2.0,
    )
    mel_spec = mel_transform(tensor_audio)
    log_mel = torch.log(mel_spec + 1e-6).squeeze(0).numpy()

    # Standardize
    mean = np.mean(log_mel)
    std = np.std(log_mel) + 1e-6
    norm_mel = (log_mel - mean) / std

    return norm_mel.astype(np.float32)
