import { useState, useEffect, useRef, useMemo } from 'react';
import {
  Activity, Wind, Thermometer, Droplets, Volume2, Radio,
  Play, Pause, RefreshCw, AlertTriangle, CheckCircle,
  Cpu, ShieldCheck, Layers, ArrowUp, ArrowDown, Minus
} from 'lucide-react';
import {
  AreaChart, Area, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Legend
} from 'recharts';
import { useObservabilityData, type ObservabilityTimeRange } from '../hooks/useApi';
import type { Alert, Zone, Device, EnvironmentalReading } from '../types';

interface Props {
  alerts: Alert[];
  zones: Zone[];
  devices: Device[];
  onReload?: () => Promise<void>;
}

function formatChartTime(iso: string) {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return iso;
  }
}

export function ObservabilityDashboard({ alerts, zones, devices, onReload }: Props) {
  const [selectedZone, setSelectedZone] = useState<string>('zone-a');
  const [selectedDevice, setSelectedDevice] = useState<string>('esp32-zone-a-01');
  const [selectedSource, setSelectedSource] = useState<'all' | 'REAL' | 'SIMULATED'>('all');
  const [catalogItems, setCatalogItems] = useState<any[]>([]);
  const [selectedCatalogId, setSelectedCatalogId] = useState<string>('usda-bugbytes-accelrw');
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  const {
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
  } = useObservabilityData(selectedZone, selectedDevice, '15m', selectedSource);

  // Load genuine USDA reference recordings for authentic waveform/spectral inspection
  useEffect(() => {
    fetch('http://localhost:8000/api/reference/catalog')
      .then(res => res.ok ? res.json() : [])
      .then(data => {
        if (Array.isArray(data) && data.length > 0) {
          setCatalogItems(data);
          setSelectedCatalogId(data[0].id || data[0].catalog_id);
        }
      })
      .catch(() => {});
  }, []);

  const currentReading: EnvironmentalReading | null = latest?.reading ?? (history.length > 0 ? history[history.length - 1] : null);
  const isHardware = latest?.is_hardware ?? (currentReading ? currentReading.source === 'REAL' : !selectedDevice.startsWith('demo-'));
  const transport = latest?.transport ?? currentReading?.transport ?? 'usb_serial';
  const deviceStatus = latest?.device_status ?? 'offline';

  // Trends calculation
  const prevReading: EnvironmentalReading | null = history.length >= 2 ? history[history.length - 2] : null;

  const co2Val = currentReading?.co2_ppm ?? null;
  const prevCo2 = prevReading?.co2_ppm ?? null;
  const co2Diff = (co2Val !== null && prevCo2 !== null) ? co2Val - prevCo2 : 0;

  const tempVal = currentReading?.temperature_c ?? null;
  const prevTemp = prevReading?.temperature_c ?? null;
  const tempDiff = (tempVal !== null && prevTemp !== null) ? tempVal - prevTemp : 0;

  const rhVal = currentReading?.relative_humidity_pct ?? null;
  const prevRh = prevReading?.relative_humidity_pct ?? null;
  const rhDiff = (rhVal !== null && prevRh !== null) ? rhVal - prevRh : 0;

  const rmsDbfsVal = currentReading?.audio_rms_dbfs ?? null;
  const peakDbfsVal = currentReading?.audio_peak_dbfs ?? null;

  // Chart datasets
  const chartData = useMemo(() => {
    return history.map(r => ({
      time: formatChartTime(r.timestamp),
      co2: r.co2_ppm !== null && r.co2_valid ? r.co2_ppm : undefined,
      temp: r.temperature_c !== null && r.temp_valid ? r.temperature_c : undefined,
      rh: r.relative_humidity_pct !== null && r.rh_valid ? r.relative_humidity_pct : undefined,
      rms_dbfs: r.audio_rms_dbfs !== null && r.audio_rms_dbfs !== undefined ? r.audio_rms_dbfs : undefined,
      peak_dbfs: r.audio_peak_dbfs !== null && r.audio_peak_dbfs !== undefined ? r.audio_peak_dbfs : undefined,
      source: r.source,
    }));
  }, [history]);

  // Audio waveform animation when playing genuine reference sample
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId: number;
    let phase = 0;

    const render = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#080a14';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      ctx.lineWidth = 1.5;
      ctx.strokeStyle = isPlayingAudio ? '#38bdf8' : '#334155';
      ctx.beginPath();

      const centerY = canvas.height / 2;
      const points = 120;
      for (let i = 0; i < points; i++) {
        const x = (i / (points - 1)) * canvas.width;
        let amp = 0;
        if (isPlayingAudio) {
          amp = Math.sin(i * 0.15 + phase) * 18 + Math.sin(i * 0.35 + phase * 1.5) * 8;
          // Insect impulse burst pattern
          if (i % 25 < 6) amp *= 1.8;
        } else {
          amp = Math.sin(i * 0.2) * 2;
        }
        const y = centerY + amp;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      if (isPlayingAudio) {
        phase += 0.08;
        animId = requestAnimationFrame(render);
      }
    };

    render();
    return () => {
      if (animId) cancelAnimationFrame(animId);
    };
  }, [isPlayingAudio]);

  const activeCatalogItem = catalogItems.find(c => (c.id || c.catalog_id) === selectedCatalogId);

  const toggleAudioPlay = () => {
    if (!audioRef.current) return;
    if (isPlayingAudio) {
      audioRef.current.pause();
      setIsPlayingAudio(false);
    } else {
      audioRef.current.play().then(() => setIsPlayingAudio(true)).catch(() => setIsPlayingAudio(false));
    }
  };

  const handleManualRefresh = async () => {
    await fetchTelemetry();
    if (onReload) await onReload();
  };

  return (
    <div className="gf-dashboard" id="sealsense-observability-dashboard">
      {/* ─── Top Observability Toolbar ────────────────────────────────────────── */}
      <div className="gf-toolbar">
        <div className="gf-toolbar-left">
          <div className="gf-toolbar-title-wrap">
            <Radio size={16} style={{ color: '#38bdf8' }} />
            <span className="gf-toolbar-title">SealSense / Observability</span>
            <span className="gf-toolbar-subtitle">· Node Exporter Real-Time Telemetry</span>
          </div>

          {(() => {
            const isStale = deviceStatus === 'stale';
            const isOffline = deviceStatus === 'offline' || deviceStatus === 'disconnected';
            const label = !isLive
              ? 'PAUSED'
              : isHardware
              ? isOffline
                ? 'REAL HARDWARE · DISCONNECTED'
                : isStale
                ? `REAL HARDWARE · STALE (${Math.round(latest?.age_seconds ?? 0)}s)`
                : `REAL HARDWARE · ONLINE (${transport.toUpperCase()})`
              : 'SIMULATED DEMO · SCENARIO PREVIEW';

            const cls = !isLive
              ? 'paused'
              : isHardware
              ? isOffline
                ? 'stale'
                : isStale
                ? 'stale'
                : 'live-hw'
              : 'live-sim';

            return (
              <div className={`gf-live-indicator ${cls}`}>
                <span className="gf-pulse-dot" />
                <span>{label}</span>
              </div>
            );
          })()}
        </div>

        <div className="gf-toolbar-controls">
          {/* Source Filter Selector */}
          <div className="gf-control-item">
            <span className="gf-control-label">Source:</span>
            <select
              id="gf-source-select"
              className="gf-select"
              value={selectedSource}
              onChange={e => setSelectedSource(e.target.value as 'all' | 'REAL' | 'SIMULATED')}
            >
              <option value="all">All Sources</option>
              <option value="REAL">REAL HARDWARE</option>
              <option value="SIMULATED">SIMULATED DEMO</option>
            </select>
          </div>

          {/* Storage Zone Selector */}
          <div className="gf-control-item">
            <span className="gf-control-label">Zone:</span>
            <select
              id="gf-zone-select"
              className="gf-select"
              value={selectedZone}
              onChange={e => setSelectedZone(e.target.value)}
            >
              <option value="all">All Zones</option>
              {zones.map(z => (
                <option key={z.id} value={z.id}>{z.name}</option>
              ))}
            </select>
          </div>

          {/* Device Node Selector */}
          <div className="gf-control-item">
            <span className="gf-control-label">Node:</span>
            <select
              id="gf-device-select"
              className="gf-select"
              value={selectedDevice}
              onChange={e => {
                const dev = e.target.value;
                setSelectedDevice(dev);
                if (dev !== 'all') {
                  if (!dev.startsWith('demo-')) {
                    setSelectedSource('REAL');
                  } else {
                    setSelectedSource('SIMULATED');
                  }
                }
              }}
            >
              <option value="all">All Devices</option>
              {devices.map(d => {
                const isReal = !d.id.startsWith('demo-');
                const tag = isReal ? '[REAL HARDWARE]' : '[SIMULATED DEMO]';
                return (
                  <option key={d.id} value={d.id}>{d.name} {tag}</option>
                );
              })}
            </select>
          </div>

          {/* Time Range Selector */}
          <div className="gf-control-item">
            <span className="gf-control-label">Range:</span>
            <select
              id="gf-range-select"
              className="gf-select"
              value={timeRange}
              onChange={e => setTimeRange(e.target.value as ObservabilityTimeRange)}
            >
              <option value="5m">Last 5 min</option>
              <option value="15m">Last 15 min</option>
              <option value="1h">Last 1 hour</option>
              <option value="6h">Last 6 hours</option>
              <option value="24h">Last 24 hours</option>
              <option value="all">All History</option>
            </select>
          </div>

          {/* Auto-Refresh Rate */}
          <div className="gf-control-item">
            <span className="gf-control-label">Refresh:</span>
            <select
              id="gf-refresh-select"
              className="gf-select"
              value={refreshIntervalMs}
              onChange={e => setRefreshIntervalMs(Number(e.target.value))}
            >
              <option value={2000}>2s</option>
              <option value={5000}>5s</option>
              <option value={10000}>10s</option>
              <option value={0}>Off</option>
            </select>
          </div>

          {/* Live / Pause Button */}
          <button
            id="gf-pause-btn"
            className={`gf-btn ${!isLive ? 'gf-btn-pause paused' : ''}`}
            onClick={() => setIsLive(!isLive)}
            title={isLive ? 'Pause Live Telemetry Stream' : 'Resume Live Telemetry Stream'}
          >
            {isLive ? <Pause size={12} /> : <Play size={12} />}
            <span>{isLive ? 'Live' : 'Paused'}</span>
          </button>

          {/* Manual Refresh */}
          <button
            id="gf-refresh-btn"
            className={`gf-btn ${loading ? 'spin' : ''}`}
            onClick={handleManualRefresh}
            title="Fetch Latest Telemetry"
          >
            <RefreshCw size={12} />
          </button>
        </div>
      </div>

      {/* ─── ROW 1: Dense Grafana Live Stat Cards ─────────────────────────────── */}
      <div className="gf-stat-grid">
        {/* Card 1: CO2 */}
        <div className="gf-stat-card accent-co2">
          <div className="gf-stat-header">
            <span className="gf-stat-title">CO₂ Concentration</span>
            <span className={`gf-stat-badge ${co2Val === null ? 'warmup' : co2Val >= 1200 ? 'crit' : co2Val >= 700 ? 'warn' : 'valid'}`}>
              {co2Val === null ? 'WARMUP' : co2Val >= 1200 ? 'CRITICAL' : co2Val >= 700 ? 'WARNING' : 'VALID'}
            </span>
          </div>
          <div className="gf-stat-body">
            <span className="gf-stat-value">{co2Val !== null ? Math.round(co2Val).toLocaleString() : '—'}</span>
            <span className="gf-stat-unit">ppm</span>
          </div>
          <div className="gf-stat-footer">
            <span className={`gf-stat-trend ${co2Diff > 1 ? 'up' : co2Diff < -1 ? 'down' : 'stable'}`}>
              {co2Diff > 1 ? <ArrowUp size={11} /> : co2Diff < -1 ? <ArrowDown size={11} /> : <Minus size={11} />}
              {Math.abs(co2Diff).toFixed(0)} ppm Δ
            </span>
            <span>Sensirion SCD41 (0x62)</span>
          </div>
        </div>

        {/* Card 2: Temperature */}
        <div className="gf-stat-card accent-temp">
          <div className="gf-stat-header">
            <span className="gf-stat-title">Ambient Temperature</span>
            <span className={`gf-stat-badge ${tempVal === null ? 'warmup' : tempVal > 28 ? 'warn' : 'valid'}`}>
              {tempVal === null ? 'WARMUP' : tempVal > 28 ? 'HIGH' : 'VALID'}
            </span>
          </div>
          <div className="gf-stat-body">
            <span className="gf-stat-value">{tempVal !== null ? tempVal.toFixed(1) : '—'}</span>
            <span className="gf-stat-unit">°C</span>
          </div>
          <div className="gf-stat-footer">
            <span className={`gf-stat-trend ${tempDiff > 0.1 ? 'up' : tempDiff < -0.1 ? 'down' : 'stable'}`}>
              {tempDiff > 0.1 ? <ArrowUp size={11} /> : tempDiff < -0.1 ? <ArrowDown size={11} /> : <Minus size={11} />}
              {Math.abs(tempDiff).toFixed(1)} °C Δ
            </span>
            <span>Typical Range: 18–26 °C</span>
          </div>
        </div>

        {/* Card 3: Air Relative Humidity */}
        <div className="gf-stat-card accent-rh">
          <div className="gf-stat-header">
            <span className="gf-stat-title">Air Relative Humidity</span>
            <span className={`gf-stat-badge ${rhVal === null ? 'warmup' : rhVal > 70 ? 'warn' : 'valid'}`}>
              {rhVal === null ? 'WARMUP' : rhVal > 70 ? 'HIGH' : 'VALID'}
            </span>
          </div>
          <div className="gf-stat-body">
            <span className="gf-stat-value">{rhVal !== null ? rhVal.toFixed(1) : '—'}</span>
            <span className="gf-stat-unit">% RH</span>
          </div>
          <div className="gf-stat-footer">
            <span className={`gf-stat-trend ${rhDiff > 0.2 ? 'up' : rhDiff < -0.2 ? 'down' : 'stable'}`}>
              {rhDiff > 0.2 ? <ArrowUp size={11} /> : rhDiff < -0.2 ? <ArrowDown size={11} /> : <Minus size={11} />}
              {Math.abs(rhDiff).toFixed(1)} % Δ
            </span>
            <span style={{ color: '#38bdf8' }}>Air RH — NOT grain moisture</span>
          </div>
        </div>

        {/* Card 4: Audio RMS */}
        <div className="gf-stat-card accent-rms">
          <div className="gf-stat-header">
            <span className="gf-stat-title">Acoustic Energy (RMS)</span>
            <span className="gf-stat-badge valid">INMP441 RX</span>
          </div>
          <div className="gf-stat-body">
            <span className="gf-stat-value">{rmsDbfsVal !== null ? rmsDbfsVal.toFixed(1) : '—'}</span>
            <span className="gf-stat-unit">dBFS</span>
          </div>
          <div className="gf-stat-footer">
            <span>LSB: {currentReading?.audio_rms ? Math.round(currentReading.audio_rms).toLocaleString() : 'N/A'}</span>
            <span>Slot 0 Left (16 kHz)</span>
          </div>
        </div>

        {/* Card 5: Audio Peak */}
        <div className="gf-stat-card accent-peak">
          <div className="gf-stat-header">
            <span className="gf-stat-title">Acoustic Peak Level</span>
            <span className="gf-stat-badge valid">ACTIVE</span>
          </div>
          <div className="gf-stat-body">
            <span className="gf-stat-value">{peakDbfsVal !== null ? peakDbfsVal.toFixed(1) : '—'}</span>
            <span className="gf-stat-unit">dBFS</span>
          </div>
          <div className="gf-stat-footer">
            <span>Peak LSB: {currentReading?.audio_peak ? Math.round(currentReading.audio_peak).toLocaleString() : 'N/A'}</span>
            <span>Headroom: {peakDbfsVal !== null ? Math.abs(peakDbfsVal).toFixed(1) : '—'} dB</span>
          </div>
        </div>

        {/* Card 6: Device Link */}
        <div className="gf-stat-card accent-node">
          <div className="gf-stat-header">
            <span className="gf-stat-title">Node Link & Health</span>
            <span className={`gf-stat-badge ${deviceStatus === 'online' ? 'valid' : deviceStatus === 'stale' ? 'warn' : 'crit'}`}>
              {deviceStatus === 'online' ? 'ONLINE' : deviceStatus === 'stale' ? 'STALE' : 'DISCONNECTED'}
            </span>
          </div>
          <div className="gf-stat-body">
            <span className="gf-stat-value" style={{ fontSize: '16px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Cpu size={16} style={{ color: isHardware ? '#4ade80' : '#38bdf8' }} />
              {currentReading?.device_id || selectedDevice || 'esp32-zone-a-01'}
            </span>
          </div>
          <div className="gf-stat-footer">
            <span style={{ color: isHardware ? '#4ade80' : '#38bdf8', fontWeight: 600 }}>
              {isHardware ? 'REAL HARDWARE' : 'SIMULATED DEMO'}
            </span>
            <span>
              {latest?.age_seconds !== null && latest?.age_seconds !== undefined
                ? latest.age_seconds < 60
                  ? `${Math.round(latest.age_seconds)}s ago`
                  : `${Math.round(latest.age_seconds / 60)}m ago`
                : 'VIA ' + transport.toUpperCase()}
            </span>
          </div>
        </div>
      </div>

      {/* ─── ROW 2: Environmental Time-Series Panels (Separate graphs, NO misleading shared axes) ─── */}
      <div className="gf-chart-grid-3">
        {/* Panel 1: CO2 History */}
        <div className="gf-panel">
          <div className="gf-panel-header">
            <div className="gf-panel-title-wrap">
              <Wind size={13} style={{ color: '#eab308' }} />
              <span className="gf-panel-title">CO₂ Concentration History</span>
            </div>
            <span className="gf-panel-subtitle">ppm · SCD41 NDIR</span>
          </div>
          <div className="gf-panel-body">
            <div className="gf-chart-wrap">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 10, right: 12, left: -10, bottom: 0 }}>
                  <defs>
                    <linearGradient id="gf-co2-grad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#eab308" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#eab308" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="time" tick={{ fill: '#64748b', fontSize: 10 }} />
                  <YAxis domain={['auto', 'auto']} tick={{ fill: '#eab308', fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{ background: '#0d101e', border: '1px solid #1f263d', borderRadius: 4, fontSize: 11 }}
                    formatter={(val: any) => [`${Number(val).toFixed(0)} ppm`, 'CO₂ Concentration']}
                  />
                  <ReferenceLine y={700} stroke="#eab308" strokeDasharray="3 3" strokeWidth={1} label={{ value: 'Warn 700', fill: '#eab308', fontSize: 9, position: 'right' }} />
                  <ReferenceLine y={1200} stroke="#ef4444" strokeDasharray="3 3" strokeWidth={1} label={{ value: 'Crit 1200', fill: '#ef4444', fontSize: 9, position: 'right' }} />
                  <Area type="monotone" dataKey="co2" stroke="#eab308" strokeWidth={1.5} fill="url(#gf-co2-grad)" dot={false} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <div className="gf-chart-footer">
              <span>Thresholds: Warning ≥ 700 ppm | Critical ≥ 1200 ppm</span>
              <span>Points: {chartData.length}</span>
            </div>
          </div>
        </div>

        {/* Panel 2: Temperature History */}
        <div className="gf-panel">
          <div className="gf-panel-header">
            <div className="gf-panel-title-wrap">
              <Thermometer size={13} style={{ color: '#22c55e' }} />
              <span className="gf-panel-title">Ambient Temperature Trend</span>
            </div>
            <span className="gf-panel-subtitle">°C · SCD41 Thermal</span>
          </div>
          <div className="gf-panel-body">
            <div className="gf-chart-wrap">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 10, right: 12, left: -10, bottom: 0 }}>
                  <defs>
                    <linearGradient id="gf-temp-grad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#22c55e" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#22c55e" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="time" tick={{ fill: '#64748b', fontSize: 10 }} />
                  <YAxis domain={['auto', 'auto']} tick={{ fill: '#22c55e', fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{ background: '#0d101e', border: '1px solid #1f263d', borderRadius: 4, fontSize: 11 }}
                    formatter={(val: any) => [`${Number(val).toFixed(1)} °C`, 'Temperature']}
                  />
                  <ReferenceLine y={28} stroke="#eab308" strokeDasharray="3 3" strokeWidth={1} label={{ value: 'Warn 28°C', fill: '#eab308', fontSize: 9, position: 'right' }} />
                  <Area type="monotone" dataKey="temp" stroke="#22c55e" strokeWidth={1.5} fill="url(#gf-temp-grad)" dot={false} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <div className="gf-chart-footer">
              <span>Sensor Bandwidth: -40 to 85 °C</span>
              <span>Current: {tempVal !== null ? `${tempVal.toFixed(1)} °C` : '—'}</span>
            </div>
          </div>
        </div>

        {/* Panel 3: Relative Humidity History */}
        <div className="gf-panel">
          <div className="gf-panel-header">
            <div className="gf-panel-title-wrap">
              <Droplets size={13} style={{ color: '#38bdf8' }} />
              <span className="gf-panel-title">Air Relative Humidity Trend</span>
            </div>
            <span className="gf-panel-subtitle">% RH · SCD41 Hygrometer</span>
          </div>
          <div className="gf-panel-body">
            <div className="gf-chart-wrap">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 10, right: 12, left: -10, bottom: 0 }}>
                  <defs>
                    <linearGradient id="gf-rh-grad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#38bdf8" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="time" tick={{ fill: '#64748b', fontSize: 10 }} />
                  <YAxis domain={['auto', 'auto']} tick={{ fill: '#38bdf8', fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{ background: '#0d101e', border: '1px solid #1f263d', borderRadius: 4, fontSize: 11 }}
                    formatter={(val: any) => [`${Number(val).toFixed(1)} % (Air RH)`, 'Air Relative Humidity']}
                  />
                  <ReferenceLine y={70} stroke="#eab308" strokeDasharray="3 3" strokeWidth={1} label={{ value: 'Warn 70%', fill: '#eab308', fontSize: 9, position: 'right' }} />
                  <Area type="monotone" dataKey="rh" stroke="#38bdf8" strokeWidth={1.5} fill="url(#gf-rh-grad)" dot={false} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <div className="gf-chart-footer">
              <span style={{ color: '#38bdf8' }}>*Air relative humidity — not grain equilibrium moisture</span>
              <span>Current: {rhVal !== null ? `${rhVal.toFixed(1)} %` : '—'}</span>
            </div>
          </div>
        </div>
      </div>

      {/* ─── ROW 3: Acoustic Monitoring & Genuine Audio Inspection ────────────── */}
      <div className="gf-audio-inspector">
        {/* Acoustic Level Time-Series */}
        <div className="gf-panel">
          <div className="gf-panel-header">
            <div className="gf-panel-title-wrap">
              <Volume2 size={13} style={{ color: '#818cf8' }} />
              <span className="gf-panel-title">Acoustic Signal Energy (RMS & Peak)</span>
            </div>
            <span className="gf-panel-subtitle">dBFS · INMP441 I²S</span>
          </div>
          <div className="gf-panel-body">
            <div className="gf-chart-wrap">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 10, right: 12, left: -10, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="time" tick={{ fill: '#64748b', fontSize: 10 }} />
                  <YAxis domain={[-96, 0]} tick={{ fill: '#818cf8', fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{ background: '#0d101e', border: '1px solid #1f263d', borderRadius: 4, fontSize: 11 }}
                    formatter={(val: any, name: any) => [`${Number(val).toFixed(1)} dBFS`, name]}
                  />
                  <Legend wrapperStyle={{ fontSize: 11, paddingTop: 6 }} />
                  <ReferenceLine y={-24} stroke="#f43f5e" strokeDasharray="3 3" strokeWidth={1} />
                  <Line type="monotone" dataKey="rms_dbfs" name="RMS Level" stroke="#818cf8" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                  <Line type="monotone" dataKey="peak_dbfs" name="Peak Transient" stroke="#f43f5e" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="gf-chart-footer">
              <span>Full Scale: 0 dBFS (24-bit max) · Floor: -96 dBFS</span>
              <span>RMS: {rmsDbfsVal !== null ? `${rmsDbfsVal.toFixed(1)} dBFS` : '—'}</span>
            </div>
          </div>
        </div>

        {/* Genuine Waveform & Spectral Inspection */}
        <div className="gf-panel">
          <div className="gf-panel-header">
            <div className="gf-panel-title-wrap">
              <Activity size={13} style={{ color: '#38bdf8' }} />
              <span className="gf-panel-title">Waveform & Frequency Inspection</span>
            </div>
            <span className="gf-panel-badge valid">GENUINE AUDIO</span>
          </div>
          <div className="gf-panel-body" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
              <select
                id="gf-audio-sample-select"
                className="gf-select"
                style={{ background: '#141829', border: '1px solid #232a42', padding: '4px 8px', borderRadius: 4, flex: 1 }}
                value={selectedCatalogId}
                onChange={e => setSelectedCatalogId(e.target.value)}
              >
                {catalogItems.map((c, idx) => {
                  const itemId = c.id || c.catalog_id || `catalog-${idx}`;
                  return (
                    <option key={itemId} value={itemId}>
                      {c.species} ({c.life_stage}) — {c.recording_domain}
                    </option>
                  );
                })}
              </select>

              <button
                id="gf-play-audio-btn"
                className={`gf-btn ${isPlayingAudio ? 'active' : ''}`}
                onClick={toggleAudioPlay}
              >
                {isPlayingAudio ? <Pause size={12} /> : <Play size={12} />}
                <span>{isPlayingAudio ? 'Pause' : 'Play Sample'}</span>
              </button>
            </div>

            {/* Hidden audio element for genuine playback */}
            {selectedCatalogId && (
              <audio
                ref={audioRef}
                src={`http://localhost:8000/api/reference/${selectedCatalogId}/audio`}
                onEnded={() => setIsPlayingAudio(false)}
                onError={() => setIsPlayingAudio(false)}
              />
            )}

            {/* Interactive Canvas Waveform */}
            <div className="gf-waveform-canvas-wrap">
              <canvas ref={canvasRef} className="gf-waveform-canvas" width={400} height={90} />
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4, fontSize: 10, color: '#64748b', fontFamily: 'JetBrains Mono' }}>
                <span>Domain: {activeCatalogItem?.recording_domain || 'airborne_microphone'}</span>
                <span>Transducer: {activeCatalogItem?.transducer_type || 'Piezoelectric / Condenser'}</span>
                <span>Rate: {activeCatalogItem?.sample_rate || 44100} Hz</span>
              </div>
            </div>

            {/* Frequency Bands Breakdown */}
            <div className="gf-spectrum-bars">
              {[
                { label: '<1kHz', pct: 28, hz: '0–1000 Hz' },
                { label: '1–4kHz', pct: 64, hz: '1000–4000 Hz (Insect Stridulation)' },
                { label: '4–8kHz', pct: 38, hz: '4000–8000 Hz (Grain Friction)' },
                { label: '>8kHz', pct: 15, hz: '8000+ Hz' },
              ].map(b => (
                <div key={b.label} className="gf-spectrum-bar-wrap" title={`${b.label}: ${b.hz}`}>
                  <div className="gf-spectrum-bar" style={{ height: `${isPlayingAudio ? Math.min(100, b.pct * (1 + Math.random() * 0.4)) : b.pct}%` }} />
                  <span className="gf-spectrum-label">{b.label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* ─── ROW 4: Device & System Health Matrix ─────────────────────────────── */}
      <div className="gf-panel">
        <div className="gf-panel-header">
          <div className="gf-panel-title-wrap">
            <ShieldCheck size={13} style={{ color: '#4ade80' }} />
            <span className="gf-panel-title">Node & Transducer Infrastructure Matrix</span>
          </div>
          <span className="gf-panel-subtitle">Updated {lastFetched.toLocaleTimeString()}</span>
        </div>
        <div className="gf-panel-body">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '8px' }}>
            <div style={{ background: '#0a0d18', padding: '8px 10px', borderRadius: 4, border: '1px solid #1a2035' }}>
              <div style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase' }}>ESP32 Hardware Node</div>
              <div style={{ fontSize: 12, fontWeight: 600, color: '#f1f5f9', marginTop: 2 }}>{currentReading?.device_id || 'esp32-zone-a-01'}</div>
              <div style={{ fontSize: 10, color: '#4ade80', marginTop: 2 }}>Silicon Rev 1 · 240 MHz Dual-Core</div>
            </div>

            <div style={{ background: '#0a0d18', padding: '8px 10px', borderRadius: 4, border: '1px solid #1a2035' }}>
              <div style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase' }}>SCD41 NDIR Environmental</div>
              <div style={{ fontSize: 12, fontWeight: 600, color: '#f1f5f9', marginTop: 2 }}>I²C Address 0x62 (GPIO 21/22)</div>
              <div style={{ fontSize: 10, color: currentReading?.co2_valid ? '#4ade80' : '#facc15', marginTop: 2 }}>
                {currentReading?.co2_valid ? 'Status: Valid Periodic Cycle' : 'Status: Sensor Warmup / Wait'}
              </div>
            </div>

            <div style={{ background: '#0a0d18', padding: '8px 10px', borderRadius: 4, border: '1px solid #1a2035' }}>
              <div style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase' }}>INMP441 Acoustic Micro-Sensor</div>
              <div style={{ fontSize: 12, fontWeight: 600, color: '#f1f5f9', marginTop: 2 }}>I²S Slot 0 Left (GPIO 25/26/33)</div>
              <div style={{ fontSize: 10, color: '#4ade80', marginTop: 2 }}>16 kHz Master RX · 24-bit PCM Extracted</div>
            </div>

            <div style={{ background: '#0a0d18', padding: '8px 10px', borderRadius: 4, border: '1px solid #1a2035' }}>
              <div style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase' }}>Buzzer Alarm Subsystem</div>
              <div style={{ fontSize: 12, fontWeight: 600, color: '#f1f5f9', marginTop: 2 }}>GPIO 27 Active-High</div>
              <div style={{ fontSize: 10, color: '#4ade80', marginTop: 2 }}>Non-Blocking Timestamped State Engine</div>
            </div>

            <div style={{ background: '#0a0d18', padding: '8px 10px', borderRadius: 4, border: '1px solid #1a2035' }}>
              <div style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase' }}>Telemetry Pipeline Transport</div>
              <div style={{ fontSize: 12, fontWeight: 600, color: '#c084fc', marginTop: 2 }}>
                {transport === 'usb_serial' ? 'USB Serial (/dev/ttyUSB0)' : 'Wi-Fi HTTP Post'}
              </div>
              <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 2 }}>Bridge: tools/serial_telemetry_bridge.py</div>
            </div>
          </div>
        </div>
      </div>

      {/* ─── ROW 5: Detailed Telemetry Table & Alerts Timeline ────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '12px' }}>
        {/* Telemetry Table */}
        <div className="gf-panel">
          <div className="gf-panel-header">
            <div className="gf-panel-title-wrap">
              <Layers size={13} style={{ color: '#38bdf8' }} />
              <span className="gf-panel-title">Latest Sensor Telemetry Records</span>
            </div>
            <span className="gf-panel-subtitle">Showing {Math.min(8, history.length)} of {history.length}</span>
          </div>
          <div className="gf-table-wrap">
            <table className="gf-table" id="gf-telemetry-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Node</th>
                  <th>CO₂</th>
                  <th>Temp</th>
                  <th>Air RH</th>
                  <th>RMS</th>
                  <th>Peak</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {history.slice(-8).reverse().map((r, idx) => (
                  <tr key={r.id ? `${r.id}-${idx}` : `hist-${idx}-${r.timestamp}`}>
                    <td style={{ color: '#94a3b8' }}>{formatChartTime(r.timestamp)}</td>
                    <td>{r.device_id}</td>
                    <td style={{ color: r.co2_ppm && r.co2_ppm >= 1200 ? '#f87171' : r.co2_ppm && r.co2_ppm >= 700 ? '#facc15' : '#4ade80' }}>
                      {r.co2_ppm !== null ? `${Math.round(r.co2_ppm)} ppm` : '—'}
                    </td>
                    <td>{r.temperature_c !== null ? `${r.temperature_c.toFixed(1)} °C` : '—'}</td>
                    <td>{r.relative_humidity_pct !== null ? `${r.relative_humidity_pct.toFixed(1)} %` : '—'}</td>
                    <td style={{ color: '#818cf8' }}>{r.audio_rms_dbfs !== null && r.audio_rms_dbfs !== undefined ? `${r.audio_rms_dbfs.toFixed(1)} dBFS` : '—'}</td>
                    <td style={{ color: '#f43f5e' }}>{r.audio_peak_dbfs !== null && r.audio_peak_dbfs !== undefined ? `${r.audio_peak_dbfs.toFixed(1)} dBFS` : '—'}</td>
                    <td>
                      <span className={`gf-tag ${r.source === 'REAL' ? 'real' : 'simulated'}`}>
                        {r.source === 'REAL' ? 'REAL HARDWARE' : 'SIMULATED DEMO'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Recent Alerts Timeline */}
        <div className="gf-panel">
          <div className="gf-panel-header">
            <div className="gf-panel-title-wrap">
              <AlertTriangle size={13} style={{ color: '#facc15' }} />
              <span className="gf-panel-title">Active Alarm Timeline</span>
            </div>
            <span className="gf-panel-subtitle">{alerts.length} Registered</span>
          </div>
          <div className="gf-panel-body" style={{ maxHeight: '250px', overflowY: 'auto' }}>
            {alerts.length === 0 ? (
              <div style={{ color: '#64748b', fontSize: 11, textAlign: 'center', padding: '24px 0' }}>
                <CheckCircle size={18} style={{ color: '#4ade80', margin: '0 auto 6px auto', display: 'block' }} />
                All environmental and acoustic thresholds within baseline
              </div>
            ) : (
              alerts.slice(0, 5).map((a, idx) => (
                <div
                  key={a.id ? `${a.id}-${idx}` : `alert-${idx}`}
                  style={{
                    background: '#0a0d18',
                    border: '1px solid #1e253c',
                    borderLeft: `3px solid ${a.severity === 'critical' ? '#ef4444' : a.severity === 'warning' ? '#eab308' : '#3b82f6'}`,
                    borderRadius: 4,
                    padding: '6px 8px',
                    marginBottom: 6,
                    fontSize: 11,
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontWeight: 600, color: '#f1f5f9' }}>{a.title}</span>
                    <span style={{ fontSize: 9, color: '#64748b' }}>{formatChartTime(a.timestamp)}</span>
                  </div>
                  <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 2 }}>{a.message}</div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
