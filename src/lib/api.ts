import type {
  Device, Zone, EnvironmentalReading, AcousticEvent, Alert, DemoScenario
} from '../types';

const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string; version: string }>('/health'),
  devices: () => request<Device[]>('/api/devices'),
  zones: () => request<Zone[]>('/api/zones'),
  readings: (zone_id?: string, limit = 100) =>
    request<EnvironmentalReading[]>(
      `/api/readings?${zone_id ? `zone_id=${zone_id}&` : ''}limit=${limit}`
    ),
  events: (zone_id?: string, limit = 50) =>
    request<AcousticEvent[]>(
      `/api/events?${zone_id ? `zone_id=${zone_id}&` : ''}limit=${limit}`
    ),
  alerts: (category?: string, severity?: string, limit = 100) => {
    const params = new URLSearchParams();
    if (category) params.set('category', category);
    if (severity) params.set('severity', severity);
    params.set('limit', String(limit));
    return request<Alert[]>(`/api/alerts?${params}`);
  },
  acknowledgeAlert: (id: string, notes?: string) =>
    request<Alert>(`/api/alerts/${id}/acknowledge`, {
      method: 'POST',
      body: JSON.stringify({ notes: notes ?? '', acknowledged_by: 'Operator' }),
    }),
  clearAlert: (id: string, notes?: string) =>
    request<Alert>(`/api/alerts/${id}/clear`, {
      method: 'POST',
      body: JSON.stringify({ notes: notes ?? '', cleared_by: 'Operator' }),
    }),
  validateEvent: (id: string, status: 'validated' | 'rejected', notes?: string) =>
    request<AcousticEvent>(`/api/events/${id}/validate`, {
      method: 'POST',
      body: JSON.stringify({ status, notes: notes ?? '', validator: 'Inspector' }),
    }),
  batchReview: (event_ids: string[], action: 'reviewed' | 'validated' | 'rejected' = 'reviewed', notes = '') =>
    request<{ status: string; action: string; reviewed_count: number; message: string }>('/api/events/batch-review', {
      method: 'POST',
      body: JSON.stringify({ event_ids, action, notes, reviewer: 'Operator' }),
    }),
  alertTrace: (id: string) =>
    request<import('../types').ExecutionTrace>(`/api/alerts/${id}/trace`),
  aggregateReadings: (zone_id?: string, bucket_minutes = 15, range_hours = 24) => {
    const params = new URLSearchParams();
    if (zone_id) params.set('zone_id', zone_id);
    params.set('bucket_minutes', String(bucket_minutes));
    params.set('range_hours', String(range_hours));
    return request<import('../types').AggregatedTelemetryResponse>(`/api/readings/aggregate?${params}`);
  },
  setScenario: (scenario: DemoScenario) =>
    request<{ scenario: string; message: string }>('/api/demo/scenario', {
      method: 'POST',
      body: JSON.stringify({ scenario }),
    }),
  uploadAcousticRecording: async (
    file: File | Blob,
    filename = 'recording.wav',
    zoneId = 'zone-a',
    deviceId = 'esp32-zone-a-01',
    saveEvent = false,
  ) => {
    const formData = new FormData();
    formData.append('file', file, filename);
    formData.append('zone_id', zoneId);
    formData.append('device_id', deviceId);
    formData.append('save_event', String(saveEvent));
    const res = await fetch(`${BASE}/api/inference/acoustic/upload`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `Upload failed with status ${res.status}`);
    }
    return res.json() as Promise<import('../types').AcousticInferenceResult>;
  },
};

