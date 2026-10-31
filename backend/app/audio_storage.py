"""
Persistent Audio Sample Storage Service for SealSense
====================================================
Manages filesystem storage, path traversal protection, SHA-256 duplicate
detection, and audio integrity validation for retained bioacoustic samples.
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import uuid
import wave
from typing import Optional, Tuple

log = logging.getLogger("sealsense.audio_storage")

DEFAULT_AUDIO_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "audio_samples")
)

def get_storage_dir() -> str:
    """Returns the configured or default audio storage directory."""
    dir_path = os.environ.get("SEALSENSE_AUDIO_DIR", DEFAULT_AUDIO_DIR)
    resolved = os.path.abspath(dir_path)
    os.makedirs(resolved, exist_ok=True)
    return resolved


def compute_sha256(data: bytes) -> str:
    """Computes hexadecimal SHA-256 digest of binary content."""
    return hashlib.sha256(data).hexdigest()


def validate_wav_bytes(data: bytes) -> Tuple[int, int, float]:
    """
    Validates WAV magic bytes and header structure using standard library wave module.
    Returns (channels, sample_rate, duration_sec).
    Raises ValueError on malformed or corrupted audio data.
    """
    if len(data) < 44:
        raise ValueError("Audio data too short to contain a valid WAV header (minimum 44 bytes required).")

    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("Invalid audio format: Missing RIFF/WAVE header signatures.")

    try:
        with wave.open(io.BytesIO(data), "rb") as wf:
            channels = wf.getnchannels()
            sample_rate = wf.getframerate()
            frames = wf.getnframes()
            if sample_rate <= 0:
                raise ValueError("Invalid sample rate in WAV header (must be > 0).")
            duration_sec = float(frames) / float(sample_rate)
            return channels, sample_rate, round(duration_sec, 3)
    except wave.Error as err:
        raise ValueError(f"Corrupt or unsupported WAV format: {err}") from err
    except Exception as err:
        raise ValueError(f"Failed to read WAV audio header: {err}") from err


def generate_sample_id() -> str:
    """Generates a secure, URL-safe unique identifier for an audio sample."""
    return f"samp-{uuid.uuid4().hex[:12]}"


def is_safe_filename(filename: str) -> bool:
    """Checks that a filename contains only safe characters and cannot traverse directories."""
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        return False
    return bool(re.match(r"^[A-Za-z0-9_\-\.]+$", filename))


def save_audio_file(sample_id: str, data: bytes) -> Tuple[str, str, int]:
    """
    Safely stores audio bytes on the filesystem using a unique sample ID.
    Guarantees no directory traversal and atomic write.
    Returns (stored_filename, resolved_file_path, file_size_bytes).
    """
    if not is_safe_filename(sample_id):
        raise ValueError(f"Invalid sample ID: '{sample_id}'. Cannot contain path separators or illegal characters.")

    storage_dir = get_storage_dir()
    stored_filename = f"{sample_id}.wav"
    resolved_path = os.path.abspath(os.path.join(storage_dir, stored_filename))

    # Path traversal protection check
    if os.path.commonpath([resolved_path, storage_dir]) != storage_dir:
        raise ValueError(f"Path traversal detected: {resolved_path}")

    # Atomic write to temporary file before renaming
    temp_path = f"{resolved_path}.tmp_{uuid.uuid4().hex[:8]}"
    try:
        with open(temp_path, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, resolved_path)
    except Exception as err:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        raise IOError(f"Failed to write audio file to storage: {err}") from err

    file_size = len(data)
    log.info("Persisted audio sample %s (%d bytes) to %s", sample_id, file_size, resolved_path)
    return stored_filename, resolved_path, file_size


def get_audio_file_path(stored_filename: str) -> Optional[str]:
    """
    Resolves the absolute path of a stored audio file with strict path traversal checks.
    Returns None if the file does not exist or fails safety checks.
    """
    if not is_safe_filename(stored_filename):
        log.warning("Attempted access with unsafe stored filename: %s", stored_filename)
        return None

    storage_dir = get_storage_dir()
    resolved_path = os.path.abspath(os.path.join(storage_dir, stored_filename))

    if os.path.commonpath([resolved_path, storage_dir]) != storage_dir:
        log.warning("Path traversal attempt detected in audio retrieval: %s", stored_filename)
        return None

    if not os.path.isfile(resolved_path):
        return None

    return resolved_path


def delete_audio_file(stored_filename: str) -> bool:
    """
    Safely removes a stored audio file from disk.
    Returns True if removed, False if file did not exist or was unsafe.
    """
    resolved_path = get_audio_file_path(stored_filename)
    if not resolved_path:
        return False

    try:
        os.remove(resolved_path)
        log.info("Deleted stored audio file: %s", resolved_path)
        return True
    except OSError as err:
        log.warning("Failed to delete stored audio file %s: %s", resolved_path, err)
        return False
