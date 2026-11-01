import type {
  EnvironmentalReading, AcousticEvent, Alert, Device, Zone,
  DemoScenario, ScenarioInfo
} from '../types';

const NOW = () => new Date().toISOString();
const TS = (offsetMin: number) =>
  new Date(Date.now() - offsetMin * 60000).toISOString();

export const SCENARIOS: ScenarioInfo[] = [
  {
    id: 'healthy_storage',
    label: 'Healthy Storage',
    description: 'All environmental metrics nominal. No acoustic anomalies.',
    icon: '🟢',
  },
  {
    id: 'rising_environmental_risk',
    label: 'Rising Environmental Risk',
    description: 'CO2 trending up. RH elevated. Temperature marginal.',
    icon: '🟡',
  },
  {
    id: 'experimental_acoustic_event',
    label: 'Experimental Acoustic Event',
    description: 'EXPERIMENTAL: Model flagged unusual audio pattern. Unvalidated.',
    icon: '🔬',
  },
  {
    id: 'combined_warning',
    label: 'Combined Warning — Inspect Required',
    description: 'High CO2 + elevated RH + acoustic anomaly. Inspection recommended.',
    icon: '🔴',
  },
  {
    id: 'return_to_normal',
    label: 'Return to Normal',
    description: 'Post-inspection — conditions normalizing.',
    icon: '↩️',
  },
];

// Static simulated devices and zones (not scenario-dependent)
export const DEMO_DEVICES: Device[] = [
  {
    id: 'demo-esp32-zone-a-01',
    name: 'Demo Zone A Node 1 (Simulated)',
    zone_id: 'zone-a',
    firmware_version: '1.2.0-SIM',
    last_seen: TS(1),
    connected: true,
    inactivity_timeout_sec: 300,
    last_activity_time: TS(1),
    is_active: true,
    sensors: [
      { type: 'SCD41', status: 'ok', last_reading: TS(1) },
      { type: 'INMP441', status: 'ok', last_reading: TS(1) },
      { type: 'BUZZER', status: 'ok' },
    ],
  },
  {
    id: 'demo-esp32-zone-b-01',
    name: 'Demo Zone B Node 1 (Simulated)',
    zone_id: 'zone-b',
    firmware_version: '1.2.0-SIM',
    last_seen: TS(3),
    connected: true,
    inactivity_timeout_sec: 300,
    last_activity_time: TS(3),
    is_active: true,
    sensors: [
      { type: 'SCD41', status: 'ok', last_reading: TS(3) },
      { type: 'INMP441', status: 'ok', last_reading: TS(3) },
      { type: 'BUZZER', status: 'ok' },
    ],
  },
  {
    id: 'demo-esp32-zone-c-01',
    name: 'Demo Zone C Node 1 (Offline Demo)',
    zone_id: 'zone-c',
    firmware_version: '1.1.3-SIM',
    last_seen: TS(45),
    connected: false,
    inactivity_timeout_sec: 300,
    last_activity_time: TS(45),
    is_active: false,
    sensors: [
      { type: 'SCD41', status: 'unknown' },
      { type: 'INMP441', status: 'unknown' },
      { type: 'BUZZER', status: 'unknown' },
    ],
  },
];

export const DEMO_ZONES: Zone[] = [
  { id: 'zone-a', name: 'Zone A — Silo 1', description: 'Primary wheat storage', device_ids: ['demo-esp32-zone-a-01'], health: 'healthy' },
  { id: 'zone-b', name: 'Zone B — Silo 2', description: 'Barley storage', device_ids: ['demo-esp32-zone-b-01'], health: 'healthy' },
  { id: 'zone-c', name: 'Zone C — Silo 3', description: 'Corn storage (offline)', device_ids: ['demo-esp32-zone-c-01'], health: 'unknown' },
];

function makeReading(
  overrides: Partial<EnvironmentalReading> & { offsetMin?: number }
): EnvironmentalReading {
  const { offsetMin = 0, ...rest } = overrides;
  return {
    id: `r-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    timestamp: TS(offsetMin),
    zone_id: 'zone-a',
    device_id: 'demo-esp32-zone-a-01',
    source: 'SIMULATED',
    co2_ppm: 420,
    temperature_c: 18.5,
    relative_humidity_pct: 58,
    co2_valid: true,
    temp_valid: true,
    rh_valid: true,
    ...rest,
  };
}

function healthyReadings(): EnvironmentalReading[] {
  return Array.from({ length: 24 }, (_, i) => makeReading({
    offsetMin: (23 - i) * 15,
    co2_ppm: 415 + Math.round(Math.random() * 15),
    temperature_c: +(18.0 + Math.random() * 1.5).toFixed(1),
    relative_humidity_pct: +(55 + Math.random() * 5).toFixed(1),
  }));
}

function risingReadings(): EnvironmentalReading[] {
  return Array.from({ length: 24 }, (_, i) => makeReading({
    offsetMin: (23 - i) * 15,
    co2_ppm: 450 + i * 30,
    temperature_c: +(19.0 + i * 0.15).toFixed(1),
    relative_humidity_pct: +(62 + i * 0.5).toFixed(1),
  }));
}

function combinedReadings(): EnvironmentalReading[] {
  return Array.from({ length: 24 }, (_, i) => makeReading({
    zone_id: 'zone-b',
    device_id: 'demo-esp32-zone-b-01',
    offsetMin: (23 - i) * 15,
    co2_ppm: 600 + i * 25,
    temperature_c: +(22.0 + i * 0.2).toFixed(1),
    relative_humidity_pct: +(72 + i * 0.8).toFixed(1),
  }));
}

function normalReadings(): EnvironmentalReading[] {
  return Array.from({ length: 24 }, (_, i) => makeReading({
    offsetMin: (23 - i) * 15,
    co2_ppm: 500 - i * 5,
    temperature_c: +(20.5 - i * 0.1).toFixed(1),
    relative_humidity_pct: +(65 - i * 0.3).toFixed(1),
  }));
}

function acousticEvent(
  overrides: Partial<AcousticEvent> = {}
): AcousticEvent {
  return {
    id: `ae-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    timestamp: NOW(),
    zone_id: 'zone-a',
    device_id: 'demo-esp32-zone-a-01',
    source: 'MODEL_EXPERIMENT',
    audio_sample_ref: 'sample-wheat-ambient-001.wav',
    prediction: 'uncertain',
    model_version: 'nocturne-v1-mini (EXPERIMENTAL)',
    score: null,
    score_semantics:
      'Raw model output — not a calibrated infestation probability. Requires expert validation.',
    confidence_band: 'uncertain',
    validation_status: 'unvalidated',
    inference_status: 'unavailable',
    waveform_preview: [0.05, 0.08, 0.06, 0.07, 0.04, 0.06, 0.05, 0.04, 0.06, 0.05, 0.07, 0.06],
    spectrogram_peaks: [{ freq_hz: 440, db: -42.0 }, { freq_hz: 880, db: -48.5 }],
    notes: 'Model compatibility under test. Audio capture working; inference blocked.',
    ...overrides,
  };
}

export function getDemoData(scenario: DemoScenario): {
  readings: EnvironmentalReading[];
  events: AcousticEvent[];
  alerts: Alert[];
  zones: Zone[];
} {
  switch (scenario) {
    case 'healthy_storage':
      return {
        readings: healthyReadings(),
        events: [acousticEvent({ inference_status: 'unavailable', prediction: 'ambient' })],
        alerts: [],
        zones: DEMO_ZONES.map(z => ({ ...z, health: z.id === 'zone-c' ? 'unknown' : 'healthy' } as Zone)),
      };

    case 'rising_environmental_risk':
      return {
        readings: risingReadings(),
        events: [acousticEvent()],
        alerts: [
          {
            id: 'alrt-001',
            timestamp: TS(5),
            zone_id: 'zone-a',
            device_id: 'demo-esp32-zone-a-01',
            severity: 'warning',
            category: 'environmental',
            title: 'CO₂ Trending Up — Zone A',
            message: 'CO₂ exceeded 700 ppm and is rising. Air RH also elevated above 70%. Rule: co2_trend_threshold / rh_high. Note: air RH is NOT grain moisture.',
            triggered_by: ['co2_trend_threshold', 'rh_high'],
            acknowledged: false,
            cleared: false,
            alarm_state: 'active_unack',
            source: 'SIMULATED',
          },
        ],
        zones: DEMO_ZONES.map(z => ({ ...z, health: z.id === 'zone-a' ? 'warning' : z.id === 'zone-c' ? 'unknown' : 'healthy' } as Zone)),
      };

    case 'experimental_acoustic_event':
      return {
        readings: healthyReadings(),
        events: [
          acousticEvent({
            inference_status: 'experimental',
            prediction: 'uncertain — possible_insect_activity',
            score: 0.42,
            score_semantics:
              'EXPERIMENTAL: Raw model confidence 0.42 (low). Not validated against grain-insect recordings. Cannot distinguish storage insects from ambient noise.',
            confidence_band: 'low',
            validation_status: 'unvalidated',
            inference_duration_ms: 48,
            waveform_preview: [0.08, 0.12, 0.35, 0.65, 0.78, 0.45, 0.22, 0.15, 0.48, 0.82, 0.61, 0.28, 0.18, 0.32, 0.14, 0.09],
            spectrogram_peaks: [
              { freq_hz: 1250, db: -16.2 },
              { freq_hz: 2400, db: -22.4 },
              { freq_hz: 3800, db: -28.1 },
            ],
            notes: 'nocturne-v1-mini output flagged unusual frequency pattern. Human review required before any action.',
          }),
        ],
        alerts: [
          {
            id: 'alrt-002',
            timestamp: NOW(),
            zone_id: 'zone-a',
            severity: 'info',
            category: 'acoustic',
            title: '⚗️ EXPERIMENTAL Acoustic Anomaly — Zone A',
            message: 'Model flagged audio anomaly (score=0.42, low confidence). NOT confirmed. This is an experimental model output — no calibrated infestation probability available. Review audio evidence.',
            triggered_by: ['nocturne_v1_mini_low_confidence'],
            acknowledged: false,
            cleared: false,
            alarm_state: 'active_unack',
            source: 'MODEL_EXPERIMENT',
          },
        ],
        zones: DEMO_ZONES.map(z => z),
      };

    case 'combined_warning':
      return {
        readings: combinedReadings(),
        events: [
          acousticEvent({
            zone_id: 'zone-b',
            device_id: 'demo-esp32-zone-b-01',
            inference_status: 'experimental',
            prediction: 'uncertain — elevated_activity',
            score: 0.55,
            score_semantics:
              'EXPERIMENTAL: Score 0.55, medium-low confidence. Not calibrated for grain storage insects.',
            confidence_band: 'medium',
            validation_status: 'unvalidated',
            inference_duration_ms: 52,
            waveform_preview: [0.12, 0.25, 0.55, 0.88, 0.95, 0.72, 0.41, 0.35, 0.62, 0.89, 0.78, 0.45, 0.29, 0.38, 0.22, 0.11],
            spectrogram_peaks: [
              { freq_hz: 1180, db: -14.5 },
              { freq_hz: 2350, db: -19.8 },
              { freq_hz: 3600, db: -24.0 },
            ],
          }),
        ],
        alerts: [
          {
            id: 'alrt-003',
            timestamp: TS(2),
            zone_id: 'zone-b',
            device_id: 'demo-esp32-zone-b-01',
            severity: 'critical',
            category: 'combined',
            title: '🔴 Combined Risk — Zone B — Inspect Required',
            message: 'HIGH CO2 (>1000 ppm) + elevated Air RH (>80%) + EXPERIMENTAL acoustic anomaly (score=0.55). Contributing factors: co2_critical_threshold, rh_critical, nocturne_v1_mini. Inspection required. Do not claim confirmed infestation from model score alone.',
            triggered_by: ['co2_critical_threshold', 'rh_critical', 'nocturne_v1_mini_medium'],
            acknowledged: false,
            cleared: false,
            alarm_state: 'active_unack',
            source: 'SIMULATED',
          },
        ],
        zones: DEMO_ZONES.map(z => ({ ...z, health: z.id === 'zone-b' ? 'critical' : z.id === 'zone-c' ? 'unknown' : 'healthy' } as Zone)),
      };

    case 'return_to_normal':
      return {
        readings: normalReadings(),
        events: [acousticEvent({ inference_status: 'unavailable', prediction: 'ambient' })],
        alerts: [
          {
            id: 'alrt-003',
            timestamp: TS(120),
            zone_id: 'zone-b',
            severity: 'critical',
            category: 'combined',
            title: '🔴 Combined Risk — Zone B — RESOLVED',
            message: 'Post-inspection: ventilation applied. Conditions normalizing.',
            triggered_by: ['co2_critical_threshold', 'rh_critical', 'nocturne_v1_mini_medium'],
            acknowledged: true,
            acknowledged_at: TS(60),
            acknowledged_by: 'Site Inspector',
            inspection_notes: 'Inspected Zone B. Ventilation fan opened. No visible infestation found. Conditions improving.',
            cleared: true,
            cleared_at: TS(40),
            cleared_by: 'Automated Rule Engine (CO2 < 550 ppm)',
            clear_notes: 'CO2 dropped below 500 ppm and Air RH dropped below 65%.',
            alarm_state: 'cleared_ack',
            source: 'SIMULATED',
          },
          {
            id: 'alrt-004',
            timestamp: TS(90),
            zone_id: 'zone-a',
            severity: 'warning',
            category: 'environmental',
            title: 'CO₂ Spike — Zone A — Auto-Cleared',
            message: 'Temporary CO₂ spike cleared after purge cycle. Awaiting operator review.',
            triggered_by: ['co2_trend_threshold'],
            acknowledged: false,
            cleared: true,
            cleared_at: TS(15),
            cleared_by: 'Environmental Rule Engine',
            clear_notes: 'Readings stabilized below 500 ppm.',
            alarm_state: 'cleared_unack',
            source: 'SIMULATED',
          },
        ],
        zones: DEMO_ZONES.map(z => ({ ...z, health: z.id === 'zone-c' ? 'unknown' : 'healthy' } as Zone)),
      };
  }
}

