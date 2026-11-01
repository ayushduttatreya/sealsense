import React, { useState } from 'react';
import {
  Warehouse, Cpu, CheckCircle2, AlertCircle, TrendingUp,
  Thermometer, Droplets, ShieldCheck
} from 'lucide-react';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';
import type { Zone, Device, EnvironmentalReading } from '../../types';
import { translations, type FarmerLanguage } from '../../lib/farmerTranslations';

interface Props {
  zones: Zone[];
  devices: Device[];
  historyReadings: EnvironmentalReading[];
  lang: FarmerLanguage;
  isBackendOnline: boolean;
}

export const FarmerStorage: React.FC<Props> = ({
  zones,
  devices,
  historyReadings,
  lang,
  isBackendOnline,
}) => {
  const t = translations[lang];
  const [selectedZoneId, setSelectedZoneId] = useState<string>('zone-a');

  // Find selected zone or default to first
  const activeZone = zones.find(z => z.id === selectedZoneId) || zones[0] || {
    id: 'zone-a',
    name: 'Storage Area A',
    description: 'Grain Silo 1 — Premium Sharbati Wheat',
    device_ids: ['esp32-zone-a-01'],
    health: 'healthy' as const,
  };

  // Find devices associated with active zone
  const zoneDevices = devices.filter(d => activeZone.device_ids?.includes(d.id) || d.zone_id === activeZone.id);
  const mainDevice = zoneDevices[0] || {
    id: 'esp32-zone-a-01',
    name: 'ESP32 Grain Storage Node A1',
    connected: isBackendOnline,
    firmware_version: 'v1.4.2-live',
    sensors: [
      { type: 'SCD41' as const, status: 'ok' as const },
      { type: 'INMP441' as const, status: 'ok' as const },
      { type: 'BUZZER' as const, status: 'unavailable' as const },
    ],
  };

  // Prepare trend data for simple trend graph
  const chartData = (historyReadings.length > 0
    ? historyReadings.slice(-20)
    : [
        { timestamp: '10:00', temperature_c: 24.8, relative_humidity_pct: 62 },
        { timestamp: '10:15', temperature_c: 25.0, relative_humidity_pct: 63 },
        { timestamp: '10:30', temperature_c: 25.2, relative_humidity_pct: 64 },
        { timestamp: '10:45', temperature_c: 25.4, relative_humidity_pct: 64.2 },
      ]
  ).map(r => ({
    time: typeof r.timestamp === 'string' && r.timestamp.includes('T')
      ? new Date(r.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      : r.timestamp,
    temp: r.temperature_c != null ? Math.round(r.temperature_c * 10) / 10 : 25.4,
    humidity: r.relative_humidity_pct != null ? Math.round(r.relative_humidity_pct * 10) / 10 : 64,
  }));

  return (
    <div className="krishi-container">
      {/* Page Header */}
      <div>
        <h2 className="krishi-greeting-title">
          <Warehouse size={22} color="#1b4d3e" />
          <span>{t.myStorageTitle}</span>
        </h2>
        <p className="krishi-greeting-sub">
          {lang === 'hi' ? 'भंडारण साइलो व सेंसर उपकरण स्थिति' : 'Grain Silo Equipment & Environmental Stability'}
        </p>
      </div>

      {/* Silo / Storage Area Switcher */}
      <div className="krishi-storage-selector">
        <button
          type="button"
          className={`krishi-silo-pill ${selectedZoneId === 'zone-a' ? 'active' : ''}`}
          onClick={() => setSelectedZoneId('zone-a')}
        >
          <Warehouse size={16} />
          <span>{t.silo1Wheat}</span>
        </button>
        <button
          type="button"
          className={`krishi-silo-pill ${selectedZoneId === 'zone-b' ? 'active' : ''}`}
          onClick={() => setSelectedZoneId('zone-b')}
        >
          <Warehouse size={16} />
          <span>{t.silo2Barley}</span>
        </button>
      </div>

      {/* Storage Area Summary Card */}
      <div style={{
        background: '#ffffff',
        border: '1.5px solid var(--krishi-card-border)',
        borderRadius: 'var(--krishi-radius-card)',
        padding: 16,
        boxShadow: 'var(--krishi-shadow)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <h3 style={{ fontSize: 16, fontWeight: 700, color: '#1e293b', margin: 0 }}>
            {activeZone.name}
          </h3>
          <span style={{
            fontSize: 11,
            fontWeight: 700,
            background: activeZone.health === 'critical' ? '#fee2e2' : '#dcfce7',
            color: activeZone.health === 'critical' ? '#b91c1c' : '#15803d',
            padding: '3px 8px',
            borderRadius: 6
          }}>
            {activeZone.health === 'critical' ? (lang === 'hi' ? 'सतर्कता' : 'Attention') : (lang === 'hi' ? 'सुरक्षित' : 'Healthy')}
          </span>
        </div>
        <p style={{ fontSize: 13, color: '#475569', margin: '0 0 12px 0' }}>
          {activeZone.description || (lang === 'hi' ? 'प्राथमिक अनाज भंडारण साइलो' : 'Primary grain storage silo')}
        </p>

        {/* Live Equipment Status List */}
        <h4 style={{ fontSize: 13, fontWeight: 700, color: '#1b4d3e', margin: '0 0 8px 0' }}>
          {t.hardwareStatus}
        </h4>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {/* Main ESP32 Hub */}
          <div className="krishi-sensor-status-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <Cpu size={18} color="#1b4d3e" />
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: '#1e293b' }}>
                  {mainDevice.name}
                </div>
                <div style={{ fontSize: 11, color: '#64748b' }}>
                  {mainDevice.connected ? t.monitoringActive : t.monitoringOffline} • USB Serial Bridge
                </div>
              </div>
            </div>
            {mainDevice.connected ? (
              <CheckCircle2 size={18} color="#16a34a" />
            ) : (
              <AlertCircle size={18} color="#ef4444" />
            )}
          </div>

          {/* SCD41 Sensor */}
          <div className="krishi-sensor-status-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <Thermometer size={18} color="#0284c7" />
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: '#1e293b' }}>
                  SCD41 Environmental Sensor
                </div>
                <div style={{ fontSize: 11, color: '#64748b' }}>
                  {lang === 'hi' ? 'CO₂, तापमान व हवा नमी सेंसर चालू है' : 'CO₂, temperature & humidity active'}
                </div>
              </div>
            </div>
            <CheckCircle2 size={18} color="#16a34a" />
          </div>

          {/* INMP441 Microphone */}
          <div className="krishi-sensor-status-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <Droplets size={18} color="#7c3aed" />
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: '#1e293b' }}>
                  INMP441 Acoustic Listening Sensor
                </div>
                <div style={{ fontSize: 11, color: '#64748b' }}>
                  {lang === 'hi' ? 'ध्वनि निगरानी सेंसर सक्रिय है' : 'Acoustic monitoring sensor active'}
                </div>
              </div>
            </div>
            <CheckCircle2 size={18} color="#16a34a" />
          </div>
        </div>
      </div>

      {/* Simple 24h Trend Graph */}
      <div style={{
        background: '#ffffff',
        border: '1.5px solid var(--krishi-card-border)',
        borderRadius: 'var(--krishi-radius-card)',
        padding: 16,
        boxShadow: 'var(--krishi-shadow)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <div>
            <h3 style={{ fontSize: 15, fontWeight: 700, color: '#1e293b', margin: '0 0 2px 0', display: 'flex', alignItems: 'center', gap: 6 }}>
              <TrendingUp size={18} color="#1b4d3e" />
              <span>{t.historicalTrend24h}</span>
            </h3>
            <p style={{ fontSize: 11, color: '#64748b', margin: 0 }}>
              {lang === 'hi' ? 'तापमान व हवा की नमी में स्थिरता' : 'Stability of temperature & air humidity'}
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 11, fontWeight: 600 }}>
            <span style={{ color: '#16a34a', display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#16a34a', display: 'inline-block' }} />
              {t.temperature} (°C)
            </span>
            <span style={{ color: '#0284c7', display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#0284c7', display: 'inline-block' }} />
              {t.airHumidity} (%)
            </span>
          </div>
        </div>

        <div style={{ height: 200, width: '100%' }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 8, right: 12, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="time" stroke="#94a3b8" fontSize={10} tickLine={false} />
              <YAxis stroke="#94a3b8" fontSize={10} tickLine={false} domain={['auto', 'auto']} />
              <Tooltip
                contentStyle={{
                  background: '#ffffff',
                  border: '1px solid #cbd5e1',
                  borderRadius: 8,
                  fontSize: 11,
                  boxShadow: '0 2px 8px rgba(0,0,0,0.08)'
                }}
              />
              <Line type="monotone" dataKey="temp" stroke="#16a34a" strokeWidth={2.5} dot={false} />
              <Line type="monotone" dataKey="humidity" stroke="#0284c7" strokeWidth={2.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Safe Grain Storage Rules */}
      <div style={{
        background: '#f8fafc',
        border: '1px solid #e2e8f0',
        borderRadius: 'var(--krishi-radius-card)',
        padding: 16
      }}>
        <h4 style={{ fontSize: 14, fontWeight: 700, color: '#1e293b', margin: '0 0 10px 0', display: 'flex', alignItems: 'center', gap: 6 }}>
          <ShieldCheck size={18} color="#1b4d3e" />
          <span>{lang === 'hi' ? 'सुरक्षित अनाज भंडारण नियम' : 'Safe Storage Rules'}</span>
        </h4>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10 }}>
          <div style={{ background: '#ffffff', padding: 10, borderRadius: 8, border: '1px solid #e2e8f0' }}>
            <div style={{ fontSize: 11, color: '#64748b' }}>{lang === 'hi' ? 'सुरक्षित तापमान' : 'Safe Temperature'}</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: '#16a34a' }}>&lt; 28 °C</div>
            <div style={{ fontSize: 10, color: '#94a3b8' }}>{lang === 'hi' ? 'गर्मी से दाना नहीं तपता' : 'Prevents thermal spoilage'}</div>
          </div>
          <div style={{ background: '#ffffff', padding: 10, borderRadius: 8, border: '1px solid #e2e8f0' }}>
            <div style={{ fontSize: 11, color: '#64748b' }}>{lang === 'hi' ? 'सुरक्षित हवा नमी' : 'Safe Air Moisture'}</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: '#0284c7' }}>&lt; 65 %</div>
            <div style={{ fontSize: 10, color: '#94a3b8' }}>{lang === 'hi' ? 'फफूंद से बचाव' : 'Prevents mould formation'}</div>
          </div>
          <div style={{ background: '#ffffff', padding: 10, borderRadius: 8, border: '1px solid #e2e8f0' }}>
            <div style={{ fontSize: 11, color: '#64748b' }}>{lang === 'hi' ? 'ताज़ा हवा CO₂' : 'Fresh Air CO₂'}</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: '#d97706' }}>&lt; 1,000 ppm</div>
            <div style={{ fontSize: 10, color: '#94a3b8' }}>{lang === 'hi' ? 'अनाज शांत व सुप्त' : 'Normal grain dormancy'}</div>
          </div>
          <div style={{ background: '#ffffff', padding: 10, borderRadius: 8, border: '1px solid #e2e8f0' }}>
            <div style={{ fontSize: 11, color: '#64748b' }}>{lang === 'hi' ? 'ध्वनि निगरानी' : 'Acoustic Activity'}</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: '#7c3aed' }}>{lang === 'hi' ? 'शांत' : 'Quiet'}</div>
            <div style={{ fontSize: 10, color: '#94a3b8' }}>{lang === 'hi' ? 'सामान्य पृष्ठभूमि शोर' : 'Normal ambient baseline'}</div>
          </div>
        </div>
      </div>
    </div>
  );
};
