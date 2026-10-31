#!/usr/bin/env bash
# ==============================================================================
# SealSense — Complete Integrated Startup Script
# ==============================================================================
# Safely starts or reuses:
#   1. FastAPI Backend (port 8000) — checks health before starting duplicate
#   2. React Frontend   (port 5173) — checks if Vite dev server is running
#   3. Serial Bridge    (/dev/ttyUSB0) — checks device, permissions & connects
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Ensure color support
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
CYAN="\033[0;36m"
RED="\033[0;31m"
BOLD="\033[1m"
NC="\033[0m"

echo -e "${CYAN}${BOLD}================================================================================"
echo -e "       SealSense — Real-Time Grain Storage Observability Platform       "
echo -e "================================================================================${NC}"

# ─── 1. Verify Project Directory & Virtualenv ─────────────────────────────────
if [ ! -f "$PROJECT_ROOT/package.json" ] || [ ! -d "$PROJECT_ROOT/backend" ]; then
    echo -e "${RED}[ERROR] Invalid project root: $PROJECT_ROOT${NC}"
    exit 1
fi

if [ ! -f "$PROJECT_ROOT/backend/.venv/bin/python" ]; then
    echo -e "${RED}[ERROR] Python virtualenv not found at backend/.venv!${NC}"
    echo -e "        Run: python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt"
    exit 1
fi

PYTHON_EXEC="$PROJECT_ROOT/backend/.venv/bin/python"

# ─── 2. Backend Inspection (Port 8000 Conflict Resolution) ────────────────────
BACKEND_PID=""
BACKEND_REUSED=false

echo -e "\n${BOLD}[1/3] Inspecting FastAPI Backend (Port 8000)...${NC}"

if curl -s -m 2 http://127.0.0.1:8000/health | grep -q '"status":"ok"'; then
    BACKEND_REUSED=true
    RUNNING_PID=$(ss -ltnp 'sport = :8000' 2>/dev/null | grep -o 'pid=[0-9]*' | head -n1 | cut -d= -f2 || true)
    echo -e "  ${GREEN}✓ Healthy SealSense backend already running on http://127.0.0.1:8000 (PID: ${RUNNING_PID:-unknown})${NC}"
    echo -e "    Reusing existing backend instance (no duplicate started)."
else
    # Check if port 8000 is occupied by an unresponsive process
    OCCUPIED_PID=$(ss -ltnp 'sport = :8000' 2>/dev/null | grep -o 'pid=[0-9]*' | head -n1 | cut -d= -f2 || true)
    if [ -n "$OCCUPIED_PID" ]; then
        echo -e "  ${RED}⚠ Port 8000 is occupied by PID $OCCUPIED_PID, but /health is not responding!${NC}"
        echo -e "    Inspect process: ps -fp $OCCUPIED_PID"
        echo -e "    If it is a stale process, terminate it with: kill $OCCUPIED_PID"
        exit 1
    fi

    echo -e "  Starting FastAPI backend on http://0.0.0.0:8000..."
    (
        cd "$PROJECT_ROOT/backend"
        exec "$PYTHON_EXEC" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ) > "$PROJECT_ROOT/backend/uvicorn.log" 2>&1 &
    BACKEND_PID=$!
    echo -e "  Backend launched with PID $BACKEND_PID (logs: backend/uvicorn.log)"

    # Await readiness
    echo -n "  Waiting for API /health..."
    READY=false
    for i in {1..30}; do
        if curl -s -m 1 http://127.0.0.1:8000/health | grep -q '"status":"ok"'; then
            READY=true
            break
        fi
        echo -n "."
        sleep 0.5
    done

    if [ "$READY" = true ]; then
        echo -e " ${GREEN}ONLINE!${NC}"
    else
        echo -e " ${RED}FAILED!${NC}"
        echo -e "Check backend/uvicorn.log for errors."
        exit 1
    fi
fi

# ─── 3. Frontend Inspection (Port 5173) ───────────────────────────────────────
FRONTEND_PID=""
FRONTEND_REUSED=false

echo -e "\n${BOLD}[2/3] Inspecting React Frontend (Port 5173)...${NC}"

if curl -s -m 2 http://localhost:5173 >/dev/null 2>&1; then
    FRONTEND_REUSED=true
    echo -e "  ${GREEN}✓ Vite dev server already running on http://localhost:5173${NC}"
    echo -e "    Reusing existing frontend instance."
else
    echo -e "  Starting Vite development server..."
    npm run dev > "$PROJECT_ROOT/vite.log" 2>&1 &
    FRONTEND_PID=$!
    echo -e "  Frontend launched with PID $FRONTEND_PID (logs: vite.log)"

    echo -n "  Waiting for frontend readiness..."
    for i in {1..20}; do
        if curl -s -m 1 http://localhost:5173 >/dev/null 2>&1; then
            break
        fi
        echo -n "."
        sleep 0.5
    done
    echo -e " ${GREEN}ONLINE!${NC}"
fi

# ─── 4. Hardware Serial Inspection (/dev/ttyUSB0) ─────────────────────────────
echo -e "\n${BOLD}[3/3] Inspecting ESP32 Serial Hardware (/dev/ttyUSB0)...${NC}"

BRIDGE_MODE="hardware"
SERIAL_PORT="/dev/ttyUSB0"

if [ ! -e "$SERIAL_PORT" ]; then
    echo -e "  ${YELLOW}⚠ Device node $SERIAL_PORT does not exist.${NC}"
    echo -e "    The ESP32 does not appear to be plugged into USB."
    echo -e "    Starting telemetry bridge in ${CYAN}--mock simulation mode${NC} so dashboard receives live telemetry."
    BRIDGE_MODE="mock"
else
    USE_SG_DIALOUT=false
    if ! id -nG | grep -qw "dialout"; then
        if getent group dialout | grep -qw "$USER"; then
            echo -e "  ${YELLOW}ℹ Notice:${NC} '$USER' is in 'dialout' in /etc/group, but this shell session predates group membership."
            echo -e "    Using ${CYAN}sg dialout${NC} for this run. (Log out and log back in to apply system-wide)."
            USE_SG_DIALOUT=true
        else
            echo -e "  ${YELLOW}⚠ PERMISSION WARNING:${NC} User '$USER' is not in the 'dialout' group."
            echo -e "  Device: $(ls -l $SERIAL_PORT)"
            echo -e "  ${BOLD}Run this once to grant permanent serial access:${NC}"
            echo -e "      ${CYAN}sudo usermod -aG dialout \"$USER\"${NC}"
            echo -e "      ${CYAN}newgrp dialout${NC}"
        fi
    else
        echo -e "  ${GREEN}✓ User '$USER' is a verified member of the 'dialout' group.${NC}"
    fi

    # Check if another process currently locks the port
    LOCKING_PID=$(lsof "$SERIAL_PORT" 2>/dev/null | awk 'NR>1 {print $2}' | head -n1 || true)
    if [ -n "$LOCKING_PID" ]; then
        echo -e "  ${YELLOW}⚠ Port $SERIAL_PORT is currently open by PID $LOCKING_PID!${NC}"
        echo -e "    Ensure Arduino Serial Monitor or minicom is closed before starting bridge."
    fi
fi

# ─── 5. Launch or Reuse Telemetry Bridge ─────────────────────────────────────
BRIDGE_PID=""
BRIDGE_REUSED=false

if [ -f "/tmp/sealsense_serial_bridge.lock" ]; then
    RUNNING_BRIDGE_PID=$(cat "/tmp/sealsense_serial_bridge.lock" 2>/dev/null || true)
    if [ -n "$RUNNING_BRIDGE_PID" ] && kill -0 "$RUNNING_BRIDGE_PID" 2>/dev/null; then
        BRIDGE_REUSED=true
        echo -e "  ${GREEN}✓ Healthy SealSense Serial Bridge already running (PID: $RUNNING_BRIDGE_PID)${NC}"
        echo -e "    Reusing existing bridge (no duplicate started)."
    fi
fi

if [ "$BRIDGE_REUSED" = false ]; then
    if [ "$BRIDGE_MODE" = "hardware" ]; then
        echo -e "  Launching hardware serial bridge on $SERIAL_PORT @ 115200 baud..."
        if [ "$USE_SG_DIALOUT" = true ]; then
            sg dialout -c "\"$PYTHON_EXEC\" \"$PROJECT_ROOT/tools/serial_telemetry_bridge.py\" --port \"$SERIAL_PORT\" --baud 115200" &
            BRIDGE_PID=$!
        else
            "$PYTHON_EXEC" "$PROJECT_ROOT/tools/serial_telemetry_bridge.py" --port "$SERIAL_PORT" --baud 115200 &
            BRIDGE_PID=$!
        fi
    else
        echo -e "  Launching mock telemetry bridge (simulation mode)..."
        "$PYTHON_EXEC" "$PROJECT_ROOT/tools/serial_telemetry_bridge.py" --mock &
        BRIDGE_PID=$!
    fi
fi

echo -e "\n${CYAN}${BOLD}================================================================================"
echo -e "  SealSense Observability Stack is Active!  "
echo -e "================================================================================${NC}"
echo -e "  🖥️  ${BOLD}Live Observability Dashboard:${NC}  ${GREEN}http://localhost:5173${NC}"
echo -e "  📡  ${BOLD}FastAPI REST Endpoints:${NC}        ${GREEN}http://localhost:8000/docs${NC}"
echo -e "  📊  ${BOLD}Latest Telemetry API:${NC}          ${GREEN}http://localhost:8000/api/telemetry/latest${NC}"
echo -e "  📜  ${BOLD}Telemetry History API:${NC}         ${GREEN}http://localhost:8000/api/telemetry/history?time_range=15m${NC}"
echo -e "${CYAN}================================================================================${NC}"
echo -e "Press ${BOLD}Ctrl+C${NC} to stop the telemetry bridge and local demo processes safely.\n"

# ─── Cleanup Handler ─────────────────────────────────────────────────────────
cleanup() {
    echo -e "\n${YELLOW}[SHUTDOWN] Stopping background services...${NC}"
    if [ -n "$BRIDGE_PID" ] && [ "$BRIDGE_REUSED" = false ]; then
        kill "$BRIDGE_PID" 2>/dev/null || true
    fi
    if [ -n "$BACKEND_PID" ] && [ "$BACKEND_REUSED" = false ]; then
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
    if [ -n "$FRONTEND_PID" ] && [ "$FRONTEND_REUSED" = false ]; then
        kill "$FRONTEND_PID" 2>/dev/null || true
    fi
    echo -e "${GREEN}[SHUTDOWN] Clean exit. Goodbye!${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

if [ "$BRIDGE_REUSED" = true ]; then
    while true; do sleep 1; done
else
    wait "$BRIDGE_PID"
fi
