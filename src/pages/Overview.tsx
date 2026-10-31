import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Activity, Radio, Warehouse, ChevronRight, CheckCircle, AlertTriangle } from 'lucide-react';
import { ObservabilityDashboard } from './ObservabilityDashboard';
import type { EnvironmentalReading, Alert, Zone, Device } from '../types';

interface Props {
  readings: EnvironmentalReading[];
  alerts: Alert[];
  zones: Zone[];
  devices?: Device[];
  onReload?: () => Promise<void>;
}

export function Overview({ readings: _readings, alerts, zones, devices = [], onReload }: Props) {
  const navigate = useNavigate();
  const [viewMode, setViewMode] = useState<'observability' | 'facility'>('observability');

  const zoneHealth = (h: Zone['health']) => {
    const map = { healthy: 'ok', warning: 'warn', critical: 'crit', unknown: 'unknown' } as const;
    return map[h];
  };

  return (
    <div className="ss-page" style={{ maxWidth: '100%' }}>
      {/* View Switcher Toolbar Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, flexWrap: 'wrap', gap: 10 }}>
        <div>
          <h1 className="ss-page-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Radio size={20} style={{ color: '#38bdf8' }} />
            SealSense Observability Console
          </h1>
          <div className="ss-page-subtitle">
            Dense, live grain-storage observability console inspired by Grafana Node Exporter
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: '#101424', padding: '3px', borderRadius: '6px', border: '1px solid #1f263d' }}>
          <button
            id="view-mode-observability-btn"
            className={`gf-btn ${viewMode === 'observability' ? 'active' : ''}`}
            onClick={() => setViewMode('observability')}
          >
            <Activity size={13} />
            <span>Live Observability Grid</span>
          </button>
          <button
            id="view-mode-facility-btn"
            className={`gf-btn ${viewMode === 'facility' ? 'active' : ''}`}
            onClick={() => setViewMode('facility')}
          >
            <Warehouse size={13} />
            <span>Facility Storage Zones ({zones.length})</span>
          </button>
        </div>
      </div>

      {viewMode === 'observability' ? (
        <ObservabilityDashboard
          alerts={alerts}
          zones={zones}
          devices={devices}
          onReload={onReload}
        />
      ) : (
        /* Storage Zone Health & Facility Drill-Down Section */
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <section className="ss-section">
            <div className="ss-section-header-row">
              <h2 className="ss-section-title">Storage Zone Health & Architecture</h2>
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

          {/* Embedded summary */}
          <ObservabilityDashboard
            alerts={alerts}
            zones={zones}
            devices={devices}
            onReload={onReload}
          />
        </div>
      )}
    </div>
  );
}
