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
    retainSample = false,
    isSynthetic = false,
    recordingDomain?: import('../types').RecordingDomain,
  ) => {
    const formData = new FormData();
    formData.append('file', file, filename);
    formData.append('zone_id', zoneId);
    formData.append('device_id', deviceId);
    formData.append('save_event', String(saveEvent));
    formData.append('retain_sample', String(retainSample));
    formData.append('is_synthetic', String(isSynthetic));
    formData.append('input_source', isSynthetic ? 'synthetic' : 'user_upload');
    if (recordingDomain) {
      formData.append('recording_domain', recordingDomain);
    }
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
  audioSamples: (filters?: {
    zone_id?: string;
    ground_truth_label?: string;
    review_status?: string;
    is_synthetic?: boolean;
    limit?: number;
  }) => {
    const params = new URLSearchParams();
    if (filters?.zone_id) params.set('zone_id', filters.zone_id);
    if (filters?.ground_truth_label) params.set('ground_truth_label', filters.ground_truth_label);
    if (filters?.review_status) params.set('review_status', filters.review_status);
    if (filters?.is_synthetic !== undefined) params.set('is_synthetic', String(filters.is_synthetic));
    if (filters?.limit) params.set('limit', String(filters.limit));
    return request<import('../types').RetainedAudioSample[]>(`/api/audio-samples?${params}`);
  },
  audioSample: (id: string) =>
    request<import('../types').RetainedAudioSample>(`/api/audio-samples/${id}`),
  getAudioSampleUrl: (id: string) => `${BASE}/api/audio-samples/${id}/audio`,
  updateSampleAnnotation: (
    id: string,
    payload: {
      ground_truth_label: import('../types').GroundTruthLabel;
      verification_method?: import('../types').VerificationMethod;
      reviewer?: string;
      evidence_notes?: string;
      review_status?: 'UNREVIEWED' | 'REVIEWED';
    }
  ) =>
    request<import('../types').RetainedAudioSample>(`/api/audio-samples/${id}/annotation`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  deleteAudioSample: (id: string) =>
    request<{ deleted: boolean; sample_id: string }>(`/api/audio-samples/${id}`, {
      method: 'DELETE',
    }),
  datasetManifestUrl: (format: 'json' | 'csv' = 'json', include_synthetic = false) =>
    `${BASE}/api/dataset/manifest?format=${format}&include_synthetic=${include_synthetic}`,
  datasetEvaluation: (threshold = 0.05) =>
    request<import('../types').DatasetEvaluationReport>(`/api/dataset/evaluation?threshold=${threshold}`),
  seedDemoAudioSamples: () =>
    request<{ seeded: number; message: string }>('/api/audio-samples/seed-demo', {
      method: 'POST',
    }),
  referenceCatalog: () =>
    request<import('../types').ReferenceAudioCatalogItem[]>('/api/reference/catalog'),
  referenceAudioUrl: (catalogId: string) => `${BASE}/api/reference/${catalogId}/audio`,
  referenceAnalysis: (catalogId: string) =>
    request<{
      catalog_id: string;
      filename: string;
      species: string;
      common_name: string;
      transducer_type: string;
      recording_domain: string;
      analysis: import('../types').SignalAnalysisResult;
    }>(`/api/reference/${catalogId}/analysis`),
  importReference: (payload: import('../types').ReferenceImportRequest) =>
    request<import('../types').AcousticInferenceResult>('/api/reference/import', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  generateSyntheticImpulse: (payload: import('../types').SyntheticImpulseRequest) =>
    request<import('../types').AcousticInferenceResult>('/api/simulation/synthetic/generate', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  syntheticWavUrl: (params?: {
    impulse_rate?: number;
    amplitude?: number;
    noise_level?: number;
    duration_sec?: number;
    seed?: number;
  }) => {
    const q = new URLSearchParams();
    if (params?.impulse_rate !== undefined) q.set('impulse_rate', String(params.impulse_rate));
    if (params?.amplitude !== undefined) q.set('amplitude', String(params.amplitude));
    if (params?.noise_level !== undefined) q.set('noise_level', String(params.noise_level));
    if (params?.duration_sec !== undefined) q.set('duration_sec', String(params.duration_sec));
    if (params?.seed !== undefined) q.set('seed', String(params.seed));
    return `${BASE}/api/simulation/synthetic/wav?${q.toString()}`;
  },
};


