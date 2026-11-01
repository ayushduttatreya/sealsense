import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  Home, Warehouse, Bell, HelpCircle, ArrowLeftRight,
  Sparkles, RotateCcw
} from 'lucide-react';
import { useObservabilityData } from '../../hooks/useApi';
import type { Alert, Zone, Device } from '../../types';
import { translations, type FarmerLanguage } from '../../lib/farmerTranslations';
import { FarmerHome } from './FarmerHome';
import { FarmerStorage } from './FarmerStorage';
import { FarmerAlerts } from './FarmerAlerts';
import { FarmerHelp } from './FarmerHelp';
import { FarmerAlertDetailModal } from './FarmerAlertDetailModal';
import { speakAdvisory, stopSpeaking } from '../../lib/voiceAssistant';
import './farmer.css';

export const FarmerApp: React.FC = () => {
  const [lang, setLang] = useState<FarmerLanguage>('hi');
  const [activeTab, setActiveTab] = useState<'home' | 'storage' | 'alerts' | 'help'>('home');
  const [selectedAlertForModal, setSelectedAlertForModal] = useState<Alert | null>(null);

  // Simulated Alert State for Judges Demonstration (Isolated from physical database)
  const [demoAlertActive, setDemoAlertActive] = useState<boolean>(false);
  const [demoAlertInspected, setDemoAlertInspected] = useState<boolean>(false);
  const [demoInspectionNotes, setDemoInspectionNotes] = useState<string>('');

  // Live Telemetry from underlying SealSense backend
  const {
    latest,
    history,
    backendOnline,
  } = useObservabilityData('zone-a', 'esp32-zone-a-01', '1h', 'all');

  // Load backend alerts, devices, zones if available
  const [realAlerts, setRealAlerts] = useState<Alert[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [zones, setZones] = useState<Zone[]>([]);

  const fetchAuxData = useCallback(async () => {
    try {
      const [resAlerts, resDevices, resZones] = await Promise.all([
        fetch('http://localhost:8000/api/alerts?limit=50').then(r => r.ok ? r.json() : []).catch(() => []),
        fetch('http://localhost:8000/api/devices').then(r => r.ok ? r.json() : []).catch(() => []),
        fetch('http://localhost:8000/api/zones').then(r => r.ok ? r.json() : []).catch(() => []),
      ]);
      setRealAlerts(resAlerts);
      setDevices(resDevices);
      setZones(resZones);
    } catch {
      // Backend unavailable; graceful fallback
    }
  }, []);

  useEffect(() => {
    void fetchAuxData();
    const interval = setInterval(fetchAuxData, 6000);
    return () => clearInterval(interval);
  }, [fetchAuxData]);

  // Create isolated demo alert object when triggered
  const simulatedDemoAlert: Alert | null = demoAlertActive
    ? {
        id: 'demo-acoustic-warning-01',
        timestamp: new Date().toISOString(),
        zone_id: 'zone-a',
        device_id: 'esp32-zone-a-01',
        severity: 'warning',
        category: 'acoustic',
        title: lang === 'hi' ? 'अनाज साइलो में असामान्य आवाज सुनी गई' : 'Unusual sound activity noticed in Storage Area A',
        message: lang === 'hi'
          ? 'सेंसर ने पृष्ठभूमि शोर से अलग ध्वनि पैटर्न दर्ज किया है। यह साइलो के संचालन, हवा के दबाव या गतिविधि के कारण हो सकता है। कृपया भंडारण क्षेत्र का निरीक्षण करें।'
          : 'The monitoring system recorded a sound pattern that differs from recent background activity. This may have several causes. Please inspect the area.',
        triggered_by: ['inmp441_acoustic_sensor'],
        acknowledged: demoAlertInspected,
        acknowledged_at: demoAlertInspected ? new Date().toISOString() : undefined,
        acknowledged_by: demoAlertInspected ? 'Kisan Operator' : undefined,
        inspection_notes: demoInspectionNotes,
        cleared: false,
        source: 'SIMULATED',
      }
    : null;

  // Combine real alerts and demo alert
  const combinedAlerts: Alert[] = simulatedDemoAlert
    ? [simulatedDemoAlert, ...realAlerts.filter(a => a.id !== simulatedDemoAlert.id)]
    : realAlerts;

  const t = translations[lang];

  // Demo Trigger Handler
  const handleTriggerDemo = () => {
    setDemoAlertActive(true);
    setDemoAlertInspected(false);
    setDemoInspectionNotes('');

    // Trigger voice alert read-out if browser permits
    const speech = lang === 'hi'
      ? 'सावधान! साइलो 1 में असामान्य ध्वनि सुनी गई है। कृपया भंडारण का निरीक्षण करें।'
      : 'Attention! Unusual sound pattern recorded in Silo 1. Please inspect the storage area.';
    speakAdvisory(speech, lang);
  };

  const handleResetDemo = () => {
    stopSpeaking();
    setDemoAlertActive(false);
    setDemoAlertInspected(false);
    setDemoInspectionNotes('');
    if (selectedAlertForModal?.id === 'demo-acoustic-warning-01') {
      setSelectedAlertForModal(null);
    }
  };

  const handleMarkInspected = (alertId: string, notes: string, inspector: string) => {
    if (alertId === 'demo-acoustic-warning-01') {
      setDemoAlertInspected(true);
      setDemoInspectionNotes(notes);
      return;
    }

    // If real alert, send inspection / acknowledge to backend API
    fetch(`http://localhost:8000/api/alerts/${alertId}/acknowledge`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user: inspector, notes }),
    }).catch(err => console.error('Error acknowledging alert:', err));

    setRealAlerts(prev =>
      prev.map(a =>
        a.id === alertId
          ? { ...a, acknowledged: true, acknowledged_by: inspector, inspection_notes: notes }
          : a
      )
    );
  };

  const activeAlertCount = combinedAlerts.filter(a => !a.acknowledged && !a.cleared).length;
  const primaryActiveAlert = combinedAlerts.find(a => !a.acknowledged && !a.cleared) || null;

  return (
    <div className="krishi-app">
      {/* ─── Top Navigation Bar ────────────────────────────────────────── */}
      <header className="krishi-topbar">
        <div className="krishi-topbar-inner">
          <Link to="/farmer" className="krishi-brand" onClick={() => setActiveTab('home')}>
            <div className="krishi-brand-icon">
              <Warehouse size={22} />
            </div>
            <div>
              <div className="krishi-brand-title">{t.appName}</div>
              <div className="krishi-brand-sub">{t.appSubtitle}</div>
            </div>
          </Link>

          <div className="krishi-topbar-actions">
            {/* Language Toggle */}
            <div className="krishi-lang-toggle">
              <button
                type="button"
                className={`krishi-lang-opt ${lang === 'hi' ? 'active' : ''}`}
                onClick={() => setLang('hi')}
                title="हिंदी में देखें"
              >
                हिं
              </button>
              <button
                type="button"
                className={`krishi-lang-opt ${lang === 'en' ? 'active' : ''}`}
                onClick={() => setLang('en')}
                title="View in English"
              >
                EN
              </button>
            </div>

            {/* Switch to Technical Console */}
            <Link to="/" className="krishi-switch-btn" title="Open Technical Observability Dashboard">
              <ArrowLeftRight size={14} />
              <span>{t.switchTechDashboard}</span>
            </Link>
          </div>
        </div>
      </header>

      {/* ─── Mandatory Demo Control Strip for Judges ───────────────────── */}
      <div className="krishi-demo-strip">
        <div className="krishi-demo-strip-inner">
          <div className="krishi-demo-strip-left">
            <span className="krishi-demo-badge">JUDGE DEMO</span>
            <span>
              {demoAlertActive ? t.demoBannerText : t.demoAlertPrompt}
            </span>
          </div>
          <div className="krishi-demo-actions">
            {!demoAlertActive ? (
              <button
                type="button"
                className="krishi-btn-demo-trigger"
                onClick={handleTriggerDemo}
              >
                <Sparkles size={13} />
                <span>{t.triggerDemoBtn}</span>
              </button>
            ) : (
              <button
                type="button"
                className="krishi-btn-demo-reset"
                onClick={handleResetDemo}
              >
                <RotateCcw size={13} />
                <span>{t.resetDemoBtn}</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ─── Main View Routing ─────────────────────────────────────────── */}
      <main style={{ flex: 1 }}>
        {activeTab === 'home' && (
          <FarmerHome
            latestData={latest}
            activeAlert={primaryActiveAlert}
            lang={lang}
            onOpenAlert={alert => setSelectedAlertForModal(alert)}
            onNavigateTab={tab => setActiveTab(tab)}
            isBackendOnline={backendOnline}
          />
        )}

        {activeTab === 'storage' && (
          <FarmerStorage
            zones={zones}
            devices={devices}
            historyReadings={history}
            lang={lang}
            isBackendOnline={backendOnline}
          />
        )}

        {activeTab === 'alerts' && (
          <FarmerAlerts
            alerts={combinedAlerts}
            lang={lang}
            onOpenAlert={alert => setSelectedAlertForModal(alert)}
            onTriggerDemo={handleTriggerDemo}
            hasDemoAlert={demoAlertActive}
          />
        )}

        {activeTab === 'help' && (
          <FarmerHelp
            lang={lang}
            onSetLang={newLang => setLang(newLang)}
          />
        )}
      </main>

      {/* ─── Alert Detail Modal (Investigation Workflow) ───────────────── */}
      <FarmerAlertDetailModal
        alert={selectedAlertForModal}
        isOpen={!!selectedAlertForModal}
        onClose={() => setSelectedAlertForModal(null)}
        lang={lang}
        onMarkInspected={handleMarkInspected}
      />

      {/* ─── Mobile-First Bottom Navigation Bar ────────────────────────── */}
      <nav className="krishi-bottom-nav">
        <button
          type="button"
          className={`krishi-nav-btn ${activeTab === 'home' ? 'active' : ''}`}
          onClick={() => setActiveTab('home')}
        >
          <Home size={20} />
          <span>{t.navHome}</span>
        </button>

        <button
          type="button"
          className={`krishi-nav-btn ${activeTab === 'storage' ? 'active' : ''}`}
          onClick={() => setActiveTab('storage')}
        >
          <Warehouse size={20} />
          <span>{t.navStorage}</span>
        </button>

        <button
          type="button"
          className={`krishi-nav-btn ${activeTab === 'alerts' ? 'active' : ''}`}
          onClick={() => setActiveTab('alerts')}
        >
          <Bell size={20} />
          <span>{t.navAlerts}</span>
          {activeAlertCount > 0 && <span className="krishi-nav-badge" />}
        </button>

        <button
          type="button"
          className={`krishi-nav-btn ${activeTab === 'help' ? 'active' : ''}`}
          onClick={() => setActiveTab('help')}
        >
          <HelpCircle size={20} />
          <span>{t.navHelp}</span>
        </button>
      </nav>
    </div>
  );
};
export default FarmerApp;
