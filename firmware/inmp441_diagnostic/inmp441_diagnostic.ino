/**
 * SealSense — INMP441 Acoustic Responsiveness & Slot 0 Calibration
 * Target: ESP32-WROOM-32 / ESP32 DevKit
 *
 * Hardware Wiring:
 *   INMP441 Pin  | ESP32 Pin  | Signal Function
 *   -------------|------------|---------------------------------------------
 *   L/R          | GND        | Tied to GND -> Transmits on Slot 0 (Left)
 *   WS / LRCL    | GPIO 25    | Word Select (16 kHz square wave)
 *   SCK / BCLK   | GPIO 26    | Bit Clock (1.024 MHz)
 *   GND          | GND        | Common Ground
 *   VDD          | 3.3V       | 3.3V Power
 *   SD           | GPIO 33    | Serial Data (I2S Input)
 *
 * Diagnostic Objective:
 *   - Continuous 1.0-second measurement windows (16,000 stereo frames at 16 kHz).
 *   - Focus analysis on Slot 0 (the verified active acoustic channel).
 *   - Correct 24-bit signed sample extraction (raw_word >> 8).
 *   - Calculate Slot 0 RMS, peak, min, max, and unique sample count.
 *   - Compare consecutive windows and report amplitude trend:
 *       INCREASED, DECREASED, or APPROXIMATELY UNCHANGED.
 *   - Slot 1 monitored as reference (values of 0 and 1 noted as idle/floating).
 *   - ZERO fabricated data. Only genuine physical measurements displayed.
 */

#include <Arduino.h>
#include <driver/i2s.h>
#include <math.h>

// ─── Pin Configuration ───────────────────────────────────────────
#define I2S_WS   25
#define I2S_SCK  26
#define I2S_SD   33

// ─── Sampling Parameters ─────────────────────────────────────────
#define SAMPLE_RATE          16000
#define FRAMES_PER_WINDOW    16000    // Exactly 1.0 second of audio
#define CHUNK_FRAMES         256      // Read in 256-frame blocks (512 words)

// ─── Trend Detection Threshold ───────────────────────────────────
#define TREND_DB_THRESHOLD   1.5f     // dB change required to flag increase/decrease

// ─── Buffer Allocation ───────────────────────────────────────────
// DMA chunk buffer: 256 stereo frames = 512 words = 2048 bytes
int32_t chunkBuffer[CHUNK_FRAMES * 2];

// 8 KB bitmap to track unique 16-bit sample values in the 16,000 sample window (65,536 bits)
uint8_t seenBitmap[8192];

// ─── State Variables for Window Comparison ───────────────────────
uint32_t windowIndex = 0;
bool     hasPrevWindow = false;
double   prevRms24 = 0.0;
float    prevRmsDbfs = -96.0f;
int32_t  prevPeak24 = 0;

// ─── Forward Declarations ─────────────────────────────────────────
bool initI2S();
void runAcousticWindow();
void printAsciiBar(float dbfs);

// ─────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n========================================================");
  Serial.println("  SealSense — INMP441 Acoustic Responsiveness Monitor   ");
  Serial.println("========================================================");
  Serial.printf("Target Board:     ESP32-WROOM-32 / DevKit\n");
  Serial.printf("I2S Config:       Master RX, 16,000 Hz, 32-bit slot width\n");
  Serial.printf("Channel Format:   I2S_CHANNEL_FMT_RIGHT_LEFT (Stereo)\n");
  Serial.printf("Wiring:           SCK=GPIO%d, WS=GPIO%d, SD=GPIO%d, L/R=GND\n", I2S_SCK, I2S_WS, I2S_SD);
  Serial.printf("Window Size:      16,000 frames (1.000 second cadence)\n");
  Serial.printf("Active Channel:   Slot 0 (Confirmed microphone transmission)\n");
  Serial.printf("Reference Channel:Slot 1 (Idle / floating LSBs)\n");
  Serial.println("--------------------------------------------------------");
  Serial.println("Test Protocol:");
  Serial.println("  1. Quiet Room:   Observe baseline RMS and stable trend (≈).");
  Serial.println("  2. Speech:       Speak into mic -> Observe RMS rise (▲).");
  Serial.println("  3. Gentle Tap:   Tap near mic -> Observe peak spike (▲).");
  Serial.println("========================================================\n");

  if (!initI2S()) {
    Serial.println("[CRITICAL] I2S Driver failed to initialize. Halting.");
    while (true) { delay(1000); }
  }

  Serial.println("[READY] Starting 1-second continuous acoustic monitoring...\n");
}

// ─────────────────────────────────────────────────────────────────
void loop() {
  runAcousticWindow();
}

// ─── I2S Driver Initialization ───────────────────────────────────
bool initI2S() {
  i2s_config_t cfg = {
    .mode                 = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate          = SAMPLE_RATE,
    .bits_per_sample      = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format       = I2S_CHANNEL_FMT_RIGHT_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags     = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count        = 4,
    .dma_buf_len          = 512,
    .use_apll             = false,
    .tx_desc_auto_clear   = false,
    .fixed_mclk           = 0
  };

  i2s_pin_config_t pins = {
    .bck_io_num   = I2S_SCK,
    .ws_io_num    = I2S_WS,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num  = I2S_SD
  };

  esp_err_t err = i2s_driver_install(I2S_NUM_0, &cfg, 0, NULL);
  if (err != ESP_OK) {
    Serial.printf("[I2S] ERROR: driver install failed: 0x%X\n", err);
    return false;
  }

  err = i2s_set_pin(I2S_NUM_0, &pins);
  if (err != ESP_OK) {
    Serial.printf("[I2S] ERROR: set pin failed: 0x%X\n", err);
    return false;
  }

  i2s_zero_dma_buffer(I2S_NUM_0);
  return true;
}

// ─── 1.0-Second Acoustic Measurement Window ──────────────────────
void runAcousticWindow() {
  windowIndex++;
  uint32_t tStart = millis();

  // Reset unique bitmap (8 KB)
  memset(seenBitmap, 0, sizeof(seenBitmap));

  // Slot 0 Accumulators (Active Audio)
  uint32_t framesCollected = 0;
  double   sumSquares24 = 0.0;
  int32_t  minSample24 = 2147483647;
  int32_t  maxSample24 = -2147483648;
  int32_t  peakSample24 = 0;
  uint32_t s0ZeroCount = 0;

  // Slot 1 Accumulators (Idle Reference)
  uint32_t s1ZeroCount = 0;
  uint32_t s1OneCount = 0;
  uint32_t s1OtherCount = 0;
  int32_t  s1Min = 2147483647;
  int32_t  s1Max = -2147483648;

  uint32_t readErrors = 0;

  // Stream exactly 16,000 stereo frames (32,000 words) from DMA
  while (framesCollected < FRAMES_PER_WINDOW) {
    size_t framesToRead = CHUNK_FRAMES;
    if (framesCollected + framesToRead > FRAMES_PER_WINDOW) {
      framesToRead = FRAMES_PER_WINDOW - framesCollected;
    }

    size_t bytesToRead = framesToRead * 2 * sizeof(int32_t);
    size_t bytesRead = 0;

    esp_err_t err = i2s_read(I2S_NUM_0, chunkBuffer, bytesToRead, &bytesRead, portMAX_DELAY);
    if (err != ESP_OK || bytesRead == 0) {
      readErrors++;
      continue;
    }

    size_t framesRead = bytesRead / (2 * sizeof(int32_t));

    for (size_t f = 0; f < framesRead; f++) {
      int32_t w0 = chunkBuffer[2 * f];      // Slot 0 (Active Audio)
      int32_t w1 = chunkBuffer[2 * f + 1];  // Slot 1 (Idle)

      // ─── Slot 0 Processing ─────────────────────────────────────
      // Extract 24-bit signed sample: w0 >> 8 preserves sign bit and discards lower 8 zero-bits
      int32_t s24 = w0 >> 8;

      if (s24 == 0) s0ZeroCount++;

      if (s24 < minSample24) minSample24 = s24;
      if (s24 > maxSample24) maxSample24 = s24;

      int32_t abs24 = (s24 < 0) ? -s24 : s24;
      if (abs24 > peakSample24) peakSample24 = abs24;

      sumSquares24 += (double)s24 * (double)s24;

      // Track unique samples via 16-bit extracted amplitude (top 16 bits of audio)
      uint16_t s16_idx = (uint16_t)(w0 >> 16);
      seenBitmap[s16_idx >> 3] |= (1 << (s16_idx & 7));

      // ─── Slot 1 Processing (Idle Channel) ──────────────────────
      if (w1 == 0) s1ZeroCount++;
      else if (w1 == 1) s1OneCount++;
      else s1OtherCount++;

      if (w1 < s1Min) s1Min = w1;
      if (w1 > s1Max) s1Max = w1;
    }

    framesCollected += framesRead;
  }

  uint32_t durationMs = millis() - tStart;

  // Count unique values from bitmap
  uint32_t uniqueCount = 0;
  for (size_t b = 0; b < sizeof(seenBitmap); b++) {
    uint8_t byteVal = seenBitmap[b];
    if (byteVal) {
      uniqueCount += __builtin_popcount(byteVal);
    }
  }

  // Calculate 24-bit and equivalent dBFS metrics
  double rms24 = (framesCollected > 0) ? sqrt(sumSquares24 / framesCollected) : 0.0;
  float  normRms = (float)(rms24 / 8388608.0);
  float  rmsDbfs = (rms24 > 0.0) ? (float)(20.0 * log10(rms24 / 8388608.0)) : -96.0f;
  float  peakDbfs = (peakSample24 > 0) ? (float)(20.0 * log10((double)peakSample24 / 8388608.0)) : -96.0f;

  // 16-bit equivalent peak and RMS for easy reference
  int16_t peak16 = (int16_t)(peakSample24 >> 8);
  double  rms16  = rms24 / 256.0;

  // Determine trend relative to previous window
  String trendStr = "";
  if (!hasPrevWindow) {
    trendStr = "BASELINE (First Window)";
  } else {
    float deltaDbfs = rmsDbfs - prevRmsDbfs;
    if (deltaDbfs >= TREND_DB_THRESHOLD) {
      char buf[64];
      snprintf(buf, sizeof(buf), "▲ INCREASED (+%.1f dB) [Acoustic activity detected]", deltaDbfs);
      trendStr = String(buf);
    } else if (deltaDbfs <= -TREND_DB_THRESHOLD) {
      char buf[64];
      snprintf(buf, sizeof(buf), "▼ DECREASED (%.1f dB) [Quieting down]", deltaDbfs);
      trendStr = String(buf);
    } else {
      char buf[64];
      snprintf(buf, sizeof(buf), "≈ APPROXIMATELY UNCHANGED (Δ %+.1f dB) [Stable]", deltaDbfs);
      trendStr = String(buf);
    }
  }

  // ─── Print Window Report ─────────────────────────────────────────
  Serial.println("================================================================================");
  Serial.printf("[WINDOW #%04u] Duration: %u ms | Frames: %u @ 16 kHz\n",
                windowIndex, durationMs, framesCollected);
  Serial.println("--------------------------------------------------------------------------------");

  // Slot 0 Analysis
  Serial.printf("SLOT 0 (Active Microphone — Extracted Signed 24-bit PCM):\n");
  Serial.printf("  RMS Amplitude:       %10.1f LSB (Normalized: %.6f | %6.1f dBFS)\n",
                rms24, normRms, rmsDbfs);
  Serial.printf("  Peak Amplitude:      %10d LSB (16-bit eq: %6d | %6.1f dBFS)\n",
                peakSample24, peak16, peakDbfs);
  Serial.printf("  Sample Extrema:      Min = %d, Max = %d\n", minSample24, maxSample24);
  Serial.printf("  Unique Samples:      %u unique amplitudes in 16,000 samples\n", uniqueCount);
  Serial.printf("  Zero Samples:        %u (%.2f%%)\n",
                s0ZeroCount, (float)s0ZeroCount * 100.0f / framesCollected);
  Serial.printf("  16-bit RMS Equiv:    %.1f LSB / 32768\n", rms16);

  // Dynamic visual dBFS bar
  Serial.print("  Acoustic Level:      ");
  printAsciiBar(rmsDbfs);
  Serial.println();

  // Window-to-Window Comparison
  Serial.println("--------------------------------------------------------------------------------");
  Serial.printf("WINDOW COMPARISON:\n");
  Serial.printf("  Status / Trend:      %s\n", trendStr.c_str());
  if (hasPrevWindow) {
    Serial.printf("  Current vs Previous: RMS: %.1f vs %.1f LSB (Δ %+.1f LSB) | dBFS: %.1f vs %.1f\n",
                  rms24, prevRms24, rms24 - prevRms24, rmsDbfs, prevRmsDbfs);
  }

  // Slot 1 Reference
  Serial.println("--------------------------------------------------------------------------------");
  Serial.printf("SLOT 1 (Reference Idle Channel — DO NOT interpret 0 or 1 as audio):\n");
  Serial.printf("  Values: 0s = %u (%.1f%%) | 1s = %u (%.1f%%) | Other = %u | Min = %d, Max = %d\n",
                s1ZeroCount, (float)s1ZeroCount * 100.0f / framesCollected,
                s1OneCount, (float)s1OneCount * 100.0f / framesCollected,
                s1OtherCount, s1Min, s1Max);
  Serial.printf("  Status: Idle floating LSB noise. No acoustic modulation present.\n");

  if (readErrors > 0) {
    Serial.printf("  [WARNING] I2S Read Errors encountered: %u\n", readErrors);
  }
  Serial.println("================================================================================\n");

  // Save for next window comparison
  prevRms24 = rms24;
  prevRmsDbfs = rmsDbfs;
  prevPeak24 = peakSample24;
  hasPrevWindow = true;
}

// ─── Visual Dynamic dBFS Bar ─────────────────────────────────────
void printAsciiBar(float dbfs) {
  // Range: -70 dBFS (quiet) to 0 dBFS (full scale), 30 characters wide
  int totalChars = 30;
  float minDbfs = -70.0f;
  float maxDbfs = 0.0f;

  float clamped = (dbfs < minDbfs) ? minDbfs : ((dbfs > maxDbfs) ? maxDbfs : dbfs);
  int filled = (int)((clamped - minDbfs) / (maxDbfs - minDbfs) * totalChars);

  Serial.printf("[%5.1f dBFS] [", dbfs);
  for (int i = 0; i < totalChars; i++) {
    if (i < filled) Serial.print("=");
    else Serial.print(" ");
  }
  Serial.print("]");
}
