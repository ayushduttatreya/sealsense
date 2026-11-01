import React, { useState } from 'react';
import {
  Thermometer, Droplets, Wind, Mic, Volume2, VolumeX,
  AlertTriangle, PhoneCall, ChevronRight,
  ShieldCheck, Warehouse, HelpCircle
} from 'lucide-react';
import type { LatestTelemetryResponse, Alert } from '../../types';
import { translations, type FarmerLanguage } from '../../lib/farmerTranslations';
import { speakAdvisory, stopSpeaking } from '../../lib/voiceAssistant';

interface Props {
  latestData: LatestTelemetryResponse | null;
  activeAlert: Alert | null;
  lang: FarmerLanguage;
  onOpenAlert: (alert: Alert) => void;
  onNavigateTab: (tab: 'home' | 'storage' | 'alerts' | 'help') => void;
  isBackendOnline: boolean;
}

export const FarmerHome: React.FC<Props> = ({
  latestData,
  activeAlert,
  lang,
  onOpenAlert,
  onNavigateTab,
  isBackendOnline,
}) => {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const t = translations[lang];

  // Derive time greeting
  const hour = new Date().getHours();
  const timeGreeting = hour < 12 ? t.greetingMorning : hour < 17 ? t.greetingAfternoon : t.greetingEvening;

  const reading = latestData?.reading;
  const deviceStatus = latestData?.device_status ?? (isBackendOnline ? 'online' : 'offline');
  const isHardware = latestData?.is_hardware ?? false;
  const ageSeconds = latestData?.age_seconds ?? 0;

  // Determine Overall Health State
  let healthState: 'safe' | 'attention' | 'critical' | 'offline' = 'safe';
  let healthTitle = t.grainSafeTitle;
  let healthDesc = t.grainSafeDesc;

  if (deviceStatus === 'offline' || !isBackendOnline) {
    healthState = 'offline';
    healthTitle = t.grainOfflineTitle;
    healthDesc = t.grainOfflineDesc;
  } else if (activeAlert) {
    if (activeAlert.severity === 'critical') {
      healthState = 'critical';
      healthTitle = t.grainCriticalTitle;
      healthDesc = activeAlert.message || t.grainCriticalDesc;
    } else {
      healthState = 'attention';
      healthTitle = t.grainAttentionTitle;
      healthDesc = activeAlert.message || t.grainAttentionDesc;
    }
  } else if (reading) {
    const co2 = reading.co2_ppm ?? 600;
    const temp = reading.temperature_c ?? 25;
    const rh = reading.relative_humidity_pct ?? 55;

    if (co2 > 1500 || temp > 33 || rh > 75) {
      healthState = 'critical';
      healthTitle = t.grainCriticalTitle;
      healthDesc = t.grainCriticalDesc;
    } else if (co2 > 1000 || temp > 29 || rh > 65) {
      healthState = 'attention';
      healthTitle = t.grainAttentionTitle;
      healthDesc = t.grainAttentionDesc;
    }
  }

  // Plain-language sensor statuses
  const tempVal = reading?.temperature_c != null ? Math.round(reading.temperature_c * 10) / 10 : 25.4;
  const rhVal = reading?.relative_humidity_pct != null ? Math.round(reading.relative_humidity_pct * 10) / 10 : 64.2;
  const co2Val = reading?.co2_ppm != null ? Math.round(reading.co2_ppm) : 820;

  let tempDesc = t.tempNormalDesc;
  if (tempVal > 30) tempDesc = t.tempWarmDesc;
  else if (tempVal < 18) tempDesc = t.tempColdDesc;

  let rhDesc = t.humidityGoodDesc;
  let rhIsCaution = false;
  if (rhVal > 68) {
    rhDesc = t.humidityHighDesc;
    rhIsCaution = true;
  }

  let co2Desc = t.co2NormalDesc;
  let co2IsCaution = false;
  if (co2Val > 1400) {
    co2Desc = t.co2CriticalDesc;
    co2IsCaution = true;
  } else if (co2Val > 1000) {
    co2Desc = t.co2ElevatedDesc;
    co2IsCaution = true;
  }

  const soundDesc = activeAlert?.title.toLowerCase().includes('sound') || activeAlert?.title.toLowerCase().includes('आवाज')
    ? t.soundElevatedDesc
    : t.soundNormalDesc;

  // Spoken advisory script
  const advisorySpeech = lang === 'hi'
    ? `${t.namaste}। ${healthTitle}। साइलो का तापमान ${tempVal} डिग्री सेल्सियस है। हवा की नमी ${rhVal} प्रतिशत है, ध्यान रहे यह हवा की नमी है, दाने की नमी नहीं। कार्बन डाइऑक्साइड ${co2Val} पीपीएम है। ध्वनि स्तर शांत व सामान्य है।`
    : `${t.namaste}. ${healthTitle}. Storage temperature is ${tempVal} degrees Celsius. Storage air relative humidity is ${rhVal} percent, note that this is air moisture, not grain moisture content. Carbon dioxide is ${co2Val} ppm. Sound monitoring is normal.`;

  const handleVoicePlay = () => {
    if (isSpeaking) {
      stopSpeaking();
      setIsSpeaking(false);
    } else {
      setIsSpeaking(true);
      speakAdvisory(
        advisorySpeech,
        lang,
        () => setIsSpeaking(true),
        () => setIsSpeaking(false)
      );
    }
  };

  return (
    <div className="krishi-container">
      {/* Hero Greeting & Status Header */}
      <div className="krishi-hero-header">
        <div>
          <h1 className="krishi-greeting-title">
            <span>{t.namaste}</span>
            <span style={{ fontSize: 20 }}>🙏</span>
          </h1>
          <p className="krishi-greeting-sub">
            {timeGreeting} • Storage Area A (Silo 1)
          </p>
        </div>

        {/* Connectivity Status Chip */}
        <div className={`krishi-conn-chip ${deviceStatus === 'online' ? 'active' : deviceStatus === 'stale' ? 'stale' : 'offline'}`}>
          <span className="krishi-dot" />
          <span>
            {deviceStatus === 'online'
              ? `${t.monitoringActive} (${isHardware ? 'ESP32 Live' : 'Demo'})`
              : deviceStatus === 'stale'
              ? `${t.monitoringStale} (${ageSeconds}s)`
              : t.monitoringOffline}
          </span>
        </div>
      </div>

      {/* Main Monitoring Health Card */}
      <div className={`krishi-health-card ${healthState}`}>
        <div className="krishi-health-header">
          <div className="krishi-health-icon-wrap">
            {healthState === 'safe' && <ShieldCheck size={28} />}
            {healthState === 'attention' && <AlertTriangle size={28} />}
            {healthState === 'critical' && <AlertTriangle size={28} />}
            {healthState === 'offline' && <Warehouse size={28} />}
          </div>
          <div className="krishi-health-info">
            <h2 className="krishi-health-title">{healthTitle}</h2>
            <p className="krishi-health-desc">{healthDesc}</p>
          </div>
        </div>

        <div className="krishi-health-footer">
          <div className="krishi-health-meta">
            <span>{t.lastUpdated}:</span>
            <strong>
              {ageSeconds < 60
                ? `${Math.max(1, ageSeconds)} ${t.secondsAgo}`
                : `${Math.round(ageSeconds / 60)} ${t.minutesAgo}`}
            </strong>
          </div>

          <button
            type="button"
            className={`krishi-btn-voice ${isSpeaking ? 'speaking' : ''}`}
            onClick={handleVoicePlay}
          >
            {isSpeaking ? <VolumeX size={15} /> : <Volume2 size={15} />}
            <span>{isSpeaking ? t.stopAudio : t.listenAudio}</span>
          </button>
        </div>
      </div>

      {/* Active Alert Banner (If Any Alert or Demo Active) */}
      {activeAlert && (
        <div
          className={`krishi-alert-banner ${activeAlert.severity === 'critical' ? 'critical' : ''}`}
          onClick={() => onOpenAlert(activeAlert)}
        >
          <div className="krishi-alert-banner-left">
            <div className="krishi-alert-banner-icon">
              <AlertTriangle size={20} />
            </div>
            <div>
              <div className="krishi-alert-banner-title">{activeAlert.title}</div>
              <div className="krishi-alert-banner-sub">{activeAlert.message}</div>
            </div>
          </div>
          <button type="button" className="krishi-alert-banner-btn">
            {t.inspectStorage}
          </button>
        </div>
      )}

      {/* Environmental Metrics Grid (4 Clean Cards) */}
      <div>
        <h3 className="krishi-section-title">
          {lang === 'hi' ? 'साइलो वातावरण स्थिति' : 'Storage Conditions'}
        </h3>
        <div className="krishi-metrics-grid">
          {/* Temperature */}
          <div className="krishi-metric-card">
            <div className="krishi-metric-top">
              <span className="krishi-metric-label">{t.temperature}</span>
              <div className="krishi-metric-icon temp">
                <Thermometer size={16} />
              </div>
            </div>
            <div className="krishi-metric-val-wrap">
              <span className="krishi-metric-val">{tempVal}</span>
              <span className="krishi-metric-unit">°C</span>
            </div>
            <div className="krishi-metric-explanation">
              {tempDesc}
            </div>
          </div>

          {/* Air Humidity (With explicit NOT grain moisture label) */}
          <div className="krishi-metric-card">
            <div className="krishi-metric-top">
              <span className="krishi-metric-label">{t.airHumidity}</span>
              <div className="krishi-metric-icon humidity">
                <Droplets size={16} />
              </div>
            </div>
            <div className="krishi-metric-val-wrap">
              <span className="krishi-metric-val">{rhVal}</span>
              <span className="krishi-metric-unit">%</span>
            </div>
            <div className={`krishi-metric-explanation ${rhIsCaution ? 'caution' : ''}`}>
              {rhDesc}
            </div>
            <div className="krishi-metric-clarification">
              ℹ️ {t.airHumidityNote}
            </div>
          </div>

          {/* Air Freshness (CO2 ppm) */}
          <div className="krishi-metric-card">
            <div className="krishi-metric-top">
              <span className="krishi-metric-label">{t.airFreshness}</span>
              <div className="krishi-metric-icon co2">
                <Wind size={16} />
              </div>
            </div>
            <div className="krishi-metric-val-wrap">
              <span className="krishi-metric-val">{co2Val}</span>
              <span className="krishi-metric-unit">ppm</span>
            </div>
            <div className={`krishi-metric-explanation ${co2IsCaution ? 'caution' : ''}`}>
              {co2Desc}
            </div>
          </div>

          {/* Sound Monitoring Activity (With explicit acoustic indicator disclaimer) */}
          <div className="krishi-metric-card">
            <div className="krishi-metric-top">
              <span className="krishi-metric-label">{t.soundActivity}</span>
              <div className="krishi-metric-icon sound">
                <Mic size={16} />
              </div>
            </div>
            <div className="krishi-metric-val-wrap">
              <span className="krishi-metric-val" style={{ fontSize: 20 }}>
                {activeAlert?.title.toLowerCase().includes('sound') || activeAlert?.title.toLowerCase().includes('आवाज')
                  ? (lang === 'hi' ? 'सतर्क' : 'Active')
                  : (lang === 'hi' ? 'शांत' : 'Quiet')}
              </span>
            </div>
            <div className="krishi-metric-explanation">
              {soundDesc}
            </div>
            <div className="krishi-metric-clarification">
              ℹ️ {t.soundDisclaimer}
            </div>
          </div>
        </div>
      </div>

      {/* Helpful Actions Section */}
      <div>
        <h3 className="krishi-section-title">
          {lang === 'hi' ? 'त्वरित किसान कार्य' : 'Quick Actions'}
        </h3>
        <div className="krishi-actions-grid">
          <div className="krishi-action-card" onClick={() => onNavigateTab('storage')}>
            <div className="krishi-action-icon">
              <Warehouse size={20} />
            </div>
            <div style={{ flex: 1 }}>
              <div className="krishi-action-title">{t.myStorageTitle}</div>
              <div className="krishi-action-desc">
                {lang === 'hi' ? 'साइलो 1 (गेहूं) व सेंसर विवरण' : 'Silo 1 (Wheat) & Sensor Details'}
              </div>
            </div>
            <ChevronRight size={18} color="#94a3b8" />
          </div>

          <div className="krishi-action-card" onClick={() => onNavigateTab('help')}>
            <div className="krishi-action-icon">
              <HelpCircle size={20} />
            </div>
            <div style={{ flex: 1 }}>
              <div className="krishi-action-title">{t.helpTitle}</div>
              <div className="krishi-action-desc">
                {lang === 'hi' ? 'CO₂ व नमी को समझें' : 'Learn CO₂ & Storage Rules'}
              </div>
            </div>
            <ChevronRight size={18} color="#94a3b8" />
          </div>

          <a
            href="tel:18001801551"
            className="krishi-action-card"
            style={{ textDecoration: 'none' }}
          >
            <div className="krishi-action-icon" style={{ background: '#fef3c7', color: '#b45309' }}>
              <PhoneCall size={20} />
            </div>
            <div style={{ flex: 1 }}>
              <div className="krishi-action-title">
                {lang === 'hi' ? 'किसान कॉल सेंटर' : 'Kisan Call Centre'}
              </div>
              <div className="krishi-action-desc" style={{ color: '#b45309', fontWeight: 600 }}>
                1800-180-1551 (टोल-फ्री)
              </div>
            </div>
            <ChevronRight size={18} color="#94a3b8" />
          </a>
        </div>
      </div>
    </div>
  );
};
