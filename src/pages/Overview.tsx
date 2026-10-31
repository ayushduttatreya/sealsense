import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Thermometer, Wind, Droplets, Activity, AlertTriangle, CheckCircle, Clock, RefreshCw, ChevronRight } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, ReferenceLine } from 'recharts';
import { MetricCard } from '../components/MetricCard';
import { SourceBadge } from '../components/SourceBadge';
import type { EnvironmentalReading, Alert, Zone } from '../types';

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

type TimeRange = '1h' | '6h' | '24h' | 'all';

interface Props {
  readings: EnvironmentalReading[];
  alerts: Alert[];
  zones: Zone[];
  onReload?: () => Promise<void>;
}

export function Overview({ readings, alerts, zones, onReload }: Props) {
  const navigate = useNavigate();
  const [timeRange, setTimeRange] = useState<TimeRange>('6h');
  const [isRefreshing, setIsRefreshing] = useState(false);

  const latest = readings[readings.length - 1];
  const source = latest?.source ?? 'SIMULATED';
  const unacked = alerts.filter(a => !a.acknowledged);
  const criticalCount = unacked.filter(a => a.severity === 'critical').length;
  const warnCount = unacked.filter(a => a.severity === 'warning').length;

  const zoneHealth = (h: Zone['health']) => {
    const map = { healthy: 'ok', warning: 'warn', critical: 'crit', unknown: 'unknown' } as const;
    return map[h];
  };

  const getFilteredReadings = () => {
    switch (timeRange) {
      case '1h': return readings.slice(-4);
      case '6h': return readings.slice(-24);
      case '24h': return readings.slice(-96);
      case 'all': return readings;
    }
  };

  const filtered = getFilteredReadings();

  const chartData = filtered.map(r => ({
    time: formatTime(r.timestamp),
    co2: r.co2_ppm,
    temp: r.temperature_c,
    rh: r.relative_humidity_pct,
  }));

  const co2Trend = readings.length >= 3
    ? (readings[readings.length-1]?.co2_ppm ?? 0) > (readings[readings.length-3]?.co2_ppm ?? 0)
      ? 'up' : 'stable'
    : 'stable';

  const handleManualRefresh = async () => {
    if (!onReload) return;
    setIsRefreshing(true);
    await onReload();
    setTimeout(() => setIsRefreshing(false), 500);
  };

  return (
    <div className="ss-page">
      <div className="ss-page-header">
        <div>
          <h1 className="ss-page-title">System Overview</h1>
          <div className="ss-page-subtitle">Real-time silo telemetry, environmental health & alarm states</div>
        </div>
        <div className="ss-page-meta">
          <Clock size={14} />
          <span>Updated {latest ? new Date(latest.timestamp).toLocaleTimeString() : '—'}</span>
          {latest && <SourceBadge source={source} />}
          {onReload && (
            <button
              id="overview-refresh-btn"
              className={`ss-btn ss-btn-ghost ss-btn-icon ${isRefreshing ? 'spin' : ''}`}
              title="Refresh Telemetry"
              onClick={handleManualRefresh}
            >
              <RefreshCw size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Zone Health with Drill-Down Navigation */}
      <section className="ss-section">
        <div className="ss-section-header-row">
          <h2 className="ss-section-title">Storage Zone Health</h2>
          <span className="ss-text-muted ss-text-xs">Click a zone to inspect detailed telemetry</span>
        </div>
        <div className="ss-zone-grid">
          {zones.map(z => (
            <div
              key={z.id}
              id={`overview-zone-card-${z.id}`}
              className={`ss-zone-card status-${zoneHealth(z.health)} clickable`}
              onClick={() => navigate(`/zones?zone=${z.id}`)}
              role="button"
              tabIndex={0}
            >
              <div className="ss-zone-header-compact">
                <div className="ss-zone-name">{z.name}</div>
                <ChevronRight size={14} className="ss-zone-arrow" />
              </div>
              <div className="ss-zone-desc">{z.description}</div>
              <div className={`ss-zone-health health-${z.health}`}>
                {z.health === 'healthy' && <CheckCircle size={14} />}
                {(z.health === 'warning' || z.health === 'critical') && <AlertTriangle size={14} />}
                {z.health.charAt(0).toUpperCase() + z.health.slice(1)}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Key Metrics */}
      <section className="ss-section">
        <h2 className="ss-section-title">Environmental Metrics <span className="ss-section-sub">Zone A · SCD41 Active Node</span></h2>
        <div className="ss-metrics-grid">
          <MetricCard
            label="CO₂ Concentration"
            value={latest?.co2_ppm?.toFixed(0) ?? '—'}
            unit=" ppm"
            icon={<Wind size={18} />}
            trend={co2Trend}
            status={
              (latest?.co2_ppm ?? 0) > 1000 ? 'crit'
              : (latest?.co2_ppm ?? 0) > 700 ? 'warn' : 'ok'
            }
            sublabel={(latest?.co2_valid === false) ? '⚠ reading invalid' : 'Thresholds: Warn 700 | Crit 1200'}
          />
          <MetricCard
            label="Air Temperature"
            value={latest?.temperature_c?.toFixed(1) ?? '—'}
            unit="°C"
            icon={<Thermometer size={18} />}
            status={
              (latest?.temperature_c ?? 0) > 25 ? 'warn' : 'ok'
            }
            sublabel="Thresholds: Warn 25°C | Crit 30°C"
          />
          <MetricCard
            label="Air Relative Humidity"
            value={latest?.relative_humidity_pct?.toFixed(1) ?? '—'}
            unit="%"
            icon={<Droplets size={18} />}
            status={
              (latest?.relative_humidity_pct ?? 0) > 75 ? 'crit'
              : (latest?.relative_humidity_pct ?? 0) > 65 ? 'warn' : 'ok'
            }
            sublabel="Air RH — not grain internal moisture"
          />
          <MetricCard
            label="Active Alarms"
            value={unacked.length}
            icon={<Activity size={18} />}
            status={criticalCount > 0 ? 'crit' : warnCount > 0 ? 'warn' : 'ok'}
            sublabel={`${criticalCount} critical, ${warnCount} warning`}
          />
        </div>
      </section>

      {/* Trend Chart with Dual Y-Axes & Threshold Lines (Grafana Benchmark) */}
      <section className="ss-section">
        <div className="ss-section-header-row">
          <div>
            <h2 className="ss-section-title">Environmental Trends</h2>
            <div className="ss-text-muted ss-text-xs">
              Dual-scale: Left axis = CO₂ (ppm) · Right axis = Temperature (°C) & Air RH (%)
            </div>
          </div>
          <div className="ss-time-range-picker">
            {(['1h', '6h', '24h', 'all'] as const).map(tr => (
              <button
                key={tr}
                id={`time-range-btn-${tr}`}
                className={`ss-range-btn ${timeRange === tr ? 'active' : ''}`}
                onClick={() => setTimeRange(tr)}
              >
                {tr.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        {chartData.length > 0 ? (
          <div className="ss-chart-wrap">
            <ResponsiveContainer width="100%" height={320}>
              <AreaChart data={chartData} margin={{ top: 15, right: 30, left: 10, bottom: 5 }}>
                <defs>
                  <linearGradient id="co2grad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="rhgrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#22d3ee" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#22d3ee" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="tempgrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#fb923c" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#fb923c" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="time" tick={{ fill: '#94a3b8', fontSize: 11 }} />
                
                {/* Left Y-Axis for CO2 (ppm) */}
                <YAxis
                  yAxisId="co2"
                  orientation="left"
                  tick={{ fill: '#818cf8', fontSize: 11 }}
                  domain={[300, 'auto']}
                  label={{ value: 'CO₂ ppm', angle: -90, position: 'insideLeft', fill: '#818cf8', fontSize: 11 }}
                />

                {/* Right Y-Axis for Temp (°C) and Air RH (%) */}
                <YAxis
                  yAxisId="env"
                  orientation="right"
                  tick={{ fill: '#22d3ee', fontSize: 11 }}
                  domain={[0, 100]}
                  label={{ value: 'Temp (°C) / RH (%)', angle: 90, position: 'insideRight', fill: '#22d3ee', fontSize: 11 }}
                />

                <Tooltip
                  contentStyle={{ background: '#1e2130', border: '1px solid #334155', borderRadius: 8, color: '#e2e8f0' }}
                  formatter={(val: any, name: any) => {
                    const num = Number(val);
                    if (name === 'CO₂ (ppm)') return [`${num.toFixed(0)} ppm`, name];
                    if (name === 'Air RH (%)') return [`${num.toFixed(1)} % (Air RH)`, name];
                    if (name === 'Temp (°C)') return [`${num.toFixed(1)} °C`, name];
                    return [val, name];
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 12, color: '#94a3b8', paddingTop: 8 }} />

                {/* Grafana-style visual threshold reference lines */}
                <ReferenceLine yAxisId="co2" y={700} stroke="#eab308" strokeDasharray="4 4" strokeWidth={1.5} />
                <ReferenceLine yAxisId="co2" y={1200} stroke="#ef4444" strokeDasharray="4 4" strokeWidth={1.5} />
                <ReferenceLine yAxisId="env" y={70} stroke="#22d3ee" strokeDasharray="3 3" strokeWidth={1.5} />

                <Area yAxisId="co2" type="monotone" dataKey="co2" name="CO₂ (ppm)" stroke="#6366f1" fill="url(#co2grad)" strokeWidth={2} dot={false} />
                <Area yAxisId="env" type="monotone" dataKey="rh" name="Air RH (%)" stroke="#22d3ee" fill="url(#rhgrad)" strokeWidth={2} dot={false} />
                <Area yAxisId="env" type="monotone" dataKey="temp" name="Temp (°C)" stroke="#fb923c" fill="url(#tempgrad)" strokeWidth={2} dot={false} />
              </AreaChart>
            </ResponsiveContainer>
            <div className="ss-chart-threshold-legend">
              <span className="th-item th-warn">--- CO₂ Warning (700 ppm)</span>
              <span className="th-item th-crit">--- CO₂ Critical (1200 ppm)</span>
              <span className="th-item th-rh">--- Air RH Warning (70%)</span>
            </div>
          </div>
        ) : (
          <div className="ss-empty">No readings available</div>
        )}
      </section>

      {/* Recent Alerts with 4-State Indicators */}
      <section className="ss-section">
        <div className="ss-section-header-row">
          <h2 className="ss-section-title">Recent Alerts</h2>
          <button
            id="overview-view-all-alerts"
            className="ss-btn ss-btn-ghost ss-text-xs"
            onClick={() => navigate('/alerts')}
          >
            View All ({alerts.length})
          </button>
        </div>
        {unacked.length === 0 ? (
          <div className="ss-empty ss-empty-ok">
            <CheckCircle size={20} />
            <span>No active unacknowledged alerts</span>
          </div>
        ) : (
          <div className="ss-alert-list">
            {unacked.slice(0, 5).map(a => (
              <div
                key={a.id}
                className={`ss-alert-row sev-${a.severity} clickable`}
                onClick={() => navigate('/alerts')}
              >
                <AlertTriangle size={16} />
                <div className="ss-alert-body">
                  <div className="ss-alert-title">{a.title}</div>
                  <div className="ss-alert-meta">
                    {new Date(a.timestamp).toLocaleString()} · {a.zone_id}
                    <span className={`ss-alarm-state-tag state-${a.alarm_state ?? 'active_unack'}`}>
                      {a.alarm_state === 'active_ack' ? 'Active · Acked'
                        : a.alarm_state === 'cleared_unack' ? 'Cleared · Unacked'
                        : a.alarm_state === 'cleared_ack' ? 'Cleared · Acked'
                        : 'Active · Unacked'}
                    </span>
                    <SourceBadge source={a.source} />
                  </div>
                </div>
                <ChevronRight size={14} className="ss-text-muted" />
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

