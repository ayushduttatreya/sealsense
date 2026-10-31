#!/usr/bin/env python3
"""
SealSense CLI Telemetry Monitor
================================
Streams live environmental and acoustic readings directly in your terminal
by querying the local FastAPI telemetry API.

Since the Python Serial Bridge holds the exclusive serial port lock,
this monitor safely reads the live database/API stream without port conflicts.

Usage:
    python tools/monitor_telemetry.py
    python tools/monitor_telemetry.py --interval 1.5
    python tools/monitor_telemetry.py --url http://localhost:8000/api/telemetry/latest
"""

import sys
import time
import json
import argparse
import urllib.request
import urllib.error
from datetime import datetime

# ANSI Color Codes
CYAN = "\033[0;36m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[1;31m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def fetch_latest_reading(api_url: str) -> dict:
    req = urllib.request.Request(
        api_url,
        headers={"User-Agent": "SealSense-CLIMonitor/1.0"},
    )
    with urllib.request.urlopen(req, timeout=2.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description="SealSense CLI Telemetry Monitor")
    parser.add_argument(
        "--url",
        default="http://localhost:8000/api/telemetry/latest",
        help="Target latest telemetry endpoint (default: http://localhost:8000/api/telemetry/latest)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Polling interval in seconds (default: 2.0)",
    )
    args = parser.parse_args()

    print(f"\n{CYAN}{BOLD}{'='*86}{RESET}")
    print(f"{CYAN}{BOLD}              SealSense — Live Terminal Telemetry Stream              {RESET}")
    print(f"{CYAN}{BOLD}{'='*86}{RESET}")
    print(f"Target API Endpoint : {GREEN}{args.url}{RESET}")
    print(f"Polling Interval    : {args.interval}s")
    print(f"Press {BOLD}Ctrl+C{RESET} to exit.\n")

    # Header
    header = (
        f"{BOLD}{'TIME (UTC)':<12} {'NODE':<16} {'CO₂ (ppm)':<12} "
        f"{'TEMP (°C)':<11} {'AIR RH (%)':<12} {'AUDIO (dBFS)':<14} {'STATUS'}{RESET}"
    )
    print(header)
    print(f"{DIM}{'-'*86}{RESET}")

    last_seen_id = None

    while True:
        try:
            data = fetch_latest_reading(args.url)
            reading = data.get("reading")
            is_hw = data.get("is_hardware", False)
            device_status = data.get("device_status", "unknown")

            if reading:
                reading_id = reading.get("id")

                # Only print when a new reading arrives or on first fetch
                if reading_id != last_seen_id:
                    last_seen_id = reading_id

                    ts = reading.get("timestamp", "")
                    time_str = ts[11:19] if len(ts) >= 19 else datetime.now().strftime("%H:%M:%S")

                    node = reading.get("device_id", "unknown")
                    co2 = reading.get("co2_ppm")
                    temp = reading.get("temperature_c")
                    rh = reading.get("relative_humidity_pct")
                    rms_dbfs = reading.get("audio_rms_dbfs")

                    # Colorize CO2
                    if co2 is not None:
                        if co2 >= 1200:
                            co2_fmt = f"{RED}{BOLD}{co2:5.0f} [CRIT]{RESET}"
                        elif co2 >= 700:
                            co2_fmt = f"{YELLOW}{BOLD}{co2:5.0f} [WARN]{RESET}"
                        else:
                            co2_fmt = f"{GREEN}{co2:5.0f} [OK]  {RESET}"
                    else:
                        co2_fmt = f"{DIM}N/A        {RESET}"

                    temp_fmt = f"{temp:5.1f} °C" if temp is not None else "  N/A  "
                    rh_fmt = f"{rh:5.1f} %" if rh is not None else "  N/A  "
                    audio_fmt = f"{rms_dbfs:5.1f} dBFS" if rms_dbfs is not None else "  N/A     "

                    status_tag = f"{GREEN}ONLINE (HW){RESET}" if is_hw else f"{CYAN}ONLINE (DEMO){RESET}"
                    if device_status == "stale":
                        status_tag = f"{YELLOW}STALE{RESET}"
                    elif device_status == "offline":
                        status_tag = f"{RED}OFFLINE{RESET}"

                    print(
                        f"{DIM}{time_str:<12}{RESET} "
                        f"{node:<16} "
                        f"{co2_fmt:<21} "
                        f"{temp_fmt:<11} "
                        f"{rh_fmt:<12} "
                        f"{audio_fmt:<14} "
                        f"{status_tag}"
                    )

        except urllib.error.URLError:
            print(f"{YELLOW}[WAITING]{RESET} Backend API not reachable at {args.url}. Is FastAPI running?")
        except Exception as e:
            print(f"{RED}[ERROR]{RESET} {e}")

        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print(f"\n{CYAN}Monitor stopped. Goodbye!{RESET}")
            sys.exit(0)


if __name__ == "__main__":
    main()
