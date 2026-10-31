#!/usr/bin/env bash
# ==============================================================================
# SealSense — Local Demonstration Startup Script
# ==============================================================================
# Launches the FastAPI backend (port 8000) and the Vite frontend (port 5173).
# Provides a graceful shutdown on Ctrl+C.
# ==============================================================================

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "================================================================================"
echo "  Starting SealSense Grain Storage Monitoring Platform  "
echo "================================================================================"

# 1. Environment & Venv Validation
if [ ! -d "backend/.venv" ]; then
    echo "[SETUP] Python virtualenv not found at backend/.venv. Creating..."
    python3 -m venv backend/.venv
    backend/.venv/bin/pip install --upgrade pip
    backend/.venv/bin/pip install -r backend/requirements.txt
fi

export SEALSENSE_DB="$PROJECT_ROOT/backend/sealsense.db"
export SEALSENSE_AUDIO_DIR="$PROJECT_ROOT/backend/data/audio_samples"
export SEALSENSE_REFERENCE_AUDIO_DIR="$PROJECT_ROOT/backend/data/reference_datasets/bug_bytes"

mkdir -p "$PROJECT_ROOT/backend/data/audio_samples"
mkdir -p "$PROJECT_ROOT/backend/data/hardware_recordings"

echo "[CONFIG] Canonical Database: $SEALSENSE_DB"
echo "[CONFIG] Audio Storage:     $SEALSENSE_AUDIO_DIR"
echo "[CONFIG] Reference Catalog: $SEALSENSE_REFERENCE_AUDIO_DIR"

# 2. Check if backend is already responding on port 8000
BACKEND_PID=""
if curl -s http://localhost:8000/health >/dev/null 2>&1; then
    echo "[BACKEND] Backend is already running on http://localhost:8000"
else
    echo "[BACKEND] Launching FastAPI backend on http://0.0.0.0:8000..."
    (
        cd backend
        exec .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ) &
    BACKEND_PID=$!
    echo "[BACKEND] Process PID: $BACKEND_PID"

    # Wait for backend readiness
    echo -n "[BACKEND] Waiting for API healthcheck..."
    for i in {1..30}; do
        if curl -s http://localhost:8000/health >/dev/null 2>&1; then
            echo " READY!"
            break
        fi
        echo -n "."
        sleep 0.5
    done
fi

# 3. Check if frontend is already responding on port 5173
FRONTEND_PID=""
if curl -s http://localhost:5173 >/dev/null 2>&1; then
    echo "[FRONTEND] Frontend is already running on http://localhost:5173"
else
    echo "[FRONTEND] Launching Vite development server..."
    npm run dev &
    FRONTEND_PID=$!
    echo "[FRONTEND] Process PID: $FRONTEND_PID"
fi

echo ""
echo "================================================================================"
echo "  SealSense Demonstration is LIVE  "
echo "================================================================================"
echo "  🖥️  Frontend Console:     http://localhost:5173"
echo "  📡  FastAPI Swagger Docs: http://localhost:8000/docs"
echo "  🔍  Acoustic Evaluation:  http://localhost:5173 (Select Acoustic Monitoring)"
echo "  🎙️  Hardware Capture:     python tools/capture_inmp441.py --port /dev/ttyUSB0"
echo "================================================================================"
echo "Press Ctrl+C to shut down all demo processes safely."
echo ""

# Graceful cleanup trap
cleanup() {
    echo ""
    echo "[SHUTDOWN] Stopping demo processes..."
    if [ -n "$FRONTEND_PID" ]; then
        kill "$FRONTEND_PID" 2>/dev/null || true
    fi
    if [ -n "$BACKEND_PID" ]; then
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
    echo "[SHUTDOWN] Done. Have a great day!"
    exit 0
}

trap cleanup SIGINT SIGTERM

# Keep parent script waiting
wait
