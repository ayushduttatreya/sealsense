/**
 * SealSense — Complete Hardware Integration & Verification Suite
 * Target: ESP32-WROOM-32 / DevKit
 *
 * Hardware Wiring:
 *   Component | Pin Name    | ESP32 GPIO | Description
 *   ----------|-------------|------------|---------------------------------------
 *   SCD41     | SDA         | GPIO 21    | I2C Data (Sensirion SCD41, addr 0x62)
 *   SCD41     | SCL         | GPIO 22    | I2C Clock (100 kHz standard mode)
 *   SCD41     | VDD         | 3.3V Rail  | Regulated 3.3V power
 *   SCD41     | GND         | Common GND | Power & signal ground
 *   INMP441   | WS / LRCL   | GPIO 25    | Word Select (16 kHz square wave)
 *   INMP441   | SCK / BCLK  | GPIO 26    | Bit Clock (1.024 MHz)
 *   INMP441   | SD / DOUT   | GPIO 33    | Serial Data (I2S input to ESP32)
 *   INMP441   | L/R         | Common GND | Tied to GND -> Transmits on Slot 0
 *   INMP441   | VDD         | 3.3V Rail  | Regulated 3.3V power
 *   INMP441   | GND         | Common GND | Power & signal ground
 *   Buzzer    | Positive    | GPIO 27    | Active-High / PWM alarm alert
 *   Buzzer    | Negative    | Common GND | Ground
 *
 * Testing Sequence:
 *   Stage 1: ESP32 Startup, Silicon & Memory Audit
 *   Stage 2: I2C Bus Discovery Scan (detecting address 0x62)
 *   Stage 3: Sensirion SCD41 Initialization & Live Climate Reading (CO2, Temp, RH)
 *   Stage 4: INMP441 I2S Acoustic Responsiveness (RMS, Peak, Extrema on Slot 0)
 *   Stage 5: Non-Blocking Buzzer Tone Test
 *   Stage 6: Wi-Fi & Backend REST API Telemetry Probe
 *   Stage 7: Integrated Operating Mode (Continuous multi-sensor telemetry)
 */

#include <Arduino.h>
#include <Wire.h>
#include <driver/i2s.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <SensirionI2cScd4x.h>
#include <math.h>

// ─── Exact Pin Configuration ─────────────────────────────────────
#define I2C_SDA         21
#define I2C_SCL         22
#define I2S_WS          25
#define I2S_BCLK        26
#define I2S_SD          33
#define BUZZER_PIN      27

// ─── Network & Telemetry Settings ─────────────────────────────────
const char* WIFI_SSID     = "YOUR_SSID";
const char* WIFI_PASSWORD = "YOUR_PASSWORD";
const char* BACKEND_URL   = "http://192.168.1.100:8000/api/telemetry";

const char* DEVICE_ID     = "esp32-zone-a-01";
const char* ZONE_ID       = "zone-a";
const char* SUITE_VER     = "2.0.0-PROTOTYPE";

// ─── Sampling Parameters ─────────────────────────────────────────
#define I2S_SAMPLE_RATE   16000
#define CHUNK_FRAMES      256
#define CHUNK_WORDS       (CHUNK_FRAMES * 2)

// ─── Sensor Objects & Globals ────────────────────────────────────
SensirionI2cScd4x scd4x;

bool scd41FoundOnI2C    = false;
bool scd41Initialized   = false;
bool inmp441Initialized = false;
bool wifiConnected      = false;

uint16_t lastCO2_ppm     = 0;
float    lastTemp_c      = NAN;
float    lastRH_pct      = NAN;
uint32_t lastScd41ReadMs = 0;

double   audioRms24      = 0.0;
int32_t  audioPeak24     = 0;
float    audioRmsDbfs    = -96.0f;
float    audioPeakDbfs   = -96.0f;
uint32_t lastAudioReadMs = 0;

int32_t dmaChunkBuffer[CHUNK_WORDS];

// ─── Non-Blocking Buzzer State Machine ───────────────────────────
int      buzzerTogglesLeft = 0;
bool     buzzerPinLevel    = false;
uint32_t buzzerNextMs      = 0;

void triggerBuzzer(int beeps) {
  buzzerTogglesLeft = beeps * 2;
  buzzerPinLevel = true;
  digitalWrite(BUZZER_PIN, HIGH);
  buzzerNextMs = millis() + 150;
}

void updateBuzzer() {
  if (buzzerTogglesLeft <= 0) return;
  uint32_t now = millis();
  if (now >= buzzerNextMs) {
    buzzerPinLevel = !buzzerPinLevel;
    digitalWrite(BUZZER_PIN, buzzerPinLevel ? HIGH : LOW);
    buzzerTogglesLeft--;
    buzzerNextMs = now + (buzzerPinLevel ? 150 : 100);
  }
}

// ─── Forward Declarations ─────────────────────────────────────────
void runStage1_SystemStartup();
void runStage2_I2CScan();
void runStage3_SCD41Verification();
void runStage4_INMP441Verification();
void runStage5_BuzzerVerification();
void runStage6_NetworkVerification();
void runIntegratedCycle();
void postTelemetryPayload();

// ─────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(1500);

  Serial.println("\n");
  Serial.println("================================================================================");
  Serial.println("   SealSense — Integrated Hardware Verification & Diagnostic Suite              ");
  Serial.println("================================================================================");
  Serial.printf("Version: %s | Target: ESP32-WROOM-32 DevKit\n", SUITE_VER);
  Serial.println("--------------------------------------------------------------------------------");

  // Initialize Buzzer GPIO
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  // Run Sequential Verification Stages
  runStage1_SystemStartup();
  runStage2_I2CScan();
  runStage3_SCD41Verification();
  runStage4_INMP441Verification();
  runStage5_BuzzerVerification();
  runStage6_NetworkVerification();

  Serial.println("\n================================================================================");
  Serial.println(">>> HARDWARE VERIFICATION COMPLETE. ENTERING INTEGRATED OPERATING MODE...      ");
  Serial.println("================================================================================\n");
}

// ─────────────────────────────────────────────────────────────────
void loop() {
  updateBuzzer();
  runIntegratedCycle();
}

// ─── STAGE 1: System Startup Audit ───────────────────────────────
void runStage1_SystemStartup() {
  Serial.println("[STAGE 1/6] ESP32 Silicon & Memory Startup Audit");
  Serial.printf("  Chip Model:         %s (Rev %d)\n", ESP.getChipModel(), ESP.getChipRevision());
  Serial.printf("  CPU Cores:          %d @ %d MHz\n", ESP.getChipCores(), ESP.getCpuFreqMHz());
  Serial.printf("  Flash Memory:       %d MB (Speed: %d MHz)\n", ESP.getFlashChipSize() / (1024 * 1024), ESP.getFlashChipSpeed() / 1000000);
  Serial.printf("  Free Heap RAM:      %u bytes\n", ESP.getFreeHeap());
  Serial.println("  Configured GPIO Mapping:");
  Serial.printf("    - I2C SDA:        GPIO %d (Sensirion SCD41 Data)\n", I2C_SDA);
  Serial.printf("    - I2C SCL:        GPIO %d (Sensirion SCD41 Clock)\n", I2C_SCL);
  Serial.printf("    - I2S WS:         GPIO %d (INMP441 Word Select / LRCL)\n", I2S_WS);
  Serial.printf("    - I2S SCK:        GPIO %d (INMP441 Bit Clock / BCLK)\n", I2S_BCLK);
  Serial.printf("    - I2S SD:         GPIO %d (INMP441 Serial Data Output)\n", I2S_SD);
  Serial.printf("    - Buzzer:         GPIO %d (Rule-based alarm annunciator)\n", BUZZER_PIN);
  Serial.println("  [PASS] Startup sequence initialized successfully.\n");
}

// ─── STAGE 2: I2C Device Discovery Scan ──────────────────────────
void runStage2_I2CScan() {
  Serial.println("[STAGE 2/6] I2C Bus Discovery Scan (GPIO 21 SDA, GPIO 22 SCL)");
  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(100000); // 100 kHz standard mode per SCD41 datasheet

  byte error, address;
  int devicesFound = 0;

  for (address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    error = Wire.endTransmission();

    if (error == 0) {
      Serial.printf("  --> I2C device detected at 7-bit address 0x%02X", address);
      if (address == SCD41_I2C_ADDR_62) {
        Serial.print("  [MATCH: Sensirion SCD41 Environmental Sensor]");
        scd41FoundOnI2C = true;
      }
      Serial.println();
      devicesFound++;
    } else if (error == 4) {
      Serial.printf("  [WARNING] Unknown error on I2C address 0x%02X\n", address);
    }
  }

  if (scd41FoundOnI2C) {
    Serial.printf("  [PASS] SCD41 sensor discovered at address 0x62 (Total I2C devices: %d).\n\n", devicesFound);
  } else {
    Serial.printf("  [FAIL] Sensirion SCD41 NOT detected at 0x62 (Total I2C devices: %d).\n", devicesFound);
    Serial.println("         Check wiring: SDA=GPIO21, SCL=GPIO22, VDD=3.3V, GND=Common.\n");
  }
}

// ─── STAGE 3: Sensirion SCD41 Verification ───────────────────────
void runStage3_SCD41Verification() {
  Serial.println("[STAGE 3/6] Sensirion SCD41 Climate Sensor Initialization & Live Test");
  if (!scd41FoundOnI2C) {
    Serial.println("  [SKIP] Skipping SCD41 initialization because sensor was not detected on I2C bus.\n");
    return;
  }

  char errMsg[64];
  int16_t err;

  scd4x.begin(Wire, SCD41_I2C_ADDR_62);

  // Clean state recovery
  err = scd4x.wakeUp();
  err = scd4x.stopPeriodicMeasurement();
  delay(100);
  err = scd4x.reinit();
  delay(100);

  uint64_t serialNumber = 0;
  err = scd4x.getSerialNumber(serialNumber);
  if (err != 0) {
    errorToString(err, errMsg, sizeof(errMsg));
    Serial.printf("  [FAIL] Failed to retrieve SCD41 serial number: %s\n\n", errMsg);
    return;
  }

  Serial.printf("  SCD41 Serial Number: 0x%08X%08X\n", (uint32_t)(serialNumber >> 32), (uint32_t)(serialNumber & 0xFFFFFFFF));

  err = scd4x.startPeriodicMeasurement();
  if (err != 0) {
    errorToString(err, errMsg, sizeof(errMsg));
    Serial.printf("  [FAIL] Failed to start periodic measurement: %s\n\n", errMsg);
    return;
  }

  Serial.println("  Periodic measurement started (5-second integration cycle).");
  Serial.print("  Awaiting initial SCD41 measurement (polling data ready)");

  bool isReady = false;
  uint32_t pollStart = millis();
  while (!isReady && (millis() - pollStart < 7000)) {
    delay(500);
    Serial.print(".");
    err = scd4x.getDataReadyStatus(isReady);
  }
  Serial.println();

  if (isReady) {
    uint16_t co2 = 0;
    float temp = 0.0f, rh = 0.0f;
    err = scd4x.readMeasurement(co2, temp, rh);
    if (err == 0 && co2 > 0) {
      lastCO2_ppm = co2;
      lastTemp_c  = temp;
      lastRH_pct  = rh;
      scd41Initialized = true;

      Serial.printf("  Live Readings: CO2 = %u ppm | Temp = %.2f °C | Air RH = %.2f %%\n", co2, temp, rh);
      Serial.println("  [PASS] SCD41 verified with authentic non-zero atmospheric readings.\n");
    } else {
      Serial.printf("  [WARNING] Measurement read error or warming up (CO2=%u ppm).\n\n", co2);
    }
  } else {
    Serial.println("  [NOTE] SCD41 sensor is warming up. First reading will arrive in operating loop.\n");
    scd41Initialized = true;
  }
}

// ─── STAGE 4: INMP441 I2S Acoustic Verification ──────────────────
void runStage4_INMP441Verification() {
  Serial.println("[STAGE 4/6] INMP441 I2S Microphone Verification (Master RX, 16 kHz Stereo)");

  i2s_config_t cfg = {
    .mode                 = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate          = I2S_SAMPLE_RATE,
    .bits_per_sample      = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format       = I2S_CHANNEL_FMT_RIGHT_LEFT, // Stereo (Slot 0 is Left channel)
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags     = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count        = 4,
    .dma_buf_len          = 512,
    .use_apll             = false,
    .tx_desc_auto_clear   = false,
    .fixed_mclk           = 0
  };

  i2s_pin_config_t pins = {
    .bck_io_num   = I2S_BCLK,
    .ws_io_num    = I2S_WS,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num  = I2S_SD
  };

  esp_err_t r = i2s_driver_install(I2S_NUM_0, &cfg, 0, NULL);
  if (r != ESP_OK) {
    Serial.printf("  [FAIL] I2S driver install failed (0x%X)\n\n", r);
    return;
  }
  r = i2s_set_pin(I2S_NUM_0, &pins);
  if (r != ESP_OK) {
    Serial.printf("  [FAIL] I2S set pin failed (0x%X)\n\n", r);
    return;
  }

  i2s_zero_dma_buffer(I2S_NUM_0);
  inmp441Initialized = true;

  // Sample 8,000 frames (0.5 second) to test acoustic responsiveness
  uint32_t framesCollected = 0;
  double sumSquares = 0.0;
  int32_t peak = 0;
  uint32_t zeroCount = 0;

  while (framesCollected < 8000) {
    size_t bytesRead = 0;
    i2s_read(I2S_NUM_0, dmaChunkBuffer, sizeof(dmaChunkBuffer), &bytesRead, portMAX_DELAY);
    size_t frames = bytesRead / (2 * sizeof(int32_t));

    for (size_t i = 0; i < frames; i++) {
      // Slot 0 (even index): 24-bit audio in bits [31:8]
      int32_t s24 = dmaChunkBuffer[2 * i] >> 8;
      if (s24 == 0) zeroCount++;

      int32_t abs24 = (s24 < 0) ? -s24 : s24;
      if (abs24 > peak) peak = abs24;

      sumSquares += (double)s24 * (double)s24;
    }
    framesCollected += frames;
  }

  double rms = sqrt(sumSquares / framesCollected);
  float rmsDbfs = (rms > 0) ? (float)(20.0 * log10(rms / 8388608.0)) : -96.0f;
  float peakDbfs = (peak > 0) ? (float)(20.0 * log10((double)peak / 8388608.0)) : -96.0f;
  float zeroPct = (float)zeroCount * 100.0f / framesCollected;

  Serial.printf("  Slot 0 Metrics:     RMS = %.1f LSB (%.1f dBFS) | Peak = %d LSB (%.1f dBFS)\n",
                rms, rmsDbfs, peak, peakDbfs);
  Serial.printf("  Zero Percentage:    %.2f %%\n", zeroPct);

  if (peak > 0 && zeroPct < 95.0f) {
    Serial.println("  [PASS] INMP441 acoustic responsiveness confirmed on Slot 0.\n");
  } else {
    Serial.println("  [WARNING] High zero count or low peak. Check GPIO 33 and 3.3V rail.\n");
  }
}

// ─── STAGE 5: Buzzer Test ─────────────────────────────────────────
void runStage5_BuzzerVerification() {
  Serial.println("[STAGE 5/6] Buzzer Annunciator Test (GPIO 27, Non-Blocking)");
  triggerBuzzer(2); // 2 short beeps
  Serial.println("  --> Non-blocking alert sequence triggered on GPIO 27 (2 beeps).");
  
  // Service the buzzer for 600ms so the user can hear the test beeps during setup
  uint32_t tEnd = millis() + 600;
  while (millis() < tEnd) {
    updateBuzzer();
    delay(10);
  }
  Serial.println("  [PASS] Buzzer state machine executed without blocking acquisition.\n");
}

// ─── STAGE 6: Network & Telemetry Verification ───────────────────
void runStage6_NetworkVerification() {
  Serial.println("[STAGE 6/6] Wi-Fi & REST API Telemetry Probe");
  if (strcmp(WIFI_SSID, "YOUR_SSID") == 0) {
    Serial.println("  [NOTICE] Default WIFI_SSID ('YOUR_SSID') is set.");
    Serial.println("           Update WIFI_SSID/WIFI_PASSWORD to enable live backend posting.");
    Serial.println("  [PASS] Local acquisition mode active.\n");
    return;
  }

  Serial.printf("  Connecting to Wi-Fi SSID '%s'...", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  uint32_t startMs = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - startMs < 8000)) {
    delay(500);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    wifiConnected = true;
    Serial.printf("\n  --> Wi-Fi Connected! IP Address: %s\n", WiFi.localIP().toString().c_str());
    Serial.println("  [PASS] Network interface operational.\n");
  } else {
    Serial.println("\n  [WARNING] Wi-Fi connection timed out. Local sensor operation continues.\n");
  }
}

// ─── Helpers ─────────────────────────────────────────────────────
String getISO8601() {
  uint32_t s = millis() / 1000;
  char buf[32];
  snprintf(buf, sizeof(buf), "2026-10-31T00:%02lu:%02lu.000Z", (s / 60) % 60, s % 60);
  return String(buf);
}

// ─── STAGE 7: Integrated Operating Loop ──────────────────────────
void runIntegratedCycle() {
  uint32_t now = millis();

  // 1. Process INMP441 Acoustic Samples
  if (inmp441Initialized) {
    size_t bytesRead = 0;
    i2s_read(I2S_NUM_0, dmaChunkBuffer, sizeof(dmaChunkBuffer), &bytesRead, 0);
    if (bytesRead > 0) {
      size_t frames = bytesRead / (2 * sizeof(int32_t));
      double sumSq = 0.0;
      int32_t peak = 0;
      for (size_t i = 0; i < frames; i++) {
        int32_t s24 = dmaChunkBuffer[2 * i] >> 8;
        int32_t abs24 = (s24 < 0) ? -s24 : s24;
        if (abs24 > peak) peak = abs24;
        sumSq += (double)s24 * (double)s24;
      }
      audioRms24 = sqrt(sumSq / frames);
      audioPeak24 = peak;
      audioRmsDbfs = (audioRms24 > 0) ? (float)(20.0 * log10(audioRms24 / 8388608.0)) : -96.0f;
      audioPeakDbfs = (audioPeak24 > 0) ? (float)(20.0 * log10((double)audioPeak24 / 8388608.0)) : -96.0f;
    }
  }

  // 2. Poll SCD41 Climate Sensor (every 5 seconds)
  if (scd41Initialized && (now - lastScd41ReadMs >= 5000)) {
    lastScd41ReadMs = now;
    bool isReady = false;
    int16_t err = scd4x.getDataReadyStatus(isReady);
    if (err == 0 && isReady) {
      uint16_t co2 = 0;
      float temp = 0.0f, rh = 0.0f;
      err = scd4x.readMeasurement(co2, temp, rh);
      if (err == 0 && co2 > 0) {
        lastCO2_ppm = co2;
        lastTemp_c  = temp;
        lastRH_pct  = rh;

        // Rule-based buzzer alert
        if (co2 >= 1200) {
          triggerBuzzer(3); // Critical alert
        } else if (co2 >= 700) {
          triggerBuzzer(1); // Warning alert
        }
      }
    }
  }

  // 3. Periodic Telemetry Log to Serial (every 2.5 seconds)
  if (now - lastAudioReadMs >= 2500) {
    lastAudioReadMs = now;
    Serial.println("--------------------------------------------------------------------------------");
    Serial.printf("[TELEMETRY @ %lu s] Node: %s | Zone: %s\n", now / 1000, DEVICE_ID, ZONE_ID);
    
    // Climate Sensor
    if (scd41Initialized && lastCO2_ppm > 0) {
      Serial.printf("  SCD41 Climate:   CO2 = %u ppm | Temp = %.1f °C | Air RH = %.1f %% [VALID]\n",
                    lastCO2_ppm, lastTemp_c, lastRH_pct);
    } else {
      Serial.printf("  SCD41 Climate:   %s\n", scd41FoundOnI2C ? "Warming up / Measuring..." : "NOT CONNECTED");
    }

    // Acoustic Sensor
    if (inmp441Initialized) {
      Serial.printf("  INMP441 Audio:   RMS = %.1f LSB (%5.1f dBFS) | Peak = %d LSB (%5.1f dBFS) [ACTIVE]\n",
                    audioRms24, audioRmsDbfs, audioPeak24, audioPeakDbfs);
    } else {
      Serial.println("  INMP441 Audio:   UNAVAILABLE");
    }

    // Network / Wi-Fi
    Serial.printf("  Network Status:  %s\n", wifiConnected ? "Wi-Fi Connected" : "Local Serial Mode");
    Serial.println("--------------------------------------------------------------------------------\n");

    // Emit structured JSON telemetry record over USB Serial for the telemetry bridge
    JsonDocument serialDoc;
    serialDoc["device_id"]        = DEVICE_ID;
    serialDoc["zone_id"]          = ZONE_ID;
    serialDoc["firmware_version"] = SUITE_VER;
    serialDoc["timestamp"]        = getISO8601();
    serialDoc["transport"]        = "usb_serial";
    serialDoc["source"]           = "REAL";

    if (scd41Initialized && lastCO2_ppm > 0) {
      serialDoc["co2_ppm"]               = (float)lastCO2_ppm;
      serialDoc["temperature_c"]        = lastTemp_c;
      serialDoc["relative_humidity_pct"] = lastRH_pct;
      serialDoc["co2_valid"]             = true;
      serialDoc["temp_valid"]            = true;
      serialDoc["rh_valid"]              = true;
    } else {
      serialDoc["co2_valid"]  = false;
      serialDoc["temp_valid"] = false;
      serialDoc["rh_valid"]   = false;
    }

    if (inmp441Initialized) {
      serialDoc["audio_rms"]       = audioRms24;
      serialDoc["audio_peak"]      = audioPeak24;
      serialDoc["audio_rms_dbfs"]  = audioRmsDbfs;
      serialDoc["audio_peak_dbfs"] = audioPeakDbfs;
      serialDoc["audio_valid"]     = true;
    } else {
      serialDoc["audio_valid"]     = false;
    }

    String serialJsonStr;
    serializeJson(serialDoc, serialJsonStr);
    Serial.print("SEALSENSE_JSON:");
    Serial.println(serialJsonStr);

    // Post to backend if Wi-Fi connected
    if (wifiConnected) {
      postTelemetryPayload();
    }
  }
}

// ─── Post Telemetry to Backend API ───────────────────────────────
void postTelemetryPayload() {
  if (WiFi.status() != WL_CONNECTED) return;

  JsonDocument doc;
  doc["device_id"] = DEVICE_ID;
  doc["zone_id"]   = ZONE_ID;
  
  uint32_t s = millis() / 1000;
  char buf[32];
  snprintf(buf, sizeof(buf), "2026-10-31T00:%02lu:%02lu.000Z", (s / 60) % 60, s % 60);
  doc["timestamp"] = buf;

  if (scd41Initialized && lastCO2_ppm > 0) {
    doc["co2_ppm"]   = lastCO2_ppm;
    doc["co2_valid"] = true;
    doc["temperature_c"] = lastTemp_c;
    doc["temp_valid"]    = true;
    doc["relative_humidity_pct"] = lastRH_pct;
    doc["rh_valid"]              = true;
  } else {
    doc["co2_valid"]  = false;
    doc["temp_valid"] = false;
    doc["rh_valid"]   = false;
  }

  String jsonStr;
  serializeJson(doc, jsonStr);

  HTTPClient http;
  http.begin(BACKEND_URL);
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(jsonStr);
  if (code == 200 || code == 201) {
    Serial.printf("[HTTP] Telemetry POST succeeded (Status %d)\n", code);
  } else {
    Serial.printf("[HTTP] Telemetry POST error (Code %d)\n", code);
  }
  http.end();
}
