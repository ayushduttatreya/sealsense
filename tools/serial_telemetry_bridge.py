#!/usr/bin/env python3
"""
SealSense Serial Telemetry Bridge
=================================
Reads framed JSON telemetry (prefix 'SEALSENSE_JSON:') or structured hardware test
telemetry from ESP32 over USB Serial, validates the payload, and forwards it to the
SealSense FastAPI telemetry API.

Features:
  - Process Mutex Lock (/tmp/sealsense_serial_bridge.lock) prevents multiple competing instances
  - Kernel Exclusive Port Locking (TIOCEXCL / exclusive=True) blocks external port contention
  - Explicit DTR/RTS management prevents unwanted ESP32 resets on connection
  - Persistent device discovery preferring /dev/serial/by-id/ symlinks
  - Clear distinction between normal idle timeouts and hardware disconnections
  - Actionable diagnostics for permission failures (dialout group) and busy ports
  - Bounded exponential backoff on reconnection with graceful teardown
  - Support for both production framed JSON and diagnostic telemetry blocks
  - Simulation fallback mode (--mock)

Usage:
    python tools/serial_telemetry_bridge.py [--port /dev/ttyUSB0] [--baud 115200] [--url http://localhost:8000/api/telemetry]
    python tools/serial_telemetry_bridge.py --mock
"""

import sys
import os
import time
import json
import argparse
import logging
import stat
import grp
import getpass
import re
import fcntl
import signal
from datetime import datetime, timezone
import urllib.request
import urllib.error

# Configure clean, informative logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("sealsense_bridge")

PREFIX = "SEALSENSE_JSON:"
LOCK_FILE_PATH = "/tmp/sealsense_serial_bridge.lock"

# Structured telemetry patterns for live hardware test firmware
RE_HEADER = re.compile(r"\[TELEMETRY @ \d+ s\] Node:\s*(\S+)\s*\|\s*Zone:\s*(\S+)")
RE_SCD41 = re.compile(r"SCD41 Climate:\s+CO2 = ([\d\.]+) ppm \| Temp = ([\d\.]+) °C \| Air RH = ([\d\.]+) %")
RE_INMP441 = re.compile(r"INMP441 Audio:\s+RMS = ([\d\.]+) LSB \(([-\d\.]+) dBFS\) \| Peak = (\d+) LSB \(([-\d\.]+) dBFS\)")


def acquire_instance_lock(lock_path: str = LOCK_FILE_PATH) -> int:
    """
    Acquires an exclusive OS-level file lock to ensure only ONE instance of the
    serial bridge runs at a time. Returns the file descriptor or exits cleanly.
    """
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o666)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.ftruncate(lock_fd, 0)
        os.write(lock_fd, f"{os.getpid()}\n".encode("utf-8"))
        return lock_fd
    except (BlockingIOError, OSError):
        try:
            with open(lock_path, "r") as f:
                other_pid = f.read().strip()
        except Exception:
            other_pid = "unknown"
        log.error(
            f"\n{'='*78}\n"
            f"  [DUPLICATE INSTANCE BLOCKED] Another SealSense bridge is running (PID: {other_pid})!\n"
            f"  The ESP32 serial port requires exactly ONE owner to prevent port contention,\n"
            f"  interrupted reads, and endless reboot cycles.\n\n"
            f"  To stop the running instance:\n"
            f"    kill {other_pid}\n"
            f"  To check port owners:\n"
            f"    sudo fuser -v /dev/ttyUSB0\n"
            f"{'='*78}\n"
        )
        sys.exit(0)


def release_instance_lock(lock_fd: int):
    """Releases the instance lock file."""
    if lock_fd is not None:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        except Exception:
            pass
        try:
            if os.path.exists(LOCK_FILE_PATH):
                os.remove(LOCK_FILE_PATH)
        except Exception:
            pass


def resolve_serial_port(requested_port: str = None) -> tuple[str, str]:
    """
    Resolves the serial device path, preferring stable persistent symlinks in /dev/serial/by-id/.
    Returns (active_path, display_info).
    """
    by_id_dir = "/dev/serial/by-id"
    if os.path.isdir(by_id_dir):
        try:
            entries = [os.path.join(by_id_dir, e) for e in os.listdir(by_id_dir)]
            # Match CP210x, FTDI, CH340, or generic USB-UART bridges
            uart_entries = [e for e in entries if any(k in e for k in ("CP210", "USB", "UART", "ESP32"))]
            if uart_entries:
                best_link = uart_entries[0]
                target_real = os.path.realpath(best_link)
                # If user didn't specify a custom port or asked for default /dev/ttyUSB0, prefer the persistent symlink
                if not requested_port or requested_port == "/dev/ttyUSB0" or requested_port == target_real:
                    return best_link, f"{best_link} -> {target_real}"
        except Exception as e:
            log.debug(f"Error inspecting /dev/serial/by-id: {e}")

    port = requested_port or "/dev/ttyUSB0"
    return port, port


def check_port_permissions(port: str) -> tuple[bool, str]:
    """Inspects file existence, character device type, ownership, and user permissions."""
    real_path = os.path.realpath(port)
    if not os.path.exists(real_path):
        return False, f"Device node '{port}' (canonical: '{real_path}') does not exist. (Is the ESP32 plugged in?)"

    try:
        st = os.stat(real_path)
        mode = st.st_mode
        if not stat.S_ISCHR(mode):
            return False, f"'{real_path}' exists but is not a character device."

        try:
            group_name = grp.getgrgid(st.st_gid).gr_name
        except KeyError:
            group_name = str(st.st_gid)

        current_user = getpass.getuser()
        try:
            current_groups = [grp.getgrgid(g).gr_name for g in os.getgroups()]
        except Exception:
            current_groups = []

        is_readable = os.access(real_path, os.R_OK)
        is_writable = os.access(real_path, os.W_OK)

        if not (is_readable and is_writable):
            msg = (
                f"\n{'='*78}\n"
                f"  [PERMISSION DENIED] Cannot access serial device '{real_path}'!\n"
                f"  Device Owner: root | Device Group: {group_name} (Mode: {oct(stat.S_IMODE(mode))})\n"
                f"  Current User: {current_user} (Groups: {', '.join(current_groups)})\n\n"
                f"  SOLUTION:\n"
                f"    1) Add your user to the '{group_name}' group:\n"
                f"         sudo usermod -aG {group_name} \"$USER\"\n\n"
                f"    2) For immediate access in your active terminal, run:\n"
                f"         newgrp {group_name}\n"
                f"       (Or log out and log back in to apply system-wide).\n"
                f"{'='*78}"
            )
            return False, msg

        return True, "OK"
    except Exception as ex:
        return False, f"Error checking permissions on '{port}': {ex}"


def forward_to_backend(url: str, payload: dict, timeout_sec: float = 3.0) -> bool:
    """Posts JSON payload to FastAPI backend via urllib."""
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "SealSense-SerialBridge/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return resp.status in (200, 201)
    except urllib.error.HTTPError as e:
        log.error(f"Backend HTTP error {e.code}: {e.reason}")
        return False
    except urllib.error.URLError as e:
        log.warning(f"Backend unreachable at {url}: {e.reason}")
        return False
    except Exception as e:
        log.error(f"Unexpected error posting to backend: {e}")
        return False


def run_bridge(requested_port: str, baud: int, url: str, verbose: bool = False):
    """
    Connects to serial port, processes lines, and forwards telemetry with:
      - Exclusive kernel port locking (TIOCEXCL)
      - Suppressed DTR/RTS pulsing to prevent ESP32 resets
      - Accurate idle timeout vs disconnection detection
      - Bounded exponential backoff
    """
    try:
        import serial
    except ImportError:
        log.error("pyserial is required. Install via: pip install pyserial")
        sys.exit(1)

    # Acquire system-wide process lock
    lock_fd = acquire_instance_lock()

    resolved_port, port_info = resolve_serial_port(requested_port)

    log.info("Starting SealSense Telemetry Bridge...")
    log.info(f"Target Serial Port : {port_info} @ {baud} baud")
    log.info(f"Target Backend API : {url}")
    log.info(f"Framing Prefix     : '{PREFIX}'")
    log.info("Press Ctrl+C to stop.")

    forward_count = 0
    last_timestamp = None
    current_block = None
    ser = None

    # Bounded exponential backoff parameters
    backoff = 1.0
    min_backoff = 1.0
    max_backoff = 10.0
    permission_warned = False
    stop_requested = False

    def handle_signal(sig, frame):
        nonlocal stop_requested
        stop_requested = True
        log.info("\nStopping SealSense Telemetry Bridge. Goodbye!")
        if ser:
            try:
                ser.close()
            except Exception:
                pass
        release_instance_lock(lock_fd)
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        while not stop_requested:
            # Reconnection loop
            if ser is None:
                # Re-resolve port dynamically in case device was re-plugged
                resolved_port, port_info = resolve_serial_port(requested_port)

                # Check file existence and group permissions
                perm_ok, perm_msg = check_port_permissions(resolved_port)
                if not perm_ok:
                    if not permission_warned:
                        log.error(perm_msg)
                        permission_warned = True
                    else:
                        log.warning(f"Waiting for '{resolved_port}'... retrying in {backoff:.1f}s")
                    time.sleep(backoff)
                    backoff = min(backoff * 1.5, max_backoff)
                    continue

                try:
                    # Configure port explicitly before opening to prevent DTR/RTS auto-reset glitches
                    new_ser = serial.Serial()
                    new_ser.port = resolved_port
                    new_ser.baudrate = baud
                    new_ser.timeout = 2.0  # Normal idle timeout waiting for sensor data
                    new_ser.write_timeout = 2.0
                    new_ser.rtscts = False
                    new_ser.dsrdtr = False
                    new_ser.exclusive = True  # Kernel TIOCEXCL: blocks any competing process
                    new_ser.dtr = False
                    new_ser.rts = False

                    new_ser.open()

                    # Re-assert DTR=False, RTS=False immediately to keep EN/Reset high
                    try:
                        new_ser.setDTR(False)
                        new_ser.setRTS(False)
                    except Exception:
                        pass

                    ser = new_ser
                    log.info(f"[CONNECTED] Successfully opened serial device '{port_info}' with exclusive lock!")
                    permission_warned = False
                    backoff = min_backoff  # Reset backoff on successful connection
                except serial.SerialException as e:
                    err_str = str(e).lower()
                    if "permission denied" in err_str:
                        log.error(
                            f"\n[PERMISSIONS ERROR] Permission denied opening '{resolved_port}'.\n"
                            f"Run: sudo usermod -aG dialout \"$USER\"\n"
                            f"Then activate with: newgrp dialout"
                        )
                    elif "could not exclusively lock" in err_str or "device or resource busy" in err_str or "errno 16" in err_str or "errno 11" in err_str:
                        log.error(
                            f"[PORT OCCUPIED] Serial device '{resolved_port}' is currently locked by another application!\n"
                            f"--> Another process (e.g. Arduino Serial Monitor, minicom, or duplicate bridge) has the port open.\n"
                            f"--> Run 'sudo fuser -v {resolved_port}' to inspect."
                        )
                    elif "no such file or directory" in err_str:
                        log.warning(f"Device '{resolved_port}' not found. ESP32 may be unplugged. Retrying in {backoff:.1f}s...")
                    else:
                        log.warning(f"Unable to open '{resolved_port}' ({e}). Retrying in {backoff:.1f}s...")

                    time.sleep(backoff)
                    backoff = min(backoff * 1.5, max_backoff)
                    continue
                except Exception as e:
                    log.error(f"Unexpected error opening '{resolved_port}': {e}")
                    time.sleep(backoff)
                    backoff = min(backoff * 1.5, max_backoff)
                    continue

            try:
                # Readline with timeout
                raw_line = ser.readline()

                # Handle normal idle read timeout
                if not raw_line:
                    # Check if device physically disappeared
                    if not os.path.exists(resolved_port):
                        raise serial.SerialException(f"Device node '{resolved_port}' disappeared from filesystem")
                    # Normal timeout waiting for sensor telemetry cycle (emitted every ~2.5s)
                    continue

                try:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                except Exception:
                    continue

                if not line:
                    continue

                payload = None

                # 1. Check for structured JSON prefix framing (production protocol)
                if line.startswith(PREFIX):
                    json_str = line[len(PREFIX):].strip()
                    try:
                        payload = json.loads(json_str)
                    except json.JSONDecodeError as err:
                        log.error(f"Malformed JSON in line: {err}")
                        continue

                # 2. Check for structured hardware telemetry blocks (hardware test firmware)
                elif (m_hdr := RE_HEADER.search(line)):
                    current_block = {
                        "device_id": m_hdr.group(1),
                        "zone_id": m_hdr.group(2),
                        "transport": "usb_serial",
                        "source": "REAL",
                        "firmware_version": "2.0.0-PROTOTYPE",
                    }
                elif current_block is not None and (m_scd := RE_SCD41.search(line)):
                    current_block["co2_ppm"] = float(m_scd.group(1))
                    current_block["temperature_c"] = float(m_scd.group(2))
                    current_block["relative_humidity_pct"] = float(m_scd.group(3))
                    current_block["co2_valid"] = True
                    current_block["temp_valid"] = True
                    current_block["rh_valid"] = True
                elif current_block is not None and (m_inmp := RE_INMP441.search(line)):
                    current_block["audio_rms"] = float(m_inmp.group(1))
                    current_block["audio_rms_dbfs"] = float(m_inmp.group(2))
                    current_block["audio_peak"] = int(m_inmp.group(3))
                    current_block["audio_peak_dbfs"] = float(m_inmp.group(4))
                    current_block["audio_valid"] = True
                elif current_block is not None and (line.startswith("Network Status:") or line.startswith("---")):
                    if "co2_ppm" in current_block and "audio_rms" in current_block:
                        payload = dict(current_block)
                    current_block = None

                elif verbose:
                    # Log non-telemetry serial debug prints when in verbose mode
                    print(f"[SERIAL] {line}")

                if payload is not None:
                    # Deduplication check
                    ts = payload.get("timestamp")
                    if ts and ts == last_timestamp:
                        continue
                    last_timestamp = ts

                    # Ensure transport and timestamp are populated
                    if "transport" not in payload:
                        payload["transport"] = "usb_serial"
                    if "timestamp" not in payload or not payload["timestamp"]:
                        payload["timestamp"] = datetime.now(timezone.utc).isoformat()

                    # Extract key metrics for concise logging
                    co2 = payload.get("co2_ppm")
                    temp = payload.get("temperature_c")
                    rh = payload.get("relative_humidity_pct")
                    rms = payload.get("audio_rms_dbfs")
                    dev = payload.get("device_id", "esp32")

                    success = forward_to_backend(url, payload)
                    if success:
                        forward_count += 1
                        co2_str = f"{co2:.0f} ppm" if co2 is not None else "N/A"
                        temp_str = f"{temp:.1f} °C" if temp is not None else "N/A"
                        rh_str = f"{rh:.1f} %" if rh is not None else "N/A"
                        rms_str = f"{rms:.1f} dBFS" if rms is not None else "N/A"
                        log.info(
                            f"Forwarded #{forward_count:04d} [{dev}] -> CO2: {co2_str} | Temp: {temp_str} | Air RH: {rh_str} | RMS: {rms_str} -> [HTTP 200]"
                        )
                    else:
                        log.warning(f"Failed to forward packet from {dev} to {url}")

            except (serial.SerialException, OSError) as e:
                err_text = str(e)
                if "device reports readiness to read but returned no data" in err_text:
                    if os.path.exists(resolved_port):
                        log.error(
                            f"[COMPETING ACCESS DETECTED] Serial driver reported readiness but 0 bytes returned.\n"
                            f"Another process is reading from '{resolved_port}' simultaneously!\n"
                            f"Ensure all other serial monitors or terminals are closed."
                        )
                    else:
                        log.warning(f"[DISCONNECTED] USB device '{resolved_port}' was physically disconnected.")
                else:
                    log.warning(f"[DISCONNECTED] Serial communication lost on '{resolved_port}': {e}. Closing port...")

                try:
                    ser.close()
                except Exception:
                    pass
                ser = None
                time.sleep(min_backoff)

    finally:
        if ser:
            try:
                ser.close()
            except Exception:
                pass
        release_instance_lock(lock_fd)


def run_mock(url: str, interval: float = 3.0):
    """Emits live simulated telemetry if hardware is not connected."""
    import random
    log.info(f"Running MOCK Telemetry Bridge emitting to {url} every {interval}s")
    count = 0
    base_co2 = 1826.0
    base_temp = 25.4
    base_rh = 68.1

    while True:
        try:
            count += 1
            now_iso = datetime.now(timezone.utc).isoformat()
            co2 = round(base_co2 + random.uniform(-15.0, 15.0), 1)
            temp = round(base_temp + random.uniform(-0.3, 0.3), 1)
            rh = round(base_rh + random.uniform(-0.5, 0.5), 1)
            rms_dbfs = round(-35.4 + random.uniform(-3.5, 3.5), 1)
            peak_dbfs = round(rms_dbfs + random.uniform(4.0, 7.0), 1)
            rms_lsb = int((10 ** (rms_dbfs / 20.0)) * 8388608.0)
            peak_lsb = int((10 ** (peak_dbfs / 20.0)) * 8388608.0)

            payload = {
                "device_id": "demo-esp32-zone-a-01",
                "zone_id": "zone-a",
                "firmware_version": "2.0.0-MOCK",
                "timestamp": now_iso,
                "transport": "mock_generator",
                "source": "SIMULATED",
                "co2_ppm": co2,
                "temperature_c": temp,
                "relative_humidity_pct": rh,
                "co2_valid": True,
                "temp_valid": True,
                "rh_valid": True,
                "audio_rms": rms_lsb,
                "audio_peak": peak_lsb,
                "audio_rms_dbfs": rms_dbfs,
                "audio_peak_dbfs": peak_dbfs,
                "audio_valid": True,
            }

            success = forward_to_backend(url, payload)
            if success:
                log.info(f"[MOCK #{count:04d}] CO2: {co2} ppm | Temp: {temp}°C | RH: {rh}% | RMS: {rms_dbfs} dBFS -> HTTP 200")
            time.sleep(interval)
        except KeyboardInterrupt:
            log.info("Mock bridge stopped.")
            break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SealSense Serial Telemetry Bridge")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port (default: /dev/ttyUSB0, auto-resolves via /dev/serial/by-id/)")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate (default: 115200)")
    parser.add_argument("--url", default="http://localhost:8000/api/telemetry", help="Target API URL")
    parser.add_argument("--mock", action="store_true", help="Generate simulated hardware telemetry")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print all raw serial lines")

    args = parser.parse_args()

    if args.mock:
        run_mock(args.url)
    else:
        run_bridge(args.port, args.baud, args.url, args.verbose)
