import { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { MapPin, Wifi, WifiOff, Thermometer, Wind, Droplets, AlertTriangle, CheckCircle, ArrowRight } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Legend } from 'recharts';
import { SourceBadge } from '../components/SourceBadge';
import type { Zone, Device, EnvironmentalReading, Alert } from '../types';

interface Props {
  zones: Zone[];
  devices: Device[];
  readings: EnvironmentalReading[];
  alerts?: Alert[];
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

type TimeRange = '1h' | '6h' | '24h' | 'all';
type Resolution = 'raw' | '15m' | '1h';

export function StorageZones({ zones, devices, readings, alerts = [] }: Props) {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const zoneParam = searchParams.get('zone');

  const [selectedZone, setSelectedZone] = useState<string>(
    zoneParam && zones.some(z => z.id === zoneParam) ? zoneParam : (zones[0]?.id ?? '')
  );
  const [timeRange, setTimeRange] = useState<TimeRange>('6h');
  const [resolution, setResolution] = useState<Resolution>('raw');

  useEffect(() => {
    if (zoneParam && zones.some(z => z.id === zoneParam)) {
      setSelectedZone(zoneParam);
    }
  }, [zoneParam, zones]);

  const handleSelectZone = (id: string) => {
    setSelectedZone(id);
    setSearchParams({ zone: id });
  };

  const zone = zones.find(z => z.id === selectedZone);
  const zoneDevices = devices.filter(d => d.zone_id === selectedZone);
  const allZoneReadings = readings.filter(r => r.zone_id === selectedZone);

  const getFilteredReadings = () => {
    switch (timeRange) {
      case '1h': return allZoneReadings.slice(-4);
      case '6h': return allZoneReadings.slice(-24);
      case '24h': return allZoneReadings.slice(-96);
      case 'all': return allZoneReadings;
    }
  };

  const filteredReadings = getFilteredReadings();
  const latest = allZoneReadings[allZoneReadings.length - 1];
  const zoneAlerts = alerts.filter(a => a.zone_id === selectedZone);

  const chartData = resolution === 'raw'
    ? filteredReadings.map(r => ({
        time: formatTime(r.timestamp),
        co2: r.co2_ppm,
        rh: r.relative_humidity_pct,
        temp: r.temperature_c,
      }))
    : (() => {
        const bucketMs = (resolution === '15m' ? 15 : 60) * 60 * 1000;
        const buckets: Record<number, { count: number; sum_co2: number; sum_rh: number; sum_temp: number; time: string }> = {};
        for (const r of filteredReadings) {
          const ts = new Date(r.timestamp).getTime();
          const bKey = Math.floor(ts / bucketMs) * bucketMs;
          if (!buckets[bKey]) {
            buckets[bKey] = {
              count: 0,
              sum_co2: 0,
              sum_rh: 0,
              sum_temp: 0,
              time: new Date(bKey).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            };
          }
          buckets[bKey].count++;
          if (r.co2_ppm !== null && r.co2_ppm !== undefined) buckets[bKey].sum_co2 += r.co2_ppm;
          if (r.relative_humidity_pct !== null && r.relative_humidity_pct !== undefined) buckets[bKey].sum_rh += r.relative_humidity_pct;
          if (r.temperature_c !== null && r.temperature_c !== undefined) buckets[bKey].sum_temp += r.temperature_c;
        }
        return Object.keys(buckets).sort().map(k => {
          const b = buckets[Number(k)];
          return {
            time: b.time,
            co2: Math.round((b.sum_co2 / b.count) * 10) / 10,
            rh: Math.round((b.sum_rh / b.count) * 10) / 10,
            temp: Math.round((b.sum_temp / b.count) * 10) / 10,
          };
        });
      })();

  const healthIcon = (h: Zone['health']) =>
    h === 'healthy' ? <CheckCircle size={14} /> : <AlertTriangle size={14} />;

  return (
    <div className="ss-page">
      <div className="ss-page-header">
        <div>
          <h1 className="ss-page-title">Storage Zones</h1>
          <div className="ss-page-subtitle">Silo-level environmental telemetry, device mesh, and alarm tracking</div>
        </div>
      </div>

      {/* Zone selector */}
      <div className="ss-zone-tabs">
        {zones.map(z => (
          <button
            key={z.id}
            id={`zone-tab-${z.id}`}
            className={`ss-zone-tab ${selectedZone === z.id ? 'active' : ''} health-${z.health}`}
            onClick={() => handleSelectZone(z.id)}
          >
            <MapPin size={14} />
            <span>{z.name}</span>
            <span className={`ss-zone-health-dot health-${z.health}`} />
          </button>
        ))}
      </div>

      {zone && (
        <>
          {/* Zone info */}
          <section className="ss-section">
            <div className="ss-zone-detail-header">
              <div>
                <h2 className="ss-section-title">{zone.name}</h2>
                <p className="ss-text-sub">{zone.description}</p>
              </div>
              <div className={`ss-zone-health-badge health-${zone.health}`}>
                {healthIcon(zone.health)}
                {zone.health.charAt(0).toUpperCase() + zone.health.slice(1)}
              </div>
            </div>
          </section>

          {/* Devices in Zone */}
          <section className="ss-section">
            <div className="ss-section-header-row">
              <h2 className="ss-section-title">Devices in Zone ({zoneDevices.length})</h2>
              <button
                className="ss-btn ss-btn-ghost ss-text-xs"
                onClick={() => navigate('/devices')}
              >
                All Device Registry <ArrowRight size={13} />
              </button>
            </div>
            <div className="ss-device-grid">
              {zoneDevices.map(d => {
                const ago = Math.round((Date.now() - new Date(d.last_seen).getTime()) / 60000);
                return (
                  <div
                    key={d.id}
                    className={`ss-device-card ${d.connected ? 'connected' : 'offline'} clickable`}
                    onClick={() => navigate('/devices')}
                  >
                    <div className="ss-device-header">
                      <span className="ss-device-name">{d.name}</span>
                      {d.connected
                        ? <span className="ss-conn-badge"><Wifi size={12} /> Connected</span>
                        : <span className="ss-conn-badge offline"><WifiOff size={12} /> Offline</span>
                      }
                    </div>
                    <div className="ss-device-id ss-mono">{d.id}</div>
                    <div className="ss-device-fw">FW: {d.firmware_version} · Timeout: {d.inactivity_timeout_sec}s</div>
                    <div className="ss-device-last">
                      Last seen: {ago < 1 ? '<1 min ago' : `${ago} min ago`}
                    </div>
                    <div className="ss-sensor-list">
                      {d.sensors.map(s => (
                        <span key={s.type} className={`ss-sensor-badge status-${s.status}`}>
                          {s.type}: {s.status}
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })}
              {zoneDevices.length === 0 && <div className="ss-empty">No devices registered for this zone</div>}
            </div>
          </section>

          {/* Latest reading */}
          <section className="ss-section">
            <h2 className="ss-section-title">
              Current Zone Readings {latest && <SourceBadge source={latest.source} />}
            </h2>
            {latest ? (
              <div className="ss-reading-grid">
                <div className="ss-reading-item">
                  <Wind size={18} className="ss-icon-co2" />
                  <div>
                    <div className="ss-reading-val">{latest.co2_ppm?.toFixed(0) ?? '—'} <span className="ss-reading-unit">ppm CO₂</span></div>
                    {!latest.co2_valid && <div className="ss-reading-warn">⚠ invalid reading</div>}
                    <div className="ss-reading-note">SCD41 photoacoustic NDIR</div>
                  </div>
                </div>
                <div className="ss-reading-item">
                  <Thermometer size={18} className="ss-icon-temp" />
                  <div>
                    <div className="ss-reading-val">{latest.temperature_c?.toFixed(1) ?? '—'} <span className="ss-reading-unit">°C</span></div>
                    {!latest.temp_valid && <div className="ss-reading-warn">⚠ invalid reading</div>}
                    <div className="ss-reading-note">Air temperature</div>
                  </div>
                </div>
                <div className="ss-reading-item">
                  <Droplets size={18} className="ss-icon-rh" />
                  <div>
                    <div className="ss-reading-val">{latest.relative_humidity_pct?.toFixed(1) ?? '—'} <span className="ss-reading-unit">% Air RH</span></div>
                    <div className="ss-reading-note">Air relative humidity — NOT grain moisture content</div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="ss-empty">No readings for this zone</div>
            )}
          </section>

          {/* Dual Y-Axis History Chart (Grafana Benchmark) */}
          {chartData.length > 0 && (
            <section className="ss-section">
              <div className="ss-section-header-row">
                <div>
                  <h2 className="ss-section-title">Zone Telemetry History</h2>
                  <div className="ss-text-muted ss-text-xs">
                    Dual-axis view: CO₂ (ppm) on left scale; Temperature (°C) and Air RH (%) on right scale
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
                  <div className="ss-time-range-picker">
                    <span className="ss-text-xs ss-text-muted" style={{ marginRight: '4px' }}>Range:</span>
                    {(['1h', '6h', '24h', 'all'] as const).map(tr => (
                      <button
                        key={tr}
                        id={`zone-time-range-btn-${tr}`}
                        className={`ss-range-btn ${timeRange === tr ? 'active' : ''}`}
                        onClick={() => setTimeRange(tr)}
                      >
                        {tr.toUpperCase()}
                      </button>
                    ))}
                  </div>

                  <div className="ss-time-range-picker">
                    <span className="ss-text-xs ss-text-muted" style={{ marginRight: '4px' }}>Rollup:</span>
                    {(['raw', '15m', '1h'] as const).map(res => (
                      <button
                        key={res}
                        id={`zone-res-btn-${res}`}
                        className={`ss-range-btn ${resolution === res ? 'active' : ''}`}
                        onClick={() => setResolution(res)}
                        title={res === 'raw' ? 'Raw 15-min sensor samples' : `InfluxDB ${res} mean downsampling bucket`}
                      >
                        {res.toUpperCase()}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="ss-chart-wrap">
                <ResponsiveContainer width="100%" height={280}>
                  <LineChart data={chartData} margin={{ top: 15, right: 30, left: 10, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                    <XAxis dataKey="time" tick={{ fill: '#94a3b8', fontSize: 11 }} />

                    {/* Left YAxis for CO2 */}
                    <YAxis
                      yAxisId="co2"
                      orientation="left"
                      tick={{ fill: '#818cf8', fontSize: 11 }}
                      domain={[300, 'auto']}
                      label={{ value: 'CO₂ ppm', angle: -90, position: 'insideLeft', fill: '#818cf8', fontSize: 11 }}
                    />

                    {/* Right YAxis for Temp & RH */}
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

                    {/* Threshold Reference Lines */}
                    <ReferenceLine yAxisId="co2" y={700} stroke="#eab308" strokeDasharray="4 4" strokeWidth={1.5} />
                    <ReferenceLine yAxisId="co2" y={1200} stroke="#ef4444" strokeDasharray="4 4" strokeWidth={1.5} />
                    <ReferenceLine yAxisId="env" y={70} stroke="#22d3ee" strokeDasharray="3 3" strokeWidth={1.5} />

                    <Line yAxisId="co2" type="monotone" dataKey="co2" name="CO₂ (ppm)" stroke="#6366f1" dot={false} strokeWidth={2.5} />
                    <Line yAxisId="env" type="monotone" dataKey="rh" name="Air RH (%)" stroke="#22d3ee" dot={false} strokeWidth={2} />
                    <Line yAxisId="env" type="monotone" dataKey="temp" name="Temp (°C)" stroke="#fb923c" dot={false} strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
                <div className="ss-chart-threshold-legend">
                  <span className="th-item th-warn">--- CO₂ Warn (700 ppm)</span>
                  <span className="th-item th-crit">--- CO₂ Crit (1200 ppm)</span>
                  <span className="th-item th-rh">--- Air RH Warn (70%)</span>
                </div>
              </div>
            </section>
          )}

          {/* Zone-Specific Alarms */}
          <section className="ss-section">
            <h2 className="ss-section-title">Active & Historical Alarms for {zone.name}</h2>
            {zoneAlerts.length === 0 ? (
              <div className="ss-empty ss-empty-ok">
                <CheckCircle size={18} />
                <span>No active alarms for this storage silo</span>
              </div>
            ) : (
              <div className="ss-alert-list">
                {zoneAlerts.map(a => (
                  <div key={a.id} className={`ss-alert-row sev-${a.severity}`}>
                    <AlertTriangle size={16} />
                    <div className="ss-alert-body">
                      <div className="ss-alert-title">{a.title}</div>
                      <div className="ss-alert-meta">
                        {new Date(a.timestamp).toLocaleString()} ·
                        <span className={`ss-alarm-state-tag state-${a.alarm_state ?? 'active_unack'}`}>
                          {a.alarm_state === 'active_ack' ? 'Active · Acked'
                            : a.alarm_state === 'cleared_unack' ? 'Cleared · Unacked'
                            : a.alarm_state === 'cleared_ack' ? 'Cleared · Acked'
                            : 'Active · Unacked'}
                        </span>
                        <SourceBadge source={a.source} />
                      </div>
                      <div className="ss-text-sub ss-text-xs ss-mt-1">{a.message}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}

