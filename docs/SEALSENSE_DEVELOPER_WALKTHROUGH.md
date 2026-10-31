# SealSense — Developer Architecture & Engineering Walkthrough
==============================================================
*A Personal Codebase Deep-Dive for the System Author*

This guide walks you through your own codebase. It explains how data flows from physical silicon through firmware, backend services, mathematical feature extractors, neural network forward passes, and finally onto the React canvas.

---

## Table of Contents
1. [Frontend-to-Backend Communication](#1-frontend-to-backend-communication)
2. [FastAPI Request Lifecycle & Routing](#2-fastapi-request-lifecycle--routing)
3. [Database Architecture & SQLite Migrations](#3-database-architecture--sqlite-migrations)
4. [Audio Ingestion & Signal Processing Engine](#4-audio-ingestion--signal-processing-engine)
5. [Model Inference Architecture & Nocturne Mini Adapter](#5-model-inference-architecture--nocturne-mini-adapter)
6. [Alert Rules Engine, 4-State Alarms & Automation Traces](#6-alert-rules-engine-4-state-alarms--automation-traces)
7. [Debugging a Broken Workflow](#7-debugging-a-broken-workflow)
8. [Locating UI Metrics in Code](#8-locating-ui-metrics-in-code)
9. [Safely Making Future Changes](#9-safely-making-future-changes)

---

## 1. Frontend-to-Backend Communication

### Architecture
Your frontend interacts with the backend through three clean abstraction layers:
1. **Contract Definitions** ([src/types/index.ts](file:///home/ayush/Projects/sealsense/src/types/index.ts)): Defines strict TypeScript interfaces mirroring backend Pydantic models.
2. **API Client** ([src/lib/api.ts](file:///home/ayush/Projects/sealsense/src/lib/api.ts)): A centralized HTTP client providing typed asynchronous methods wrapping standard `fetch()`.
3. **Data Fetching Hooks** ([src/hooks/useApi.ts](file:///home/ayush/Projects/sealsense/src/hooks/useApi.ts)): Provides reactive state management (`data`, `loading`, `error`, `reload`) with polling intervals.

### Real Code Example: API Client Method
From [src/lib/api.ts](file:///home/ayush/Projects/sealsense/src/lib/api.ts):
```typescript
// Centralized fetch wrapper handling JSON parsing and error extraction
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const errorBody = await res.text();
    throw new Error(`API Error ${res.status} [${path}]: ${errorBody}`);
  }
  return res.json() as Promise<T>;
}

// Typed resource caller
export const api = {
  zones: () => request<Zone[]>('/api/zones'),
  devices: () => request<Device[]>('/api/devices'),
  uploadAcousticRecording: (formData: FormData) =>
    fetch(`${BASE_URL}/api/inference/acoustic/upload`, {
      method: 'POST',
      body: formData, // No manual Content-Type header to allow browser boundary generation
    }).then(r => r.json()),
};
```

> **Developer Exercise 1**:  
> Open [src/lib/api.ts](file:///home/ayush/Projects/sealsense/src/lib/api.ts) and locate `api.referenceAnalysis`. Trace which endpoint it calls (`/api/reference/{id}/analysis`). In your browser, navigate to [http://localhost:8000/api/reference/usda_bb_so_01/analysis](http://localhost:8000/api/reference/usda_bb_so_01/analysis) to observe the raw JSON response received by this frontend method.

---

## 2. FastAPI Request Lifecycle & Routing

### Route Organization
All API endpoints are defined in [backend/app/main.py](file:///home/ayush/Projects/sealsense/backend/app/main.py). FastAPI uses Pydantic schemas ([backend/app/models.py](file:///home/ayush/Projects/sealsense/backend/app/models.py)) to validate every request payload and serialize responses.

### Request Flow Diagram
```
Browser / cURL ──▶ FastAPI Routing Engine ──▶ Dependency Injection (get_db)
                         │
                         ▼
             Pydantic Payload Validation
                         │
                         ▼
        Service Layer (audio_storage / signal_analysis / model adapter)
                         │
                         ▼
             aiosqlite Database Execution
                         │
                         ▼
               JSON Response Serializer
```

### Real Code Example: Acoustic Upload Endpoint
In [backend/app/main.py](file:///home/ayush/Projects/sealsense/backend/app/main.py):
```python
@app.post("/api/inference/acoustic/upload", response_model=RetainedAudioSample)
async def upload_acoustic_recording(
    file: UploadFile = File(...),
    zone_id: str = Form("zone-a"),
    device_id: str = Form("esp32-zone-a-01"),
    recording_domain: RecordingDomain = Form("airborne_microphone"),
    input_source: str = Form("hardware_recording"),
    is_synthetic: bool = Form(False),
    notes: Optional[str] = Form(None),
):
    # 1. Read binary bytes into memory
    content = await file.read()
    
    # 2. Validate WAV structure via wave module
    channels, sample_rate, duration_sec = validate_wav_bytes(content)
    
    # 3. Compute deterministic SHA-256 digest
    sha256_hash = compute_sha256(content)
    
    # 4. Compute physical signal analysis (RMS, centroid, Wiener entropy, clicks)
    sig_analysis = analyze_wav_bytes(content)
    
    # 5. Run Nocturne Mini model forward pass
    inference_result = nocturne_adapter.predict_wav_bytes(content)
    
    # 6. Persist recording file to disk and record metadata in SQLite
    sample_id = save_audio_file(content, filename=file.filename)
    await insert_retained_sample(...)
    return sample_response
```

> **Developer Exercise 2**:  
> In your terminal, run this cURL command to simulate uploading audio directly to your FastAPI route without using the UI:
> ```bash
> curl -X POST "http://localhost:8000/api/inference/acoustic/upload" \
>   -F "file=@backend/data/reference_datasets/bug_bytes/accelrw.wav" \
>   -F "recording_domain=accelerometer" \
>   -F "zone_id=zone-a"
> ```
> Inspect the returned JSON payload and locate the `signal_analysis` block.

---

## 3. Database Architecture & SQLite Migrations

### Database Setup
SealSense uses asynchronous SQLite via `aiosqlite` in [backend/app/database.py](file:///home/ayush/Projects/sealsense/backend/app/database.py). The canonical database resides at:
`/home/ayush/Projects/sealsense/backend/sealsense.db`

### Core Tables
1. `environmental_readings`: Stores CO₂ ($ppm$), Temperature ($^\circ C$), and Air Relative Humidity ($\%$).
2. `acoustic_events`: Stores inference results, model confidence bands, and human review statuses.
3. `alerts`: Stores ThingsBoard-style 4-state alarms with severity, acknowledgment timestamps, and execution traces.
4. `retained_audio_samples`: The central scientific library storing file paths, SHA-256 hashes, physical signal characteristics, recording domains, and biological ground truth.

### Safe Migrations Strategy
SealSense automatically executes non-destructive schema migrations during `init_db()` at startup:
```python
# Check if column exists using table_info PRAGMA before altering
cursor = await db.execute("PRAGMA table_info(retained_audio_samples)")
columns = [row[1] for row in await cursor.fetchall()]

if "recording_domain" not in columns:
    log.info("Migrating schema: Adding recording_domain column...")
    await db.execute("ALTER TABLE retained_audio_samples ADD COLUMN recording_domain TEXT NOT NULL DEFAULT 'unknown'")
```

> **Developer Exercise 3**:  
> Query your local database directly from the terminal using Python:
> ```bash
> backend/.venv/bin/python -c "
> import sqlite3
> conn = sqlite3.connect('backend/sealsense.db')
> print('Retained samples:', conn.execute('SELECT COUNT(*) FROM retained_audio_samples').fetchone()[0])
> print('Acoustic events:', conn.execute('SELECT COUNT(*) FROM acoustic_events').fetchone()[0])
> "
> ```

---

## 4. Audio Ingestion & Signal Processing Engine

### Signal Processing Engine ([backend/app/signal_analysis.py](file:///home/ayush/Projects/sealsense/backend/app/signal_analysis.py))
To avoid biological overclaiming, SealSense calculates 8 acoustic physical characteristics:

1. **RMS Energy & Peak**: Root-mean-square amplitude in both linear scale and dBFS:
   $$\text{RMS}_{\text{dBFS}} = 20 \log_{10}\left(\frac{\text{RMS}}{32768}\right)$$
2. **Spectral Centroid ($Hz$)**: The center of mass of the frequency spectrum:
   $$f_c = \frac{\sum_{k} f_k \cdot |X(f_k)|^2}{\sum_{k} |X(f_k)|^2}$$
3. **Spectral Bandwidth ($Hz$)**: The spectral spread around the centroid.
4. **Spectral Flatness (Wiener Entropy)**: Ratio of geometric mean to arithmetic mean of spectral power ($0.0 = \text{tonal/resonant}, 1.0 = \text{white noise}$).
5. **Multi-Band Energy Distribution**: Split into 4 bands: Sub-1 kHz (grain handling/mechanical), 1–4 kHz (primary insect stridulation and kernel impacts), 4–8 kHz (friction/locomotion), and >8 kHz (ultrasonic/resonance).
6. **Hilbert/MAD Transient Click Detection**:
   - 4th-order Butterworth high-pass filter ($800\text{ Hz}$).
   - Instantaneous envelope via Hilbert analytic signal: $e(t) = |s(t) + j\mathcal{H}\{s(t)\}|$.
   - Adaptive threshold: $\tau = \text{median}(e) + 5.0 \times \text{MAD}(e)$.
   - 8 ms refractory lockout to prevent multi-triggering on kernel ringing.

> **Developer Exercise 4**:  
> Run the signal analysis engine on a pure synthetic sine wave vs. random noise in Python:
> ```bash
> backend/.venv/bin/python -c "
> import numpy as np
> from app.signal_analysis import analyze_signal
> tone = (np.sin(2*np.pi*1000*np.linspace(0, 1, 16000)) * 16000).astype(np.int16)
> stats = analyze_signal(tone, 16000)
> print('1 kHz Sine Centroid:', stats['spectral_centroid_hz'], 'Flatness:', stats['spectral_flatness'])
> "
> ```

---

## 5. Model Inference Architecture & Nocturne Mini Adapter

### Model Adapter Pattern
Located in [backend/app/adapters/nocturne.py](file:///home/ayush/Projects/sealsense/backend/app/adapters/nocturne.py):
- **Base Class**: `BaseAudioModelAdapter` defines a unified interface: `predict(audio_array, sample_rate)` and `predict_wav_bytes(wav_bytes)`.
- **Lazy Loading**: The heavy PyTorch weights (`models--stratus-labs--nocturne-v1-mini`) are never loaded during import; they are loaded into RAM only on the first inference request.
- **Input Tensor Standardization**: Nocturne Mini requires an exact mono 10.0-second window ($160{,}000$ samples at $16{,}000\text{ Hz}$).
  - Audio shorter than 10s is zero-padded.
  - Audio longer than 10s is centrally cropped or sliced into non-overlapping windows.

### Why Do Outdoor Species Appear in Grain Inspections?
Nocturne Mini is an open bioacoustic foundation model trained on outdoor nocturnal wildlife (frogs, birds, bats, insects). Because its vocabulary consists of outdoor species (e.g. *Rhinophrynus dorsalis*, *Eleutherodactylus cystignathoides*), when presented with grain kernel impacts, it produces low-probability activations across its nearest spectral acoustic matches.

SealSense handles this honestly:
- Labeled **EXPERIMENTAL RESEARCH CLASSIFIER**.
- Confidence band is set to `low` or `uncertain` when scores are below calibrated thresholds.
- We never map an outdoor toad activation to a fake "99% Weevil Detection".

> **Developer Exercise 5**:  
> View the adapter implementation in [backend/app/adapters/nocturne.py](file:///home/ayush/Projects/sealsense/backend/app/adapters/nocturne.py) lines 75 to 110. Notice how `resample_to_16k_mono` uses `scipy.signal.resample_poly` for anti-aliased resampling.

---

## 6. Alert Rules Engine, 4-State Alarms & Automation Traces

### ThingsBoard 4-State Alarm Lifecycle ([backend/app/models.py](file:///home/ayush/Projects/sealsense/backend/app/models.py))
An alarm progresses through four deterministic states:
```
Condition Triggered ──▶ active_unack ──(Acknowledge)──▶ active_ack
                              │                              │
                        (Condition Normal)             (Condition Normal)
                              │                              │
                              ▼                              ▼
                        cleared_unack ──(Acknowledge)──▶ cleared_ack (Resolved)
```

### Home Assistant Automation Execution Traces ([backend/app/alert_rules.py](file:///home/ayush/Projects/sealsense/backend/app/alert_rules.py))
Every triggered alert creates an `ExecutionTrace` with step-by-step audit entries:
- `Step 1 (trigger)`: Evaluated environmental readings.
- `Step 2 (condition)`: CO₂ check: $880\text{ ppm} > 700\text{ ppm}$ $\to$ TRUE.
- `Step 3 (condition)`: Temperature check: $27.0^\circ C > 25.0^\circ C$ $\to$ TRUE.
- `Step 4 (condition)`: Air RH check: $76.0\% > 70.0\%$ $\to$ TRUE.
- `Step 5 (action)`: Dispatched `Generate Actionable Environmental Alert`.

> **Developer Exercise 6**:  
> In your browser, open [Alerts & Events](http://localhost:5173/alerts) and click **"Inspect Automation Trace"** on an active alert to view the exact trace steps rendered from this backend model.

---

## 7. Debugging a Broken Workflow

### Step-by-Step Diagnostic Protocol
If an operation fails (e.g., audio upload fails or a chart is empty):

1. **Check the Browser DevTools Network Tab**:
   - Press `F12` $\to$ click **Network** $\to$ repeat the action.
   - Look at the failed HTTP status code (e.g., 400 Bad Request, 500 Internal Error).
   - Click the request $\to$ view **Response** to read the exact error message string returned by FastAPI.
2. **Check the Backend Terminal Logs**:
   - Look at the terminal running `uvicorn`.
   - FastAPI prints Python stack traces directly with line numbers pointing to the failing function.
3. **Verify Database Integrity**:
   - Check if the database has locked: `fuser backend/sealsense.db`.
   - Ensure the column exists: `sqlite3 backend/sealsense.db "PRAGMA table_info(retained_audio_samples);"`

---

## 8. Locating UI Metrics in Code

Here is the exact mapping between what you see on screen and where it lives in the source code:

| UI Metric / Visual Component | Frontend File | Backend Source Function |
|:---|:---|:---|
| **Zone Cards (CO₂, Temp, Air RH)** | [src/pages/Overview.tsx](file:///home/ayush/Projects/sealsense/src/pages/Overview.tsx#L40) | `get_demo_data()` in [backend/app/demo_data.py](file:///home/ayush/Projects/sealsense/backend/app/demo_data.py) |
| **Air RH vs. Grain Moisture Guardrail** | [src/pages/StorageZones.tsx](file:///home/ayush/Projects/sealsense/src/pages/StorageZones.tsx#L95) | Static guardrail in `StorageZones.tsx` |
| **Acoustic Waveform Visualizer** | [src/components/AudioWaveform.tsx](file:///home/ayush/Projects/sealsense/src/components/AudioWaveform.tsx) | `waveform_preview` generated in `models.py` |
| **Spectral Centroid & Click Count** | [src/pages/AcousticMonitoring.tsx](file:///home/ayush/Projects/sealsense/src/pages/AcousticMonitoring.tsx#L250) | `analyze_wav_bytes()` in [backend/app/signal_analysis.py](file:///home/ayush/Projects/sealsense/backend/app/signal_analysis.py) |
| **`INSUFFICIENT VALIDATION DATA` Banner** | [src/pages/AcousticMonitoring.tsx](file:///home/ayush/Projects/sealsense/src/pages/AcousticMonitoring.tsx#L610) | `evaluate_dataset_samples()` in [backend/app/evaluation.py](file:///home/ayush/Projects/sealsense/backend/app/evaluation.py) |
| **Automation Execution Trace Modal** | [src/pages/AlertsEvents.tsx](file:///home/ayush/Projects/sealsense/src/pages/AlertsEvents.tsx#L220) | `evaluate_environmental()` in [backend/app/alert_rules.py](file:///home/ayush/Projects/sealsense/backend/app/alert_rules.py) |
| **SCD41 `NOT CONNECTED` Badge** | [src/pages/DevicesSensors.tsx](file:///home/ayush/Projects/sealsense/src/pages/DevicesSensors.tsx#L125) | `DEMO_DEVICES` in [backend/app/demo_data.py](file:///home/ayush/Projects/sealsense/backend/app/demo_data.py) |

---

## 9. Safely Making Future Changes

### 3 Golden Rules for SealSense Development
1. **Never Fabricate Sensor Telemetry**: If a physical sensor (such as the SCD41) is unpopulated, leave its status as `not_connected` or mark simulated series as `DEMO / SIMULATED`.
2. **Never Equate Resampling to Sensor Transduction**: Resampling a 25 kHz accelerometer recording to 16 kHz changes the digital clock, but does not alter the fact that it measures kernel acceleration ($m/s^2$) rather than air pressure ($Pa$). Retain the original `recording_domain` and exclude incompatible sensors from field microphone evaluation.
3. **Always Run the Test Suites Before Committing**:
   ```bash
   # 1. Run all 37 backend unit tests
   backend/.venv/bin/python -m unittest discover -s backend/tests -v

   # 2. Run the 8 REA verification tests
   backend/.venv/bin/python backend/tests/test_rea_features.py

   # 3. Verify frontend production TypeScript build
   npm run build
   ```
