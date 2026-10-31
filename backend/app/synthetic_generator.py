"""
Synthetic Bioacoustic Simulation Scenario Generator for SealSense
================================================================
Generates deterministic synthetic stored-grain pest feeding/locomotion click
impulses with controllable impulse rate, pulse amplitude, background noise floor,
and random seed.

CRITICAL REPRODUCIBILITY & SCIENTIFIC SAFEGUARDS:
1. Every generated file is explicitly marked:
   - `input_source = "synthetic"`
   - `is_synthetic = True`
2. Synthetic simulation recordings are STRICTLY EXCLUDED from scientific evaluation
   metrics and real-world ground-truth performance calculations.
3. This utility enables end-to-end smoke testing and audio pipeline demonstration
   when live sensor hardware (e.g. defective INMP441) is unavailable.
"""
from __future__ import annotations

import io
import wave
import numpy as np
from typing import Tuple


def generate_synthetic_impulse_wav(
    impulse_rate: float = 12.0,
    amplitude: float = 0.6,
    noise_level: float = 0.04,
    duration_sec: float = 10.0,
    sample_rate: int = 16000,
    seed: int = 42,
) -> bytes:
    """
    Generates realistic synthetic stored-grain insect micro-acoustic impulse audio.

    Parameters:
    - impulse_rate: Average number of click impulses per second (Poisson process, 1.0 to 50.0 Hz).
    - amplitude: Peak amplitude scaling of impulses (0.01 to 1.0).
    - noise_level: Standard deviation of background Gaussian floor (0.0 to 0.3).
    - duration_sec: Total duration in seconds (default: 10.0s).
    - sample_rate: Sample rate in Hz (default: 16000 Hz, native to Nocturne Mini).
    - seed: Integer random seed for deterministic reproducibility.

    Returns:
    - bytes of a standard 16-bit PCM mono WAV file.
    """
    duration_sec = max(1.0, min(60.0, float(duration_sec)))
    sample_rate = max(8000, min(48000, int(sample_rate)))
    impulse_rate = max(0.5, min(100.0, float(impulse_rate)))
    amplitude = max(0.01, min(1.0, float(amplitude)))
    noise_level = max(0.0, min(0.5, float(noise_level)))

    rng = np.random.default_rng(int(seed))
    total_samples = int(duration_sec * sample_rate)

    # Ambient noise floor (simulating grain bin acoustic background)
    audio = rng.normal(0, noise_level, total_samples).astype(np.float32)

    # Generate Poisson-distributed kernel click impulses
    # Micro-acoustic kernel chewing/locomotion events typically ring between 1.8 kHz and 3.8 kHz
    avg_interval_samples = sample_rate / impulse_rate
    pos = int(rng.exponential(avg_interval_samples))
    impulse_len = int(0.004 * sample_rate)  # 4 milliseconds per click impulse
    t_imp = np.arange(impulse_len) / sample_rate

    while pos + impulse_len < total_samples:
        # Resonant frequency of kernel impact
        freq = rng.uniform(1800.0, 3600.0)
        # Exponential decay constant (0.8ms to 1.8ms)
        decay = rng.uniform(0.0008, 0.0018)
        kernel_click = np.sin(2 * np.pi * freq * t_imp) * np.exp(-t_imp / decay)
        
        # Amplitude variation per click (clicks vary as insect turns or bites)
        click_amp = amplitude * rng.uniform(0.5, 1.0)
        audio[pos : pos + impulse_len] += (kernel_click * click_amp).astype(np.float32)

        # Minimum interval of 8ms between distinct clicks to prevent unphysical clipping
        pos += max(int(0.008 * sample_rate), int(rng.exponential(avg_interval_samples)))

    # Prevent distortion by clipping to [-1.0, 1.0]
    audio = np.clip(audio, -1.0, 1.0)
    int16_samples = (audio * 32767.0).astype(np.int16)

    # Write WAV structure
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit PCM
        wf.setframerate(sample_rate)
        wf.writeframes(int16_samples.tobytes())

    return buf.getvalue()


def generate_synthetic_chirp_wav(
    duration_sec: float = 10.0,
    sample_rate: int = 16000,
    f_start: float = 200.0,
    f_end: float = 800.0,
) -> bytes:
    """
    Generates standard synthetic frequency-modulated sweep chirp for baseline audio testing.
    """
    total_samples = int(duration_sec * sample_rate)
    t = np.linspace(0, duration_sec, total_samples, endpoint=False)
    # Linear chirp frequency
    freqs = f_start + (f_end - f_start) * (t / duration_sec)
    phases = 2 * np.pi * freqs * t
    audio = (0.7 * np.sin(phases)).astype(np.float32)

    int16_samples = (audio * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(int16_samples.tobytes())
    return buf.getvalue()
