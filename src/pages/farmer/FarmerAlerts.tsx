import React, { useState } from 'react';
import {
  Bell, CheckCircle2, Volume2, VolumeX,
  AlertTriangle, Sparkles, Clock, MapPin
} from 'lucide-react';
import type { Alert } from '../../types';
import { translations, type FarmerLanguage } from '../../lib/farmerTranslations';
import { speakAdvisory, stopSpeaking } from '../../lib/voiceAssistant';

interface Props {
  alerts: Alert[];
  lang: FarmerLanguage;
  onOpenAlert: (alert: Alert) => void;
  onTriggerDemo: () => void;
  hasDemoAlert: boolean;
}

export const FarmerAlerts: React.FC<Props> = ({
  alerts,
  lang,
  onOpenAlert,
  onTriggerDemo,
  hasDemoAlert,
}) => {
  const t = translations[lang];
  const [filter, setFilter] = useState<'all' | 'active' | 'inspected'>('all');
  const [speakingId, setSpeakingId] = useState<string | null>(null);

  const filteredAlerts = alerts.filter(a => {
    if (filter === 'active') return !a.acknowledged && !a.cleared;
    if (filter === 'inspected') return a.acknowledged || a.cleared;
    return true;
  });

  const handleVoicePlay = (alert: Alert, e: React.MouseEvent) => {
    e.stopPropagation();
    if (speakingId === alert.id) {
      stopSpeaking();
      setSpeakingId(null);
    } else {
      setSpeakingId(alert.id);
      const speech = lang === 'hi'
        ? `${alert.title}। ${alert.message}। सलाह: साइलो का भौतिक निरीक्षण करें। बिना पुष्टि कीटनाशक न डालें।`
        : `${alert.title}. ${alert.message}. Recommended action: conduct a physical inspection of storage.`;
      speakAdvisory(
        speech,
        lang,
        () => setSpeakingId(alert.id),
        () => setSpeakingId(null)
      );
    }
  };

  return (
    <div className="krishi-container">
      {/* Header */}
      <div>
        <h2 className="krishi-greeting-title">
          <Bell size={22} color="#1b4d3e" />
          <span>{t.alertsTitle}</span>
        </h2>
        <p className="krishi-greeting-sub">
          {lang === 'hi' ? 'भंडारण सुरक्षा सूचनाएँ व अनुशंसित किसान सलाह' : 'Storage Condition Warnings & Recommended Actions'}
        </p>
      </div>

      {/* Filter Tabs */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, overflowX: 'auto', paddingBottom: 4 }}>
        <button
          type="button"
          className={`krishi-lang-opt ${filter === 'all' ? 'active' : ''}`}
          style={{ padding: '6px 14px', borderRadius: 999, border: '1px solid #cbd5e1' }}
          onClick={() => setFilter('all')}
        >
          {lang === 'hi' ? 'सभी सूचनाएँ' : 'All Alerts'} ({alerts.length})
        </button>
        <button
          type="button"
          className={`krishi-lang-opt ${filter === 'active' ? 'active' : ''}`}
          style={{ padding: '6px 14px', borderRadius: 999, border: '1px solid #cbd5e1' }}
          onClick={() => setFilter('active')}
        >
          {lang === 'hi' ? 'सक्रिय' : 'Active'} ({alerts.filter(a => !a.acknowledged && !a.cleared).length})
        </button>
        <button
          type="button"
          className={`krishi-lang-opt ${filter === 'inspected' ? 'active' : ''}`}
          style={{ padding: '6px 14px', borderRadius: 999, border: '1px solid #cbd5e1' }}
          onClick={() => setFilter('inspected')}
        >
          {lang === 'hi' ? 'जाँचे गए' : 'Inspected'} ({alerts.filter(a => a.acknowledged || a.cleared).length})
        </button>
      </div>

      {/* Alerts List */}
      {filteredAlerts.length > 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {filteredAlerts.map(alert => {
            const isDemo = alert.source === 'SIMULATED' || alert.id.startsWith('demo-');
            const isCritical = alert.severity === 'critical';
            const isInspected = alert.acknowledged || alert.cleared;

            return (
              <div
                key={alert.id}
                className="krishi-alert-card"
                onClick={() => onOpenAlert(alert)}
              >
                {/* Top Row: Severity & Location & Demo Badge */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8, flexWrap: 'wrap', gap: 6 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span className={`krishi-alert-chip ${isCritical ? 'critical' : 'warning'}`}>
                      {isCritical
                        ? (lang === 'hi' ? 'अति महत्वपूर्ण' : 'Urgent Warning')
                        : (lang === 'hi' ? 'ध्यान दें' : 'Attention Advisory')}
                    </span>
                    {isDemo && (
                      <span className="krishi-demo-badge">SIMULATED DEMO</span>
                    )}
                    <span style={{ fontSize: 11, color: '#64748b', display: 'flex', alignItems: 'center', gap: 4 }}>
                      <MapPin size={12} />
                      {alert.zone_id}
                    </span>
                  </div>

                  <span style={{ fontSize: 11, color: '#94a3b8', display: 'flex', alignItems: 'center', gap: 4 }}>
                    <Clock size={12} />
                    {new Date(alert.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>

                {/* Title & Message */}
                <h3 style={{ fontSize: 15, fontWeight: 700, color: '#1e293b', margin: '0 0 6px 0' }}>
                  {alert.title}
                </h3>
                <p style={{ fontSize: 13, color: '#475569', margin: '0 0 12px 0', lineHeight: 1.45 }}>
                  {alert.message}
                </p>

                {/* Inspection Checklist Preview */}
                <div style={{
                  background: '#f8fafc',
                  border: '1px solid #e2e8f0',
                  borderRadius: 8,
                  padding: '8px 12px',
                  marginBottom: 12,
                  fontSize: 11,
                  color: '#475569'
                }}>
                  <strong>{t.inspectionChecklist}:</strong>{' '}
                  {t.alertStep1}
                </div>

                {/* Footer Actions */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderTop: '1px solid #f1f5f9', paddingTop: 10, flexWrap: 'wrap', gap: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11 }}>
                    {isInspected ? (
                      <span style={{ color: '#15803d', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4 }}>
                        <CheckCircle2 size={14} />
                        {lang === 'hi' ? 'निरीक्षण पूर्ण' : 'Inspected & Confirmed'}
                      </span>
                    ) : (
                      <span style={{ color: '#b45309', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4 }}>
                        <AlertTriangle size={14} />
                        {lang === 'hi' ? 'निरीक्षण लंबित' : 'Inspection Pending'}
                      </span>
                    )}
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <button
                      type="button"
                      className={`krishi-btn-voice ${speakingId === alert.id ? 'speaking' : ''}`}
                      onClick={e => handleVoicePlay(alert, e)}
                    >
                      {speakingId === alert.id ? <VolumeX size={14} /> : <Volume2 size={14} />}
                      <span>{speakingId === alert.id ? t.stopAudio : t.listenAudio}</span>
                    </button>
                    <button
                      type="button"
                      className="krishi-btn-primary"
                      style={{ padding: '6px 12px', fontSize: 12 }}
                      onClick={() => onOpenAlert(alert)}
                    >
                      {isInspected ? (lang === 'hi' ? 'विवरण देखें' : 'View Notes') : t.inspectStorage}
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* Empty State */
        <div style={{
          background: '#ffffff',
          border: '1.5px solid var(--krishi-card-border)',
          borderRadius: 'var(--krishi-radius-card)',
          padding: '36px 20px',
          textAlign: 'center',
          boxShadow: 'var(--krishi-shadow)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 12
        }}>
          <div style={{
            width: 56,
            height: 56,
            borderRadius: 18,
            background: '#dcfce7',
            color: '#15803d',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <CheckCircle2 size={32} />
          </div>
          <div>
            <h3 style={{ fontSize: 17, fontWeight: 700, color: '#1e293b', margin: '0 0 6px 0' }}>
              {t.noActiveAlerts}
            </h3>
            <p style={{ fontSize: 13, color: '#64748b', margin: 0, maxWidth: 360, lineHeight: 1.45 }}>
              {t.allClearMessage}
            </p>
          </div>

          {!hasDemoAlert && (
            <button
              type="button"
              className="krishi-btn-demo-trigger"
              style={{ marginTop: 8, padding: '8px 16px', fontSize: 12 }}
              onClick={onTriggerDemo}
            >
              <Sparkles size={14} />
              <span>{t.triggerDemoBtn} (Judge Demonstration)</span>
            </button>
          )}
        </div>
      )}
    </div>
  );
};
