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
// Sensirion I2C SCD4x v1.1.0 API
#include <SensirionI2cScd4x.h>

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
SensirionI2cScd4x scd4x;

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
float    lastAudioRms     = 0.0f;
int32_t  lastAudioPeak    = 0;
float    lastAudioRmsDbfs = -96.0f;
float    lastAudioPeakDbfs = -96.0f;

bool     wifiConnected = false;

// ─── Forward Declarations ─────────────────────────────────────────
void setupSCD41();
void readSCD41();
void setupI2S();
void processI2SAudio();
void sendTelemetry();
void triggerBuzzerAlert(int beeps);
void updateBuzzer();
String getISO8601();

// ─── Non-Blocking Buzzer State Machine ───────────────────────────
int      buzzerTogglesLeft = 0;
bool     buzzerPinLevel    = false;
uint32_t buzzerNextMs      = 0;
uint32_t lastBuzzerAlertMs = 0;

void triggerBuzzerAlert(int beeps) {
  uint32_t now = millis();
  if (now - lastBuzzerAlertMs < 10000) return;  // 10s debounce between alarm bursts
  lastBuzzerAlertMs = now;
  buzzerTogglesLeft = beeps * 2;
  buzzerPinLevel    = true;
  digitalWrite(BUZZER_PIN, HIGH);
  buzzerNextMs      = now + 150;
}

void updateBuzzer() {
  if (buzzerTogglesLeft <= 0) return;
  uint32_t now = millis();
  if (now >= buzzerNextMs) {
    buzzerPinLevel = !buzzerPinLevel;
    digitalWrite(BUZZER_PIN, buzzerPinLevel ? HIGH : LOW);
    buzzerTogglesLeft--;
    buzzerNextMs = now + 150;
    if (buzzerTogglesLeft == 0) {
      digitalWrite(BUZZER_PIN, LOW);
      buzzerPinLevel = false;
    }
  }
}

// ─────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println(String("[SealSense] Booting firmware ") + FIRMWARE_VER);
  Serial.println("[SealSense] Device: " + String(DEVICE_ID) + " Zone: " + String(ZONE_ID));

  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  // ── I2C init ─────────────────────────────────────────────────
  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(100000);  // SCD41 standard mode: 100 kHz

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

  // ── Service non-blocking buzzer ──────────────────────────────
  updateBuzzer();

  // ── SCD41 acquisition (non-blocking poll) ────────────────────
  if (now - lastEnvMs >= ENV_SAMPLE_MS) {
    lastEnvMs = now;
    readSCD41();
  }

  // ── I2S audio feature extraction (Slot 0, non-blocking) ──────
  processI2SAudio();

  // ── Rule-based buzzer alerts (independent of ML inference) ───
  if (scd41Ready && !isnan(lastCO2_ppm)) {
    if (lastCO2_ppm >= CO2_CRITICAL_PPM) {
      triggerBuzzerAlert(3);  // 3 short beeps = critical threshold exceeded
    } else if (lastCO2_ppm >= CO2_WARN_PPM) {
      triggerBuzzerAlert(1);  // 1 short beep = warning threshold exceeded
    }
  }

  // ── Telemetry (USB Serial every 5s; HTTP when WiFi connected) ───
  if (now - lastTelMs >= ENV_SAMPLE_MS) {
    lastTelMs = now;
    sendTelemetry();
  }
}

// ─── SCD41 Setup ─────────────────────────────────────────────────
void setupSCD41() {
  int16_t err;
  char    errMsg[64];

  scd4x.begin(Wire, SCD41_I2C_ADDR_62);

  // Wake up if the sensor was previously put in sleep mode
  scd4x.wakeUp();
  delay(20);

  // Stop any ongoing measurements before reconfiguring
  err = scd4x.stopPeriodicMeasurement();
  if (err) {
    Serial.println("[SCD41] stopPeriodicMeasurement notification (sensor was idle or booting)");
  }
  delay(500);

  // Re-initialise sensor state
  err = scd4x.reinit();
  if (err) {
    errorToString(err, errMsg, sizeof(errMsg));
    Serial.printf("[SCD41] reinit warning: %s\n", errMsg);
  }
  delay(20);

  // Verify serial number (sanity check that sensor is present on 0x62)
  uint64_t serialNumber = 0;
  err = scd4x.getSerialNumber(serialNumber);
  if (err) {
    errorToString(err, errMsg, sizeof(errMsg));
    Serial.printf("[SCD41] ERROR getSerialNumber: %s\n", errMsg);
    Serial.println("[SCD41] Check wiring: SDA=GPIO21 SCL=GPIO22 VDD=3.3V GND=GND");
    scd41Ready = false;
    return;
  }
  Serial.printf("[SCD41] Online! Serial: 0x%08X%08X\n",
                (uint32_t)(serialNumber >> 32),
                (uint32_t)(serialNumber & 0xFFFFFFFF));

  // Start periodic measurement (1 sample every ~5 s from SCD41)
  err = scd4x.startPeriodicMeasurement();
  if (err) {
    errorToString(err, errMsg, sizeof(errMsg));
    Serial.printf("[SCD41] ERROR startPeriodicMeasurement: %s\n", errMsg);
    scd41Ready = false;
    return;
  }

  scd41Ready = true;
  Serial.println("[SCD41] Periodic measurement started successfully");
}

// ─── SCD41 Read ──────────────────────────────────────────────────
void readSCD41() {
  if (!scd41Ready) return;

  int16_t err;
  char    errMsg[64];
  bool    isReady = false;

  err = scd4x.getDataReadyStatus(isReady);
  if (err) {
    errorToString(err, errMsg, sizeof(errMsg));
    Serial.printf("[SCD41] getDataReadyStatus error: %s\n", errMsg);
    return;
  }
  if (!isReady) return;  // Not ready yet (measurement takes ~5000 ms)

  uint16_t co2Raw = 0;
  float    temp = NAN, rh = NAN;

  err = scd4x.readMeasurement(co2Raw, temp, rh);
  if (err) {
    errorToString(err, errMsg, sizeof(errMsg));
    Serial.printf("[SCD41] readMeasurement error: %s\n", errMsg);
    return;
  }

  // co2Raw == 0 indicates sensor warm-up / invalid measurement per Sensirion datasheet
  if (co2Raw == 0) {
    Serial.println("[SCD41] Sensor warming up (CO2=0 ppm) — awaiting valid measurement");
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
  // Use stereo RIGHT_LEFT format to preserve both slots in ESP32 legacy I2S driver
  // Slot 0 (Left channel) carries INMP441 audio when L/R is tied to GND.
  i2s_config_t cfg = {
    .mode                 = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate          = I2S_SAMPLE_RATE,
    .bits_per_sample      = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format       = I2S_CHANNEL_FMT_RIGHT_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags     = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count        = 4,
    .dma_buf_len          = 256,
    .use_apll             = false,
    .tx_desc_auto_clear   = false,
    .fixed_mclk           = 0,
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
  Serial.println("[I2S] INMP441 initialized — BCLK=26 WS=25 DOUT=33 (Stereo Master RX)");
}

// ─── I2S Audio Feature Extraction ────────────────────────────────
/**
 * Reads I2S samples and accumulates RMS & Peak amplitude from Slot 0 (Left).
 * Does NOT run heavy ML inference on-device (server-side inference).
 */
void processI2SAudio() {
  size_t bytesRead = 0;
  // Read interleaved 32-bit stereo words: [Slot0_L, Slot1_R, Slot0_L, Slot1_R, ...]
  int32_t rawBuf[512];
  i2s_read(I2S_NUM_0, rawBuf, sizeof(rawBuf), &bytesRead, 0);

  if (bytesRead == 0) return;

  size_t stereoFrames = bytesRead / (2 * sizeof(int32_t));
  if (stereoFrames == 0) return;

  double sumSq = 0;
  int32_t peak = 0;
  for (size_t i = 0; i < stereoFrames; i++) {
    // Slot 0 (Left channel): 24-bit audio aligned at bits [31:8]
    int32_t s24 = rawBuf[2 * i] >> 8;
    int32_t abs24 = (s24 < 0) ? -s24 : s24;
    if (abs24 > peak) peak = abs24;
    float s = (float)s24 / 8388608.0f;  // Normalise 24-bit to [-1.0, 1.0]
    sumSq += (double)(s * s);
  }

  audioRmsAccum += (float)(sumSq / stereoFrames);
  audioSampleCount++;
  if (peak > lastAudioPeak) {
    lastAudioPeak = peak;
  }

  // Periodic RMS and peak window aggregation
  if (millis() - lastI2sWindowMs >= 2500) {
    lastI2sWindowMs = millis();
    float windowRms = (audioSampleCount > 0)
      ? sqrt(audioRmsAccum / audioSampleCount)
      : 0.0f;
    lastAudioRms = windowRms * 8388608.0f; // Scale to LSB
    lastAudioRmsDbfs = (windowRms > 0.000001f)
      ? (float)(20.0 * log10(windowRms))
      : -96.0f;
    lastAudioPeakDbfs = (lastAudioPeak > 0)
      ? (float)(20.0 * log10((double)lastAudioPeak / 8388608.0))
      : -96.0f;

    audioRmsAccum   = 0;
    audioSampleCount = 0;
    // Decay peak for next window
    lastAudioPeak = peak;
  }
}

// ─── Unified Telemetry Sender ─────────────────────────────────────
/**
 * Emits structured JSON telemetry over USB Serial (for serial_telemetry_bridge.py)
 * and forwards via HTTPClient if Wi-Fi is connected.
 */
void sendTelemetry() {
  JsonDocument doc;
  doc["device_id"]        = DEVICE_ID;
  doc["zone_id"]          = ZONE_ID;
  doc["firmware_version"] = FIRMWARE_VER;
  doc["timestamp"]        = getISO8601();
  doc["transport"]        = wifiConnected ? "wifi" : "usb_serial";
  doc["source"]           = "REAL";

  // SCD41 Climate metrics
  if (scd41Ready && !isnan(lastCO2_ppm) && lastCO2_ppm > 0) {
    doc["co2_ppm"]               = lastCO2_ppm;
    doc["temperature_c"]        = lastTemp_c;
    doc["relative_humidity_pct"] = lastRH_pct;
    doc["co2_valid"]             = true;
    doc["temp_valid"]            = true;
    doc["rh_valid"]              = true;
  } else {
    doc["co2_valid"]  = false;
    doc["temp_valid"] = false;
    doc["rh_valid"]   = false;
  }

  // INMP441 Acoustic metrics
  doc["audio_rms"]       = lastAudioRms;
  doc["audio_peak"]      = lastAudioPeak;
  doc["audio_rms_dbfs"]  = lastAudioRmsDbfs;
  doc["audio_peak_dbfs"] = lastAudioPeakDbfs;
  doc["audio_valid"]     = true;

  String body;
  serializeJson(doc, body);

  // 1. Always emit structured JSON over USB Serial for the telemetry bridge
  Serial.print("SEALSENSE_JSON:");
  Serial.println(body);

  // 2. Also POST over HTTP if Wi-Fi connected
  if (wifiConnected && WiFi.status() == WL_CONNECTED) {
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
}

// ─── Helpers ─────────────────────────────────────────────────────
String getISO8601() {
  uint32_t s = millis() / 1000;
  char buf[32];
  snprintf(buf, sizeof(buf), "2026-01-01T00:%02lu:%02lu.000Z", (s / 60) % 60, s % 60);
  return String(buf);
}

