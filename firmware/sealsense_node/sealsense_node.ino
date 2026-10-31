/**
 * SealSense Node Firmware
 * Target: ESP32-WROOM-32 / ESP32 DevKit
 * 
 * Sensors:
 *   SCD41  — CO2, Temperature, Air Relative Humidity (NOT grain moisture)
 *     SDA: GPIO21, SCL: GPIO22, VCC: 3.3V, GND: common
 *
 *   INMP441 — I2S microphone
 *     BCLK/SCK: GPIO26, WS/LRCLK: GPIO25, SD/DOUT: GPIO33
 *     L/R: GND (mono), VDD: 3.3V, GND: common
 *
 *   Buzzer — rule-based alerts only, NOT triggered by acoustic model
 *     Pin: GPIO27 (active-high)
 *
 * Libraries (install via Arduino Library Manager or PlatformIO):
 *   - Sensirion I2C SCD4x  (Sensirion AG)  — check version compatibility below
 *   - Arduino ESP32 core   >= 2.0.0
 *   - ArduinoJson          >= 7.0.0
 *
 * NOTE: Check your installed library versions before changing API calls.
 * The SCD4x library API has changed between versions. This targets:
 *   Sensirion I2C SCD4x v0.4.x / v1.x (use SensirionI2CScd4x class).
 */

#include <Arduino.h>
#include <Wire.h>
#include <driver/i2s.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
// Check your installed version: Sensirion I2C SCD4x
#include <SensirionI2CScd4x.h>

// ─── Configuration ───────────────────────────────────────────────
const char* WIFI_SSID     = "YOUR_SSID";
const char* WIFI_PASSWORD = "YOUR_PASSWORD";
const char* BACKEND_URL   = "http://192.168.1.100:8000/api/telemetry";  // Update IP

const char* DEVICE_ID     = "esp32-zone-a-01";
const char* ZONE_ID       = "zone-a";
const char* FIRMWARE_VER  = "1.2.0";

// ─── Pin Definitions ─────────────────────────────────────────────
#define I2C_SDA         21
#define I2C_SCL         22
#define I2S_BCLK        26
#define I2S_WS          25
#define I2S_DOUT        33
#define BUZZER_PIN      27

// ─── Timing ──────────────────────────────────────────────────────
const uint32_t ENV_SAMPLE_MS   = 5000;    // 5 s — SCD41 measurement interval
const uint32_t TELEMETRY_MS    = 30000;   // 30 s — HTTP post interval
const uint32_t I2S_SAMPLE_RATE = 16000;   // Hz — required by nocturne-v1-mini
const uint32_t I2S_WINDOW_MS   = 10000;   // 10 s audio window

// ─── CO2 Alert Thresholds (buzzer only — rule-based) ─────────────
const float CO2_WARN_PPM      = 700.0f;
const float CO2_CRITICAL_PPM  = 1200.0f;
const float RH_WARN_PCT       = 70.0f;   // Air RH — NOT grain moisture

// ─── Globals ─────────────────────────────────────────────────────
SensirionI2CScd4x scd4x;

// SCD41 last readings
float     lastCO2_ppm  = NAN;
float     lastTemp_c   = NAN;
float     lastRH_pct   = NAN;    // Air relative humidity
bool      scd41Ready   = false;
uint32_t  lastEnvMs    = 0;
uint32_t  lastTelMs    = 0;

// I2S buffer (10 s at 16kHz, mono, 16-bit = 320000 bytes — must fit in PSRAM or be streamed)
// For boards without PSRAM, reduce window or stream to SPIFFS/SD
// Here we use a smaller internal RAM buffer and accumulate features, not raw PCM
#define  I2S_BUF_LEN   1024
int16_t  i2sBuf[I2S_BUF_LEN];

// Simple RMS accumulator for audio activity
float    audioRmsAccum = 0;
uint32_t audioSampleCount = 0;
uint32_t lastI2sWindowMs  = 0;

bool     wifiConnected = false;

// ─── Forward Declarations ─────────────────────────────────────────
void setupSCD41();
void readSCD41();
void setupI2S();
void processI2SAudio();
void postTelemetry();
void buzzerAlert(int code);
String getISO8601();

// ─────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("[SealSense] Booting firmware " FIRMWARE_VER);
  Serial.println("[SealSense] Device: " + String(DEVICE_ID) + " Zone: " + String(ZONE_ID));

  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  // ── I2C init ─────────────────────────────────────────────────
  Wire.begin(I2C_SDA, I2C_SCL);

  // ── SCD41 init ───────────────────────────────────────────────
  setupSCD41();

  // ── I2S init ─────────────────────────────────────────────────
  setupI2S();

  // ── WiFi (non-blocking; telemetry posts when connected) ──────
  Serial.print("[WiFi] Connecting to " + String(WIFI_SSID) + " ...");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  uint32_t wt = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - wt < 10000) {
    delay(500); Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    wifiConnected = true;
    Serial.println("\n[WiFi] Connected: " + WiFi.localIP().toString());
  } else {
    Serial.println("\n[WiFi] Not connected — sensor acquisition continues locally");
  }
}

// ─────────────────────────────────────────────────────────────────
void loop() {
  uint32_t now = millis();

  // ── SCD41 acquisition (non-blocking poll) ────────────────────
  if (now - lastEnvMs >= ENV_SAMPLE_MS) {
    lastEnvMs = now;
    readSCD41();
  }

  // ── I2S audio feature extraction (separate from inference) ───
  processI2SAudio();

  // ── Rule-based buzzer alerts (independent of ML inference) ───
  if (scd41Ready) {
    if (!isnan(lastCO2_ppm) && lastCO2_ppm >= CO2_CRITICAL_PPM) {
      buzzerAlert(3);  // 3 short beeps = critical
    } else if (!isnan(lastCO2_ppm) && lastCO2_ppm >= CO2_WARN_PPM) {
      buzzerAlert(1);  // 1 beep = warning
    }
  }

  // ── HTTP telemetry post ───────────────────────────────────────
  if (wifiConnected && (now - lastTelMs >= TELEMETRY_MS)) {
    lastTelMs = now;
    if (WiFi.status() == WL_CONNECTED) {
      postTelemetry();
    } else {
      Serial.println("[WiFi] Connection lost; skipping telemetry post");
      wifiConnected = false;
      WiFi.reconnect();
    }
  }
}

// ─── SCD41 Setup ─────────────────────────────────────────────────
void setupSCD41() {
  uint16_t err;
  char     errMsg[64];

  scd4x.begin(Wire);

  // Stop any ongoing measurements before reconfiguring
  err = scd4x.stopPeriodicMeasurement();
  if (err) {
    Serial.println("[SCD41] stopPeriodicMeasurement error — may be first boot");
  }
  delay(500);

  // Verify serial number (sanity check that sensor is present)
  uint16_t sn0, sn1, sn2;
  err = scd4x.getSerialNumber(sn0, sn1, sn2);
  if (err) {
    errorToString(err, errMsg, sizeof(errMsg));
    Serial.printf("[SCD41] ERROR getSerialNumber: %s\n", errMsg);
    Serial.println("[SCD41] Check wiring: SDA=GPIO21 SCL=GPIO22 VCC=3.3V");
    return;
  }
  Serial.printf("[SCD41] Serial: 0x%04X%04X%04X\n", sn0, sn1, sn2);

  // Start periodic measurement (1 reading every ~5 s from SCD41)
  err = scd4x.startPeriodicMeasurement();
  if (err) {
    errorToString(err, errMsg, sizeof(errMsg));
    Serial.printf("[SCD41] ERROR startPeriodicMeasurement: %s\n", errMsg);
    return;
  }

  scd41Ready = true;
  Serial.println("[SCD41] Periodic measurement started");
}

// ─── SCD41 Read ──────────────────────────────────────────────────
void readSCD41() {
  if (!scd41Ready) return;

  uint16_t err;
  char     errMsg[64];
  bool     isReady = false;

  err = scd4x.getDataReadyFlag(isReady);
  if (err) {
    errorToString(err, errMsg, sizeof(errMsg));
    Serial.printf("[SCD41] getDataReadyFlag error: %s\n", errMsg);
    return;
  }
  if (!isReady) return;  // not ready yet — check again next cycle

  uint16_t co2Raw;
  float    temp, rh;

  err = scd4x.readMeasurement(co2Raw, temp, rh);
  if (err) {
    errorToString(err, errMsg, sizeof(errMsg));
    Serial.printf("[SCD41] readMeasurement error: %s\n", errMsg);
    return;
  }

  // co2Raw == 0 means invalid measurement per SCD41 datasheet
  if (co2Raw == 0) {
    Serial.println("[SCD41] Invalid measurement (CO2=0) — skipping");
    return;
  }

  lastCO2_ppm = (float)co2Raw;
  lastTemp_c  = temp;
  lastRH_pct  = rh;  // Air relative humidity — NOT grain moisture content

  Serial.printf("[SCD41] CO2=%u ppm  Temp=%.1f°C  Air_RH=%.1f%%\n",
                co2Raw, temp, rh);
}

// ─── I2S Setup ───────────────────────────────────────────────────
void setupI2S() {
  i2s_config_t cfg = {
    .mode            = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate     = I2S_SAMPLE_RATE,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,  // INMP441 outputs 24-bit in 32-bit frame
    .channel_format  = I2S_CHANNEL_FMT_ONLY_LEFT,  // L/R pin tied to GND = left channel
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count   = 4,
    .dma_buf_len     = I2S_BUF_LEN,
    .use_apll        = false,
    .tx_desc_auto_clear = false,
    .fixed_mclk      = 0,
  };

  i2s_pin_config_t pins = {
    .bck_io_num   = I2S_BCLK,
    .ws_io_num    = I2S_WS,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num  = I2S_DOUT,
  };

  esp_err_t r = i2s_driver_install(I2S_NUM_0, &cfg, 0, NULL);
  if (r != ESP_OK) {
    Serial.printf("[I2S] Driver install failed: %d\n", r);
    return;
  }
  r = i2s_set_pin(I2S_NUM_0, &pins);
  if (r != ESP_OK) {
    Serial.printf("[I2S] Set pin failed: %d\n", r);
    return;
  }
  Serial.println("[I2S] INMP441 initialized — BCLK=26 WS=25 DOUT=33");
}

// ─── I2S Audio Feature Extraction ────────────────────────────────
/**
 * Reads I2S samples and accumulates RMS amplitude.
 * Does NOT run ML inference on-device (ESP32 can't run nocturne-v1-mini).
 * Audio features or raw buffers can be sent to backend for server-side inference.
 */
void processI2SAudio() {
  size_t bytesRead = 0;
  // INMP441 gives 32-bit frames; we discard upper 8 bits (24-bit data)
  int32_t rawBuf[I2S_BUF_LEN / 2];
  i2s_read(I2S_NUM_0, rawBuf, sizeof(rawBuf), &bytesRead, 0);

  if (bytesRead == 0) return;

  size_t samples = bytesRead / sizeof(int32_t);
  double sumSq = 0;
  for (size_t i = 0; i < samples; i++) {
    // Shift right 8 to get 24-bit value, normalise to float
    float s = (float)(rawBuf[i] >> 8) / 8388608.0f;  // 2^23
    sumSq += s * s;
  }

  audioRmsAccum += (float)(sumSq / samples);
  audioSampleCount++;

  // Every 10 s window: report RMS
  if (millis() - lastI2sWindowMs >= I2S_WINDOW_MS) {
    lastI2sWindowMs = millis();
    float windowRms = (audioSampleCount > 0)
      ? sqrt(audioRmsAccum / audioSampleCount)
      : 0.0f;
    Serial.printf("[I2S] Audio RMS (10s window) = %.5f\n", windowRms);
    // TODO Milestone 4: POST acoustic features to backend for server-side inference
    audioRmsAccum   = 0;
    audioSampleCount = 0;
  }
}

// ─── HTTP Telemetry Post ──────────────────────────────────────────
void postTelemetry() {
  if (isnan(lastCO2_ppm) && isnan(lastTemp_c) && isnan(lastRH_pct)) {
    Serial.println("[HTTP] No valid readings — skipping telemetry post");
    return;
  }

  JsonDocument doc;
  doc["device_id"] = DEVICE_ID;
  doc["zone_id"]   = ZONE_ID;
  doc["timestamp"] = getISO8601();

  if (!isnan(lastCO2_ppm)) {
    doc["co2_ppm"]   = lastCO2_ppm;
    doc["co2_valid"] = true;
  } else {
    doc["co2_valid"] = false;
  }

  if (!isnan(lastTemp_c)) {
    doc["temperature_c"] = lastTemp_c;
    doc["temp_valid"]    = true;
  } else {
    doc["temp_valid"] = false;
  }

  if (!isnan(lastRH_pct)) {
    // Field is air relative humidity — backend enforces this label
    doc["relative_humidity_pct"] = lastRH_pct;
    doc["rh_valid"]              = true;
  } else {
    doc["rh_valid"] = false;
  }

  String body;
  serializeJson(doc, body);

  HTTPClient http;
  http.begin(BACKEND_URL);
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(body);

  if (code == 200 || code == 201) {
    Serial.printf("[HTTP] Telemetry posted OK (%d)\n", code);
  } else {
    Serial.printf("[HTTP] POST failed: %d\n", code);
  }
  http.end();
}

// ─── Buzzer (rule-based only) ─────────────────────────────────────
void buzzerAlert(int beeps) {
  static uint32_t lastBuzzMs = 0;
  if (millis() - lastBuzzMs < 10000) return;  // Debounce 10 s
  lastBuzzMs = millis();
  for (int i = 0; i < beeps; i++) {
    digitalWrite(BUZZER_PIN, HIGH); delay(200);
    digitalWrite(BUZZER_PIN, LOW);  delay(150);
  }
}

// ─── Helpers ─────────────────────────────────────────────────────
String getISO8601() {
  // With NTP this would use proper time — for now uses uptime
  // TODO Milestone 3: sync NTP before posting
  uint32_t s = millis() / 1000;
  char buf[32];
  snprintf(buf, sizeof(buf), "2026-01-01T00:%02lu:%02lu.000Z", (s / 60) % 60, s % 60);
  return String(buf);
}
