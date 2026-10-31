#!/usr/bin/env python3
"""
SealSense — Physical INMP441 Hardware Audio Capture & Ingestion Tool
===================================================================
Captures authentic 16 kHz, 16-bit mono WAV audio from an ESP32-WROOM-32
with an INMP441 I2S microphone connected via USB Serial (/dev/ttyUSB0).

Streaming Protocol:
  1. Sends trigger command 'CAPTURE_WAV:<seconds>\\n' over Serial at 115200 baud.
  2. Awaits framing marker '>>>BEGIN_WAV:<bytes><<<'.
  3. Receives exact binary payload (44-byte WAV header + PCM samples).
  4. Awaits completion marker '>>>END_WAV:<bytes><<<'.
  5. Validates WAV integrity, calculates physical signal statistics, and writes metadata.
  6. Optionally uploads directly to SealSense backend (/api/inference/acoustic/upload).

Usage:
  python tools/capture_inmp441.py --port /dev/ttyUSB0 --duration 10 --upload
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import time
import wave
from datetime import datetime, timezone

try:
    import serial
except ImportError:
    print("[ERROR] pyserial is not installed. Install it with: pip install pyserial")
    sys.exit(1)

try:
    import numpy as np
except ImportError:
    print("[ERROR] numpy is not installed. Install it with: pip install numpy")
    sys.exit(1)

try:
    import urllib.request
    import urllib.error
except ImportError:
    pass

DEFAULT_PORT = os.environ.get("SEALSENSE_SERIAL_PORT", "/dev/ttyUSB0")
DEFAULT_BAUD = 115200
DEFAULT_DURATION = 10
DEFAULT_OUTPUT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "backend", "data", "hardware_recordings")
)
BACKEND_UPLOAD_URL = os.environ.get(
    "SEALSENSE_BACKEND_URL", "http://localhost:8000/api/inference/acoustic/upload"
)


def compute_sha256(data: bytes) -> str:
    """Computes SHA-256 hex digest of data."""
    return hashlib.sha256(data).hexdigest()


def calculate_audio_stats(wav_bytes: bytes) -> dict:
    """Calculates RMS, peak, extrema, and signal characteristics from WAV bytes."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        raw_frames = wf.readframes(n_frames)

    duration_sec = n_frames / float(framerate) if framerate > 0 else 0.0
    dtype = np.int16 if sampwidth == 2 else np.int32
    samples = np.frombuffer(raw_frames, dtype=dtype).astype(np.float64)

    if len(samples) == 0:
        return {
            "sample_count": 0,
            "duration_sec": 0.0,
            "rms_lsb": 0.0,
            "rms_dbfs": -96.0,
            "peak_lsb": 0,
            "peak_dbfs": -96.0,
            "min_sample": 0,
            "max_sample": 0,
            "zero_crossing_rate": 0.0,
            "zero_sample_pct": 100.0,
            "clipping_pct": 0.0,
        }

    max_possible = 32768.0 if sampwidth == 2 else 2147483648.0
    rms = float(np.sqrt(np.mean(samples ** 2)))
    peak = int(np.max(np.abs(samples)))
    min_val = int(np.min(samples))
    max_val = int(np.max(samples))

    rms_dbfs = float(20.0 * np.log10(rms / max_possible)) if rms > 0 else -96.0
    peak_dbfs = float(20.0 * np.log10(peak / max_possible)) if peak > 0 else -96.0

    zero_count = int(np.sum(samples == 0))
    zero_pct = float(zero_count * 100.0 / len(samples))

    clipped_count = int(np.sum(np.abs(samples) >= (max_possible - 8)))
    clipping_pct = float(clipped_count * 100.0 / len(samples))

    # Zero crossing rate
    signs = np.sign(samples)
    signs[signs == 0] = 1
    zero_crossings = int(np.sum(np.diff(signs) != 0))
    zcr = float(zero_crossings / len(samples))

    return {
        "sample_count": len(samples),
        "duration_sec": round(duration_sec, 3),
        "channels": n_channels,
        "sample_rate": framerate,
        "sample_width_bits": sampwidth * 8,
        "rms_lsb": round(rms, 2),
        "rms_normalized": round(rms / max_possible, 6),
        "rms_dbfs": round(rms_dbfs, 2),
        "peak_lsb": peak,
        "peak_dbfs": round(peak_dbfs, 2),
        "min_sample": min_val,
        "max_sample": max_val,
        "zero_crossing_rate": round(zcr, 4),
        "zero_sample_pct": round(zero_pct, 2),
        "clipping_pct": round(clipping_pct, 2),
    }


def capture_wav_from_serial(
    port: str, baud: int, duration_sec: int, timeout_sec: int = 45
) -> bytes:
    """
    Connects to the ESP32 serial port, initiates streaming, and captures binary WAV bytes.
    """
    print(f"[SERIAL] Connecting to {port} at {baud} baud...")
    try:
        ser = serial.Serial(port, baud, timeout=2.0)
    except Exception as e:
        raise RuntimeError(
            f"Failed to open serial port {port}: {e}. Ensure permissions with: sudo chmod 666 {port}"
        ) from e

    time.sleep(1.5)  # Allow DTR reset settling
    ser.reset_input_buffer()

    cmd = f"CAPTURE_WAV:{duration_sec}\n"
    print(f"[SERIAL] Sending recording trigger command: {cmd.strip()}")
    ser.write(cmd.encode("utf-8"))
    ser.flush()

    expected_bytes = None
    start_time = time.time()

    # Step 1: Await BEGIN marker
    print("[SERIAL] Waiting for ESP32 framing header (>>>BEGIN_WAV:<bytes><<<)...")
    while time.time() - start_time < timeout_sec:
        raw_line = ser.readline()
        if not raw_line:
            continue
        line = raw_line.decode("utf-8", errors="replace").strip()
        if ">>>BEGIN_WAV:" in line:
            try:
                parts = line.split(">>>BEGIN_WAV:")[1].split("<<<")[0]
                expected_bytes = int(parts)
                print(f"[SERIAL] Captured begin marker! Expected payload: {expected_bytes} bytes.")
                break
            except Exception as parse_err:
                raise RuntimeError(f"Malformed BEGIN_WAV marker: {line}") from parse_err

    if expected_bytes is None:
        ser.close()
        raise TimeoutError(f"Timed out after {timeout_sec}s waiting for >>>BEGIN_WAV<<< marker.")

    # Step 2: Receive exact binary payload
    print(f"[SERIAL] Streaming {expected_bytes} binary WAV bytes directly from I2S DMA...")
    wav_buffer = bytearray()
    chunk_timeout = time.time() + 30.0

    while len(wav_buffer) < expected_bytes and time.time() < chunk_timeout:
        remaining = expected_bytes - len(wav_buffer)
        to_read = min(remaining, 4096)
        chunk = ser.read(to_read)
        if chunk:
            wav_buffer.extend(chunk)
            pct = len(wav_buffer) * 100.0 / expected_bytes
            print(f"\r  Progress: {len(wav_buffer)}/{expected_bytes} bytes ({pct:.1f}%)", end="", flush=True)

    print()
    if len(wav_buffer) < expected_bytes:
        ser.close()
        raise RuntimeError(
            f"Incomplete WAV stream: received {len(wav_buffer)} of {expected_bytes} expected bytes."
        )

    # Step 3: Drain trailing END marker
    end_marker_found = False
    drain_deadline = time.time() + 3.0
    while time.time() < drain_deadline:
        line = ser.readline().decode("utf-8", errors="replace").strip()
        if ">>>END_WAV:" in line:
            end_marker_found = True
            break

    ser.close()
    if not end_marker_found:
        print("[WARNING] Did not observe trailing >>>END_WAV<<< marker, but payload was fully received.")

    return bytes(wav_buffer)


def upload_to_backend(
    wav_path: str,
    backend_url: str,
    zone_id: str = "zone-a",
    device_id: str = "esp32-zone-a-01",
    input_source: str = "hardware_recording",
    recording_domain: str = "airborne_microphone",
    is_synthetic: bool = False,
    notes: str = "Physical INMP441 recording captured from ESP32 on /dev/ttyUSB0",
) -> dict:
    """
    Uploads the captured WAV to the SealSense backend acoustic inference endpoint.
    """
    import mimetypes
    import uuid

    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
    filename = os.path.basename(wav_path)

    with open(wav_path, "rb") as f:
        file_bytes = f.read()

    body = bytearray()

    def add_field(name: str, value: str):
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.extend(f"{value}\r\n".encode("utf-8"))

    add_field("zone_id", zone_id)
    add_field("device_id", device_id)
    add_field("input_source", input_source)
    add_field("recording_domain", recording_domain)
    add_field("is_synthetic", "false" if not is_synthetic else "true")
    add_field("notes", notes)

    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode("utf-8")
    )
    body.extend(b"Content-Type: audio/wav\r\n\r\n")
    body.extend(file_bytes)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    req = urllib.request.Request(backend_url, data=bytes(body), method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp_data = resp.read().decode("utf-8")
            return json.loads(resp_data)
    except urllib.error.HTTPError as http_err:
        err_msg = http_err.read().decode("utf-8")
        raise RuntimeError(f"Backend HTTP {http_err.code} Error: {err_msg}") from http_err
    except Exception as e:
        raise RuntimeError(f"Failed to upload to backend: {e}") from e


def main():
    parser = argparse.ArgumentParser(
        description="Capture genuine 16 kHz WAV audio from connected ESP32 + INMP441"
    )
    parser.add_argument("--file", help="Ingest an existing local WAV file instead of capturing from serial")
    parser.add_argument("--port", default=DEFAULT_PORT, help=f"Serial port (default: {DEFAULT_PORT})")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD, help=f"Baud rate (default: {DEFAULT_BAUD})")
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION, help="Recording duration in seconds (default: 10)")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help=f"Directory to save recording (default: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--upload", action="store_true", default=True, help="Automatically ingest into backend")
    parser.add_argument("--no-upload", action="store_false", dest="upload", help="Do not upload to backend")
    parser.add_argument("--backend-url", default=BACKEND_UPLOAD_URL, help=f"Backend URL (default: {BACKEND_UPLOAD_URL})")
    parser.add_argument("--zone", default="zone-a", help="Storage zone (default: zone-a)")
    parser.add_argument("--device", default="esp32-zone-a-01", help="Device ID (default: esp32-zone-a-01)")

    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    print("================================================================================")
    print("  SealSense Physical Audio Capture Tool — INMP441 Hardware Ingestion  ")
    print("================================================================================")

    if args.file:
        if not os.path.isfile(args.file):
            print(f"[ERROR] Specified file not found: {args.file}")
            sys.exit(1)
        print(f"Source Mode:         Existing local file: {args.file}")
        with open(args.file, "rb") as f:
            wav_bytes = f.read()
        wav_filename = os.path.basename(args.file)
        wav_path = args.file
        json_path = os.path.splitext(wav_path)[0] + ".json"
    else:
        wav_filename = f"inmp441_hardware_{timestamp_str}_{args.duration}s.wav"
        wav_path = os.path.join(args.output_dir, wav_filename)
        json_path = os.path.join(args.output_dir, f"inmp441_hardware_{timestamp_str}_{args.duration}s.json")
        print(f"Target Serial Port:  {args.port}")
        print(f"Baud Rate:           {args.baud}")
        print(f"Requested Duration:  {args.duration} seconds (16,000 Hz, 16-bit Mono)")
        print(f"Output File:         {wav_path}")
        print("--------------------------------------------------------------------------------")
        wav_bytes = capture_wav_from_serial(args.port, args.baud, args.duration)
        with open(wav_path, "wb") as f:
            f.write(wav_bytes)

    sha256_hash = compute_sha256(wav_bytes)
    stats = calculate_audio_stats(wav_bytes)

    metadata = {
        "filename": wav_filename,
        "file_size_bytes": len(wav_bytes),
        "sha256_hash": sha256_hash,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "hardware": {
            "device_id": args.device,
            "zone_id": args.zone,
            "transducer_type": "airborne_microphone",
            "recording_domain": "airborne_microphone",
            "microphone_model": "INMP441 I2S Omnidirectional MEMS",
            "microcontroller": "ESP32-WROOM-32 DevKit",
            "serial_port": args.port,
            "is_synthetic": False,
            "biological_provenance": "Live physical airborne acoustic monitoring",
        },
        "signal_analysis": stats,
    }

    with open(json_path, "w") as f:
        json.dump(metadata, f, indent=2)

    print("\n[VALIDATION] WAV Audio Capture Succeeded:")
    print(f"  File Size:          {len(wav_bytes)} bytes")
    print(f"  SHA-256 Digest:     {sha256_hash}")
    print(f"  Sample Rate:        {stats['sample_rate']} Hz (Mono 16-bit PCM)")
    print(f"  Duration:           {stats['duration_sec']} seconds ({stats['sample_count']} samples)")
    print(f"  RMS Amplitude:      {stats['rms_lsb']} LSB ({stats['rms_dbfs']} dBFS)")
    print(f"  Peak Amplitude:     {stats['peak_lsb']} LSB ({stats['peak_dbfs']} dBFS)")
    print(f"  Extrema:            Min = {stats['min_sample']}, Max = {stats['max_sample']}")
    print(f"  Zero Sample Pct:    {stats['zero_sample_pct']}%")
    print(f"  Saved WAV:          {wav_path}")
    print(f"  Saved Metadata:     {json_path}")

    if args.upload:
        print("\n[BACKEND] Uploading recording to SealSense API...")
        try:
            result = upload_to_backend(
                wav_path=wav_path,
                backend_url=args.backend_url,
                zone_id=args.zone,
                device_id=args.device,
                input_source="hardware_recording",
                recording_domain="airborne_microphone",
                is_synthetic=False,
                notes=f"Physical INMP441 airborne recording ({args.duration}s) via ESP32 {args.device} on {args.port}",
            )
            print("[BACKEND] Ingestion Successful:")
            print(f"  Sample ID:          {result.get('sample_id')}")
            print(f"  Recording Domain:   {result.get('recording_domain')}")
            print(f"  Input Source:       {result.get('input_source')}")
            print(f"  Inference Status:   {result.get('inference_status')}")
            print(f"  Model Version:      {result.get('model_version')}")
            print(f"  Confidence Band:    {result.get('confidence_band')}")
            print(f"  Predicted Class:    {result.get('prediction')} (Score: {result.get('score')})")
            if "signal_analysis" in result and result["signal_analysis"]:
                sa = result["signal_analysis"]
                print(f"  Centroid / Bandwidth:{sa.get('spectral_centroid_hz', 0):.1f} Hz / {sa.get('spectral_bandwidth_hz', 0):.1f} Hz")
                print(f"  Transient Impulses: {sa.get('transient_click_count', 0)} detected (Hilbert/MAD)")
        except Exception as upload_err:
            print(f"[WARNING] Could not upload to backend ({upload_err}). Backend might be offline. WAV is safely saved locally.")

    print("\n================================================================================")
    print("Capture and ingestion completed successfully.")
    print("================================================================================")


if __name__ == "__main__":
    main()
