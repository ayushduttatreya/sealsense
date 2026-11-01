import { useState, useEffect, useCallback } from 'react';
import type { DemoScenario } from '../types';
import { getDemoData, DEMO_DEVICES } from '../lib/demo';
import type {
  EnvironmentalReading, AcousticEvent, Alert, Device, Zone,
} from '../types';

// Try backend; fall back to demo data gracefully
const BASE = 'http://localhost:8000';

async function tryFetch<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${BASE}${path}`, { signal: AbortSignal.timeout(2000) });
    if (!res.ok) return null;
    return res.json() as Promise<T>;
  } catch {
    return null;
  }
}

export function useBackendHealth() {
  const [online, setOnline] = useState(false);
  const check = useCallback(async () => {
    const data = await tryFetch<{ status: string }>('/health');
    setOnline(!!data && data.status === 'ok');
  }, []);
  useEffect(() => { void check(); const id = setInterval(check, 5000); return () => clearInterval(id); }, [check]);
  return online;
}

export type AppMode = 'backend' | 'demo';

export function useSealSenseData(scenario: DemoScenario) {
  const backendOnline = useBackendHealth();
  const mode: AppMode = backendOnline ? 'backend' : 'demo';
  const [readings, setReadings] = useState<EnvironmentalReading[]>([]);
  const [events, setEvents] = useState<AcousticEvent[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [zones, setZones] = useState<Zone[]>([]);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    setLoading(true);
    if (backendOnline) {
      const [r, e, a, d, z] = await Promise.all([
        tryFetch<EnvironmentalReading[]>('/api/readings?limit=100'),
        tryFetch<AcousticEvent[]>('/api/events?limit=50'),
        tryFetch<Alert[]>('/api/alerts?limit=100'),
        tryFetch<Device[]>('/api/devices'),
        tryFetch<Zone[]>('/api/zones'),
      ]);
      if (r) setReadings(r);
      if (e) setEvents(e);
      if (a) setAlerts(a);
      if (d) setDevices(d);
      if (z) setZones(z);
    } else {
      const demo = getDemoData(scenario);
      setReadings(demo.readings);
      setEvents(demo.events);
      setAlerts(demo.alerts);
      setDevices(DEMO_DEVICES);
      setZones(demo.zones);
    }
    setLoading(false);
  }, [backendOnline, scenario]);

  useEffect(() => { void reload(); }, [reload]);

  const acknowledgeAlert = useCallback(async (id: string, notes: string) => {
    if (backendOnline) {
      await fetch(`${BASE}/api/alerts/${id}/acknowledge`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes, acknowledged_by: 'Operator' }),
      });
      await reload();
    } else {
      setAlerts(prev =>
        prev.map(a => {
          if (a.id !== id) return a;
          const acked = true;
          const cleared = a.cleared;
          const alarm_state = cleared ? 'cleared_ack' : 'active_ack';
          return {
            ...a,
            acknowledged: acked,
            acknowledged_at: new Date().toISOString(),
            acknowledged_by: 'Operator',
            inspection_notes: notes,
            alarm_state,
          };
        })
      );
    }
  }, [backendOnline, reload]);

  const clearAlert = useCallback(async (id: string, notes: string) => {
    if (backendOnline) {
      await fetch(`${BASE}/api/alerts/${id}/clear`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes, cleared_by: 'Operator' }),
      });
      await reload();
    } else {
      setAlerts(prev =>
        prev.map(a => {
          if (a.id !== id) return a;
          const cleared = true;
          const acked = a.acknowledged;
          const alarm_state = acked ? 'cleared_ack' : 'cleared_unack';
          return {
            ...a,
            cleared,
            cleared_at: new Date().toISOString(),
            cleared_by: 'Operator',
            clear_notes: notes,
            alarm_state,
          };
        })
      );
    }
  }, [backendOnline, reload]);

  const validateAcousticEvent = useCallback(async (id: string, status: 'validated' | 'rejected', notes: string) => {
    if (backendOnline) {
      await fetch(`${BASE}/api/events/${id}/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status, notes, validator: 'Inspector' }),
      });
      await reload();
    } else {
      setEvents(prev =>
        prev.map(e =>
          e.id === id
            ? {
                ...e,
                validation_status: status,
                validation_notes: notes,
                validated_at: new Date().toISOString(),
                validated_by: 'Inspector',
              }
            : e
        )
      );
    }
  }, [backendOnline, reload]);

  const batchReviewEvents = useCallback(async (eventIds: string[], action: 'reviewed' | 'validated' | 'rejected' = 'reviewed', notes = '') => {
    if (backendOnline) {
      await fetch(`${BASE}/api/events/batch-review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event_ids: eventIds, action, notes, reviewer: 'Operator' }),
      });
      await reload();
    } else {
      setEvents(prev =>
        prev.map(e =>
          eventIds.includes(e.id)
            ? {
                ...e,
                review_status: 'reviewed',
                reviewed_at: new Date().toISOString(),
                reviewed_by: 'Operator',
                ...(action === 'validated' || action === 'rejected'
                  ? { validation_status: action, validation_notes: notes }
                  : {}),
              }
            : e
        )
      );
    }
  }, [backendOnline, reload]);

  const getAlertTrace = useCallback(async (alertId: string) => {
    if (backendOnline) {
      try {
        const res = await fetch(`${BASE}/api/alerts/${alertId}/trace`);
        if (res.ok) {
          return (await res.json()) as import('../types').ExecutionTrace;
        }
      } catch (err) {
        console.warn('API trace fetch failed, falling back to local trace builder', err);
      }
    }
    const alert = alerts.find(a => a.id === alertId);
    const rules = alert?.triggered_by && alert.triggered_by.length > 0 ? alert.triggered_by : ['threshold_breach'];
    return {
      alert_id: alertId,
      triggered_at: alert?.timestamp || new Date().toISOString(),
      zone_id: alert?.zone_id || 'zone-a',
      device_id: alert?.device_id,
      rule_id: rules.join(' + '),
      summary: `Automation trace for ${alert?.title || alertId}. Triggered by ${rules.length} conditions. Action: ${alert?.severity?.toUpperCase() || 'ALERT'} in state ${alert?.alarm_state?.toUpperCase() || 'ACTIVE_UNACK'}.`,
      steps: [
        {
          step_id: 'trigger/0',
          step_type: 'trigger' as const,
          name: `Telemetry Ingest (${alert?.source || 'SIMULATED'})`,
          status: 'passed' as const,
          timestamp: alert?.timestamp || new Date().toISOString(),
          details: { device_id: alert?.device_id, zone_id: alert?.zone_id },
        },
        ...rules.map((r, i) => ({
          step_id: `condition/${i}`,
          step_type: 'condition' as const,
          name: `Evaluate Rule Gate: ${r}`,
          status: 'passed' as const,
          timestamp: alert?.timestamp || new Date().toISOString(),
          details: { rule: r, result: true },
        })),
        {
          step_id: 'action/0',
          step_type: 'action' as const,
          name: 'Generate Actionable Environmental Alert',
          status: 'executed' as const,
          timestamp: alert?.timestamp || new Date().toISOString(),
          details: { severity: alert?.severity, state: alert?.alarm_state },
        },
      ],
    };
  }, [backendOnline, alerts]);

  const setScenario = useCallback(async (s: DemoScenario) => {
    if (backendOnline) {
      await fetch(`${BASE}/api/demo/scenario`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario: s }),
      });
      await reload();
    }
  }, [backendOnline, reload]);

  return {
    mode,
    readings,
    events,
    alerts,
    devices,
    zones,
    loading,
    reload,
    acknowledgeAlert,
    clearAlert,
    validateAcousticEvent,
    batchReviewEvents,
    getAlertTrace,
    setScenario,
  };
}

export type ObservabilityTimeRange = '5m' | '15m' | '1h' | '6h' | '24h' | 'all';

export function useObservabilityData(
  zoneId: string,
  deviceId: string,
  initialTimeRange: ObservabilityTimeRange = '15m',
  sourceFilter: string = 'all'
) {
  const backendOnline = useBackendHealth();
  const [timeRange, setTimeRange] = useState<ObservabilityTimeRange>(initialTimeRange);
  const [refreshIntervalMs, setRefreshIntervalMs] = useState<number>(3000);
  const [isLive, setIsLive] = useState<boolean>(true);
  const [latest, setLatest] = useState<import('../types').LatestTelemetryResponse | null>(null);
  const [history, setHistory] = useState<EnvironmentalReading[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [lastFetched, setLastFetched] = useState<Date>(new Date());

  const fetchTelemetry = useCallback(async () => {
    try {
      const qParams = new URLSearchParams();
      if (zoneId && zoneId !== 'all') qParams.set('zone_id', zoneId);
      if (deviceId && deviceId !== 'all') qParams.set('device_id', deviceId);
      if (sourceFilter && sourceFilter !== 'all') qParams.set('source', sourceFilter);

      const latestPath = `/api/telemetry/latest?${qParams.toString()}`;
      qParams.set('time_range', timeRange);
      qParams.set('limit', '300');
      const historyPath = `/api/telemetry/history?${qParams.toString()}`;

      const [latData, histData] = await Promise.all([
        tryFetch<import('../types').LatestTelemetryResponse>(latestPath),
        tryFetch<import('../types').TelemetryHistoryResponse>(historyPath),
      ]);

      if (latData) setLatest(latData);
      setHistory(histData?.readings ?? []);
      setLastFetched(new Date());
    } finally {
      setLoading(false);
    }
  }, [zoneId, deviceId, timeRange, sourceFilter]);

  useEffect(() => {
    void fetchTelemetry();
  }, [fetchTelemetry]);

  useEffect(() => {
    if (!isLive || refreshIntervalMs <= 0) return;
    const interval = setInterval(() => {
      void fetchTelemetry();
    }, refreshIntervalMs);
    return () => clearInterval(interval);
  }, [isLive, refreshIntervalMs, fetchTelemetry]);

  return {
    latest,
    history,
    loading,
    timeRange,
    setTimeRange,
    refreshIntervalMs,
    setRefreshIntervalMs,
    isLive,
    setIsLive,
    lastFetched,
    fetchTelemetry,
    backendOnline,
  };
}

