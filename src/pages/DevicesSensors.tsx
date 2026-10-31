import { useNavigate } from 'react-router-dom';
import { Wifi, WifiOff, Cpu, Clock, Activity, MapPin, ArrowRight, ShieldCheck, Radio } from 'lucide-react';
import type { Device, Zone } from '../types';

interface Props {
  devices: Device[];
  zones: Zone[];
}

const sensorLabel: Record<string, string> = {
  SCD41: 'SCD41 Environmental (CO₂, Temp, RH)',
  INMP441: 'INMP441 I2S Microphone',
  BUZZER: 'Piezo Buzzer (Rule-Based Alert)',
};

export function DevicesSensors({ devices, zones }: Props) {
  const navigate = useNavigate();
  const zoneMap = Object.fromEntries(zones.map(z => [z.id, z.name]));
  const onlineCount = devices.filter(d => d.connected).length;

  return (
    <div className="ss-page">
      <div className="ss-page-header">
        <div>
          <h1 className="ss-page-title">Device & Sensor Mesh</h1>
          <div className="ss-page-subtitle">
            ThingsBoard connectivity lifecycle: Server-side inactivity detection & hardware inventory
          </div>
        </div>
        <div className="ss-page-meta">
          <span className="ss-status-pill live">
            <Activity size={13} /> {onlineCount}/{devices.length} Online Nodes
          </span>
          <span className="ss-status-pill demo">
            <Radio size={13} /> Inactivity Threshold: 300s
          </span>
        </div>
      </div>

      <div className="ss-device-cards">
        {devices.map(d => {
          const zoneName = zoneMap[d.zone_id] ?? d.zone_id;
          const diffSec = Math.round((Date.now() - new Date(d.last_seen).getTime()) / 1000);
          const timeoutSec = d.inactivity_timeout_sec ?? 300;
          const isAlive = d.connected && diffSec < timeoutSec;
          const remainingSec = Math.max(0, timeoutSec - diffSec);
          const agoMin = Math.round(diffSec / 60);

          return (
            <div
              key={d.id}
              id={`device-card-${d.id}`}
              className={`ss-device-full-card ${isAlive ? '' : 'offline'}`}
            >
              <div className="ss-dfc-header">
                <div className="ss-dfc-icon">
                  <Cpu size={22} />
                </div>
                <div className="ss-dfc-title">
                  <div className="ss-dfc-name">{d.name}</div>
                  <div className="ss-dfc-id ss-mono">{d.id}</div>
                </div>
                <div className={`ss-conn-badge ${isAlive ? '' : 'offline'}`}>
                  {isAlive ? <Wifi size={13} /> : <WifiOff size={13} />}
                  {isAlive ? 'Active Telemetry' : 'Inactive / Offline'}
                </div>
              </div>

              {/* ThingsBoard Heartbeat Status Bar */}
              <div className="ss-inactivity-status-box">
                <div className="ss-inactivity-header">
                  <span className="ss-inactivity-title">Heartbeat State:</span>
                  <span className={`ss-inactivity-val ${isAlive ? 'alive' : 'stale'}`}>
                    {isAlive
                      ? `Active (Inactivity grace: ${remainingSec}s remaining)`
                      : `Inactive (Timeout ${timeoutSec}s exceeded by ${diffSec - timeoutSec}s)`}
                  </span>
                </div>
                <div className="ss-inactivity-bar-bg">
                  <div
                    className={`ss-inactivity-bar-fill ${isAlive ? 'ok' : 'crit'}`}
                    style={{ width: `${Math.min(100, Math.max(5, (remainingSec / timeoutSec) * 100))}%` }}
                  />
                </div>
              </div>

              <div className="ss-dfc-fields">
                <div className="ss-dfc-field">
                  <span className="ss-dfc-key">Assigned Silo</span>
                  <button
                    className="ss-dfc-val ss-link-btn"
                    onClick={() => navigate(`/zones?zone=${d.zone_id}`)}
                    title="View Silo Telemetry"
                  >
                    <MapPin size={12} /> {zoneName} <ArrowRight size={11} />
                  </button>
                </div>
                <div className="ss-dfc-field">
                  <span className="ss-dfc-key">Firmware Version</span>
                  <span className="ss-dfc-val ss-mono">{d.firmware_version}</span>
                </div>
                <div className="ss-dfc-field">
                  <Clock size={13} />
                  <span className="ss-dfc-key">Last Activity</span>
                  <span className="ss-dfc-val">
                    {new Date(d.last_seen).toLocaleTimeString()}{' '}
                    <span className="ss-dfc-ago">
                      ({agoMin < 1 ? '<1 min ago' : `${agoMin}m ago`})
                    </span>
                  </span>
                </div>
                <div className="ss-dfc-field">
                  <ShieldCheck size={13} />
                  <span className="ss-dfc-key">Transport Mode</span>
                  <span className="ss-dfc-val ss-source-note">
                    {isAlive ? 'ESP32 Wi-Fi HTTP Post (Active session)' : 'Session timed out (Disconnected)'}
                  </span>
                </div>
              </div>

              <div className="ss-dfc-sensors">
                <div className="ss-dfc-sensors-title">Sensor Inventory & Health</div>
                {d.sensors.map(s => (
                  <div key={s.type} className={`ss-sensor-row status-${s.status}`}>
                    <span className={`ss-sensor-dot status-${s.status}`} />
                    <div>
                      <div className="ss-sensor-type">{sensorLabel[s.type] ?? s.type}</div>
                      <div className="ss-sensor-meta">
                        Operational Status: <strong>{s.status === 'not_connected' ? 'NOT CONNECTED (Hardware Unpopulated)' : s.status.toUpperCase()}</strong>
                        {s.last_reading && ` · Last reading: ${new Date(s.last_reading).toLocaleTimeString()}`}
                        {s.status === 'not_connected' && ' · Physical sensor unpopulated (Live telemetry disabled; no fabricated data)'}
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Pin Reference Schematics */}
              {d.sensors.some(s => s.type === 'SCD41') && (
                <div className="ss-pin-ref">
                  <div className="ss-pin-title">SCD41 I2C Wiring (ESP32-WROOM-32)</div>
                  <div className="ss-pin-grid">
                    <span>SDA</span><span className="ss-mono">GPIO 21</span>
                    <span>SCL</span><span className="ss-mono">GPIO 22</span>
                    <span>VCC</span><span className="ss-mono">3.3 V Rail</span>
                    <span>GND</span><span className="ss-mono">Common GND</span>
                  </div>
                </div>
              )}

              {d.sensors.some(s => s.type === 'INMP441') && (
                <div className="ss-pin-ref">
                  <div className="ss-pin-title">INMP441 I2S MEMS Wiring</div>
                  <div className="ss-pin-grid">
                    <span>BCLK / SCK</span><span className="ss-mono">GPIO 26</span>
                    <span>WS / LRCLK</span><span className="ss-mono">GPIO 25</span>
                    <span>SD / DOUT</span><span className="ss-mono">GPIO 33</span>
                    <span>L / R Channel</span><span className="ss-mono">GND (Mono Left)</span>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

