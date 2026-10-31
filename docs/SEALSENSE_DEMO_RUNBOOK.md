# SealSense — 5 to 7 Minute Demonstration Runbook
===================================================
*A Professional, Repeatable Script for Technical & Agricultural Demonstrations*

---

## Demonstration Setup (T-minus 2 Minutes)

1. **Hardware Connection**:
   - Plug the ESP32 DevKit into your Linux workstation via USB (`/dev/ttyUSB0`).
   - Confirm port availability: `ls -la /dev/ttyUSB0`.
2. **Start the Platform**:
   ```bash
   cd /home/ayush/Projects/sealsense
   ./scripts/start_demo.sh
   ```
3. **Open the Browser**:
   - Navigate to [http://localhost:5173](http://localhost:5173).
   - Ensure browser zoom is comfortable for presentation (100% or 110%).

---

## Demonstration Overview & Narrative Arc

| Time | Phase | Target Page | Key Action | What You Say (Spoken Narrative) |
|:---|:---|:---|:---|:---|
| **0:00 - 1:00** | Introduction & Overview | **Overview** | Walk through silo metrics, health cards, and scenario selector. | *"SealSense is an intelligent grain-storage monitoring platform designed to detect early biological infestation and environmental spoilage in grain silos..."* |
| **1:00 - 2:15** | Storage Zones & Climate | **Storage Zones** | Select Zone A; inspect CO₂, temp, and air relative humidity charts. | *"In post-harvest grain management, insect respiration and mold activity generate elevated carbon dioxide and heat pockets..."* |
| **2:15 - 3:45** | Acoustic Pipeline & Mic | **Acoustic Monitoring** | Show USDA reference, physical microphone capture, and signal analysis. | *"Acoustic monitoring is the gold standard for non-destructive internal pest detection, but sensor physics matter..."* |
| **3:45 - 4:45** | Scientific Evaluation | **Dataset Evaluation Tab** | Point out the `INSUFFICIENT VALIDATION DATA` banner and exclusion logic. | *"Rather than claiming inflated accuracy, SealSense separates biological ground truth from model eligibility..."* |
| **4:45 - 5:45** | Alerts & Automation | **Alerts & Events** | Acknowledge active alarm; inspect Home Assistant automation trace. | *"When thresholds are breached, SealSense implements a ThingsBoard-style 4-state alarm lifecycle..."* |
| **5:45 - 6:30** | Hardware Integrity | **Devices & Sensors** | Inspect `esp32-zone-a-01`, show INMP441 active, explain SCD41 unpopulated. | *"Honesty is paramount in agricultural IoT: our microphone is active and verified, while our unpopulated CO₂ sensor is marked NOT CONNECTED..."* |
| **6:30 - 7:00** | Q&A / Conclusion | **Overview** | Return to overview; summarize next milestones. | *"To summarize: SealSense combines physical acoustic analysis with environmental guardrails..."* |

---

## Step-by-Step Presenter Script

### Phase 1: Platform Overview (0:00 – 1:00)
- **Target Page**: [Overview](http://localhost:5173)
- **Visual Focus**: The top metric cards (Active Zones, Connected Nodes, Active Alarms) and the 3 storage silo cards.
- **Action**: Switch the scenario dropdown in the top-right header to **"Rising Environmental Risk"**.
- **Spoken Narrative**:
  > *"Welcome everyone. Today I'm presenting SealSense, an integrated monitoring system for commercial grain storage silos. In grain storage, invisible threats like weevil infestations and mold pockets cause billions in post-harvest losses annually.*
  >
  > *On our overview console, you can see our facility map: Zone A is our primary wheat silo, Zone B is barley, and Zone C is currently an unmonitored silo. At a glance, operators monitor environmental health, acoustic event indicators, and node connectivity across the entire mesh."*

---

### Phase 2: Climate Telemetry & Domain Guardrails (1:00 – 2:15)
- **Target Page**: [Storage Zones](http://localhost:5173/zones)
- **Visual Focus**: The time-series graphs for CO₂, Temperature, and Air Relative Humidity in Zone A.
- **Action**: Hover over the CO₂ curve at ~880 ppm and point out the guardrail note below the charts.
- **Spoken Narrative**:
  > *"Let's drill into Zone A. In grain preservation, elevated CO₂ is the earliest chemical indicator of biological activity—both insect respiration and fungal growth produce carbon dioxide before noticeable temperature spikes occur.*
  >
  > *Notice an important domain guardrail implemented directly into SealSense: our relative humidity sensor measures **Air Relative Humidity** inside the headspace air, which is mathematically and physically distinct from **Grain Moisture Content** ($MC_{wb}$). Conflating air humidity with grain moisture is a classic mistake in grain tech that SealSense explicitly prevents through strict data typing and clear labeling."*

---

### Phase 3: Acoustic Monitoring & Physical Hardware (2:15 – 3:45)
- **Target Page**: [Acoustic Monitoring](http://localhost:5173/acoustic)
- **Visual Focus**: The Upload & Inference tab, waveform visualizer, and acoustic features panel.
- **Action**:
  1. Click on **"USDA Bug Bytes Reference Catalog"**.
  2. Select `Sitophilus oryzae Larvae Feeding (Accelerometer)` and click **"Inspect Signal Features"**.
  3. Show the physical feature breakdown: RMS energy, spectral centroid, Wiener entropy (flatness), and transient click detection via Hilbert transform and Median Absolute Deviation (MAD).
  4. Show Nocturne Mini inference output.
- **Spoken Narrative**:
  > *"Now let's examine SealSense's acoustic monitoring engine. Internal feeding larvae such as the Rice Weevil (*Sitophilus oryzae*) chew within grain kernels, generating micro-acoustic impact impulses.*
  >
  > *Here in our USDA Bug Bytes reference library, we can inspect genuine research recordings. When we run our physical signal analysis, SealSense extracts 8 fundamental wave properties: RMS amplitude, spectral centroid, spectral bandwidth, zero-crossing rate, and an adaptive transient click count. Notice how our Hilbert transform with Median Absolute Deviation captures the sharp mastication clicks.*
  >
  > *Next, notice our machine learning classification: we route the audio through our on-device Nocturne Mini adapter. We prominently label this inference as an **Experimental Research Demonstration**. Why? Because Nocturne Mini was trained on outdoor nocturnal wildlife. Presenting generic bioacoustic activations as verified grain-weevil detection would be scientifically dishonest."*

---

### Phase 4: Dataset Integrity & Scientific Evaluation (3:45 – 4:45)
- **Target Page**: Click the **"Dataset Evaluation"** tab.
- **Visual Focus**: The prominent banner: `INSUFFICIENT VALIDATION DATA` and the 4 breakdown cards (Transducer Type, Domains & Eligibility, Exclusion Reasons, Independent Biological Labels).
- **Spoken Narrative**:
  > *"This tab showcases SealSense's commitment to dataset integrity. Most commercial IoT dashboards display false 95% accuracy metrics derived from training loss or synthetic tests.*
  >
  > *SealSense decouples **Biological Ground Truth** from **Model Evaluation Eligibility**. Our USDA reference recordings have verified biological provenance—they are real weevils in wheat. However, they were recorded using contact accelerometers and piezo discs, not airborne microphones. Resampling an accelerometer recording to 16 kHz does not turn structural vibration into acoustic air pressure. Therefore, SealSense marks them sensor-incompatible and displays **INSUFFICIENT VALIDATION DATA** until genuine field microphone datasets are collected."*

---

### Phase 5: Alarm Lifecycle & Automation Traces (4:45 – 5:45)
- **Target Page**: [Alerts & Events](http://localhost:5173/alerts)
- **Visual Focus**: The active alarm in Zone A and the execution trace modal.
- **Action**:
  1. Click **"Inspect Automation Trace"** to show the 5-step trigger $\to$ condition $\to$ action pipeline.
  2. Click **"Acknowledge"** $\to$ alarm changes state to `active_ack`.
  3. Click **"Clear / Resolve"** $\to$ alarm transitions to `cleared_ack`.
- **Spoken Narrative**:
  > *"When risk thresholds are exceeded, SealSense implements a ThingsBoard-style 4-state alarm lifecycle: `active_unack`, `active_ack`, `cleared_unack`, and `cleared_ack`.*
  >
  > *Opening our Automation Execution Trace, operators see the exact Home Assistant-style deterministic rule execution: the environmental trigger evaluated CO₂ above 700 ppm, verified temperature above 25°C, confirmed Air RH above 70%, and executed the alert generation. Operators acknowledge the incident and clear it when verified, creating an immutable audit trail."*

---

### Phase 6: Hardware Status & Transparency (5:45 – 6:30)
- **Target Page**: [Devices & Sensors](http://localhost:5173/devices)
- **Visual Focus**: The `esp32-zone-a-01` device card.
- **Action**: Point out the green dot for `INMP441 Microphone` and the red dashed badge for `SCD41 CO₂ Sensor (NOT CONNECTED)`.
- **Spoken Narrative**:
  > *"Finally, let's look at our physical hardware mesh. Node `esp32-zone-a-01` is connected via USB serial. Our INMP441 I²S microphone is physically wired and fully operational.*
  >
  > *Notice that our SCD41 CO₂ sensor is explicitly flagged as **NOT CONNECTED (Hardware Unpopulated)**. We do not invent fake live sensor readings. When hardware is absent, SealSense reports it transparently while maintaining full software readiness."*

---

### Phase 7: Conclusion & Summary (6:30 – 7:00)
- **Target Page**: Return to [Overview](http://localhost:5173)
- **Spoken Narrative**:
  > *"To summarize: SealSense unites hardware acoustic capture, rigorous physical signal processing, transparent evaluation guardrails, and deterministic environmental alerting into a complete, honest grain-preservation platform.*
  >
  > *Thank you, and I'd be glad to take any questions or demonstrate live acoustic capture from our connected ESP32 microphone."*

---

## Disclosures & Data Truth Table (For Q&A)

| Data Element | Real / Simulated / Experimental | Honest Scientific Explanation |
|:---|:---|:---|
| **INMP441 Microphone Audio** | **REAL** | Captured live via I²S from physical microphone on ESP32 (`/dev/ttyUSB0`). |
| **USDA Bug Bytes Audio** | **REAL REFERENCE** | Authenticated USDA ARS research recordings; recorded on contact transducers in laboratory cultures. |
| **Physical Signal Metrics** | **REAL** | Computed directly via standard mathematical signal processing (RMS, FFT centroid, Wiener entropy, Hilbert/MAD). |
| **Nocturne Mini Inference** | **EXPERIMENTAL** | Real PyTorch neural network forward pass, but trained on outdoor nocturnal wildlife, not stored-grain insects. |
| **Environmental Readings (CO₂ / Temp / RH)** | **SIMULATED** | Generated by deterministic scenario generator for demonstration while physical SCD41 sensor is unpopulated. |
| **SCD41 Hardware Status** | **REAL** | Transparently reported as `NOT CONNECTED`. |
| **Field Accuracy / F1 Metrics** | **SUPPRESSED** | Blocked with `INSUFFICIENT VALIDATION DATA` banner to prevent false claims. |
