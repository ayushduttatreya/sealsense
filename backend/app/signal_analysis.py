"""
Bioacoustic Signal Analysis Module for SealSense
=================================================
Calculates physical acoustic characteristics for stored-grain acoustic and
vibrational recordings without claiming biological pest identification.

Metrics computed:
- RMS energy & RMS dB
- Peak amplitude & Peak dBFS
- Spectral centroid (Hz)
- Spectral bandwidth (Hz)
- Spectral flatness (Wiener entropy, [0, 1])
- Zero-crossing rate (fraction & crossings/sec)
- Band-energy distribution (Sub-1k, 1k-4k, 4k-8k, Ultrasonic >8k)
- Transient / impulse counts via 800 Hz high-pass filtering, Hilbert analytic
  signal envelope extraction, and adaptive MAD thresholding with an 8 ms refractory period.

CRITICAL SCIENTIFIC SAFEGUARD:
These measurements are acoustic signal physical properties, NOT biological diagnoses.
"""
from __future__ import annotations

import io
import wave
import logging
from typing import Dict, Any, Union, Optional
import numpy as np

log = logging.getLogger("sealsense.signal_analysis")


def analyze_signal(
    audio: np.ndarray,
    sample_rate: int,
    impulse_hp_cutoff: float = 800.0,
    mad_multiplier: float = 5.0,
    refractory_sec: float = 0.008,
) -> Dict[str, Any]:
    """
    Computes comprehensive physical signal characteristics from a mono floating-point waveform.

    Parameters:
    - audio: 1D numpy array of audio samples (typically in [-1.0, 1.0]).
    - sample_rate: Sampling frequency in Hz.
    - impulse_hp_cutoff: Cutoff frequency for transient isolation (default 800 Hz).
    - mad_multiplier: Sensitivity multiplier over median absolute deviation for impulse peaks.
    - refractory_sec: Minimum dead-time between distinct transient events (default 8 ms).
    """
    if not isinstance(audio, np.ndarray):
        audio = np.asarray(audio, dtype=np.float32)

    if audio.ndim > 1:
        # Downmix if multi-channel
        audio = np.mean(audio, axis=-1)

    n_samples = len(audio)
    if n_samples == 0:
        raise ValueError("Audio array is empty; cannot compute signal characteristics.")

    duration_sec = float(n_samples / sample_rate) if sample_rate > 0 else 0.0

    # 1. RMS Energy & RMS dB
    rms = float(np.sqrt(np.mean(audio**2)))
    rms_db = round(float(20.0 * np.log10(rms + 1e-12)), 2)
    rms = round(rms, 6)

    # 2. Peak Amplitude & Peak dBFS
    peak = float(np.max(np.abs(audio)))
    peak_dbfs = round(float(20.0 * np.log10(peak + 1e-12)), 2)
    peak = round(peak, 6)

    # 3. Spectral Moments (Centroid & Bandwidth) & Spectral Flatness
    # FFT magnitude spectrum
    X = np.abs(np.fft.rfft(audio))
    freqs = np.fft.rfftfreq(n_samples, 1.0 / sample_rate)
    sum_X = float(np.sum(X)) + 1e-12

    # Spectral centroid (center of mass)
    centroid = float(np.sum(freqs * X) / sum_X)

    # Spectral bandwidth (spread around centroid)
    bandwidth = float(np.sqrt(np.sum(((freqs - centroid) ** 2) * X) / sum_X))

    # Spectral flatness (Wiener entropy = geometric mean / arithmetic mean of power spectrum)
    power = X**2 + 1e-12
    geo_mean = float(np.exp(np.mean(np.log(power))))
    arith_mean = float(np.mean(power))
    flatness = float(geo_mean / (arith_mean + 1e-12))
    flatness = max(0.0, min(1.0, flatness))

    # 4. Zero-Crossing Rate (ZCR)
    sign_changes = np.abs(np.diff(np.signbit(audio)))
    zcr = float(np.mean(sign_changes)) if len(sign_changes) > 0 else 0.0
    zcr_per_sec = float(zcr * sample_rate)

    # 5. Band-Energy Distribution
    # Bands: 0-1kHz, 1k-4kHz, 4k-8kHz, >8kHz
    nyquist = sample_rate / 2.0
    total_power = float(np.sum(power)) + 1e-12

    mask_sub1k = freqs < min(1000.0, nyquist)
    mask_1k_4k = (freqs >= 1000.0) & (freqs < min(4000.0, nyquist))
    mask_4k_8k = (freqs >= 4000.0) & (freqs < min(8000.0, nyquist))
    mask_ultrasonic = freqs >= 8000.0

    pct_sub1k = round(float(np.sum(power[mask_sub1k]) / total_power) * 100.0, 2)
    pct_1k_4k = round(float(np.sum(power[mask_1k_4k]) / total_power) * 100.0, 2)
    pct_4k_8k = round(float(np.sum(power[mask_4k_8k]) / total_power) * 100.0, 2)
    pct_ultrasonic = round(float(np.sum(power[mask_ultrasonic]) / total_power) * 100.0, 2) if nyquist > 8000.0 else 0.0

    # Ensure sum normalization
    sum_pct = pct_sub1k + pct_1k_4k + pct_4k_8k + pct_ultrasonic
    if sum_pct > 0:
        band_distribution = {
            "sub_1k_pct": round((pct_sub1k / sum_pct) * 100.0, 2),
            "band_1k_4k_pct": round((pct_1k_4k / sum_pct) * 100.0, 2),
            "band_4k_8k_pct": round((pct_4k_8k / sum_pct) * 100.0, 2),
            "ultrasonic_8k_plus_pct": round((pct_ultrasonic / sum_pct) * 100.0, 2),
            "sub_1khz_pct": round((pct_sub1k / sum_pct) * 100.0, 2),
            "band_1k_to_4k_pct": round((pct_1k_4k / sum_pct) * 100.0, 2),
            "band_4k_to_8k_pct": round((pct_4k_8k / sum_pct) * 100.0, 2),
            "ultrasonic_gt_8k_pct": round((pct_ultrasonic / sum_pct) * 100.0, 2),
        }
    else:
        band_distribution = {
            "sub_1k_pct": 25.0,
            "band_1k_4k_pct": 25.0,
            "band_4k_8k_pct": 25.0,
            "ultrasonic_8k_plus_pct": 25.0,
            "sub_1khz_pct": 25.0,
            "band_1k_to_4k_pct": 25.0,
            "band_4k_to_8k_pct": 25.0,
            "ultrasonic_gt_8k_pct": 25.0,
        }

    # 6. Transient / Impulse Detection
    # High-pass filter above impulse_hp_cutoff to eliminate baseline environmental rumble
    transient_count = 0
    impulse_rate_hz = 0.0
    try:
        from scipy import signal
        cutoff_norm = impulse_hp_cutoff / nyquist
        if cutoff_norm < 0.95:
            b, a = signal.butter(2, cutoff_norm, btype="high")
            filtered = signal.filtfilt(b, a, audio)
        else:
            filtered = audio

        # Instantaneous amplitude envelope via Hilbert transform
        env = np.abs(signal.hilbert(filtered))

        # Dynamic threshold based on Median Absolute Deviation (MAD)
        med_val = float(np.median(env))
        mad = float(1.4826 * np.median(np.abs(env - med_val)))
        thresh = med_val + (mad_multiplier * mad)

        # Minimum distance in samples between peaks (refractory period)
        min_distance = max(1, int(refractory_sec * sample_rate))
        peaks, _ = signal.find_peaks(env, height=thresh, distance=min_distance)
        transient_count = int(len(peaks))
        impulse_rate_hz = round(float(transient_count / duration_sec), 2) if duration_sec > 0 else 0.0
    except Exception as e:
        log.warning("Transient impulse analysis encountered fallback: %s", e)
        transient_count = 0
        impulse_rate_hz = 0.0

    method_str = (
        f"Transient clicks detected via {int(impulse_hp_cutoff)} Hz 2-pole Butterworth highpass filter, "
        f"Hilbert transform analytic signal envelope, and adaptive thresholding ({mad_multiplier:.1f}x MAD above median) "
        f"with a {int(refractory_sec * 1000)} ms refractory period. Band energy distribution calculated across 4 discrete spectral regimes."
    )

    return {
        "rms_energy": rms,
        "rms_db": rms_db,
        "peak_amplitude": peak,
        "peak_dbfs": peak_dbfs,
        "spectral_centroid_hz": round(centroid, 1),
        "spectral_bandwidth_hz": round(bandwidth, 1),
        "spectral_flatness": round(flatness, 6),
        "zero_crossing_rate": round(zcr, 6),
        "zero_crossings_per_sec": round(zcr_per_sec, 1),
        "band_energy_distribution": band_distribution,
        "transient_click_count": transient_count,
        "transient_clicks_per_sec": impulse_rate_hz,
        "transient_impulse_count": transient_count,
        "impulse_rate_hz": impulse_rate_hz,
        "transient_detection_method": method_str,
        "duration_sec": round(duration_sec, 2),
        "analyzed_sample_rate": sample_rate,
        "method_notes": method_str,
        "scientific_disclaimer": (
            "Acoustic signal physical characteristics only. Transient impulse counts and spectral moments describe "
            "vibrational dynamics and waveform geometry; they do NOT confirm insect presence or taxonomic identification."
        ),
    }


def analyze_wav_bytes(wav_bytes: bytes) -> Dict[str, Any]:
    """
    Decodes a standard PCM WAV byte string and computes signal characteristics at its native sample rate.
    """
    with io.BytesIO(wav_bytes) as buf:
        with wave.open(buf, "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            sample_rate = wf.getframerate()
            n_frames = wf.getnframes()
            frames = wf.readframes(n_frames)

    if sampwidth == 2:
        raw_int = np.frombuffer(frames, dtype=np.int16)
        audio = raw_int.astype(np.float32) / 32768.0
    elif sampwidth == 4:
        raw_int = np.frombuffer(frames, dtype=np.int32)
        audio = raw_int.astype(np.float32) / 2147483648.0
    elif sampwidth == 1:
        raw_int = np.frombuffer(frames, dtype=np.uint8)
        audio = (raw_int.astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"Unsupported WAV sample width: {sampwidth} bytes")

    if n_channels > 1:
        audio = audio.reshape(-1, n_channels)
        audio = np.mean(audio, axis=1)

    return analyze_signal(audio, sample_rate)
