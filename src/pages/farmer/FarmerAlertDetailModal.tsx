import React, { useState } from 'react';
import { Volume2, VolumeX, CheckCircle2, AlertTriangle, X, ShieldAlert } from 'lucide-react';
import type { Alert } from '../../types';
import { translations, type FarmerLanguage } from '../../lib/farmerTranslations';
import { speakAdvisory, stopSpeaking } from '../../lib/voiceAssistant';

interface Props {
  alert: Alert | null;
  isOpen: boolean;
  onClose: () => void;
  lang: FarmerLanguage;
  onMarkInspected: (alertId: string, notes: string, inspector: string) => void;
}

export const FarmerAlertDetailModal: React.FC<Props> = ({
  alert,
  isOpen,
  onClose,
  lang,
  onMarkInspected,
}) => {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [inspectorName, setInspectorName] = useState('Kisan Operator');
  const [inspectionNotes, setInspectionNotes] = useState('');
  const [submitted, setSubmitted] = useState(false);

  if (!isOpen || !alert) return null;

  const t = translations[lang];
  const isDemo = alert.source === 'SIMULATED' || alert.id.startsWith('demo-');

  const speechText = lang === 'hi'
    ? `${alert.title}। ${alert.message}। सलाह: साइलो का ढक्कन खोलें, भीतरी नमी देखें, और दाने का तापमान मापें। बिना निरीक्षण कीटनाशक का प्रयोग न करें।`
    : `${alert.title}. ${alert.message}. Recommended inspection: check grain temperature and inspect silo roof for condensation. Do not apply pesticides without physical inspection.`;

  const handleVoice = () => {
    if (isSpeaking) {
      stopSpeaking();
      setIsSpeaking(false);
    } else {
      setIsSpeaking(true);
      speakAdvisory(
        speechText,
        lang,
        () => setIsSpeaking(true),
        () => setIsSpeaking(false)
      );
    }
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onMarkInspected(
      alert.id,
      inspectionNotes || (lang === 'hi' ? 'भंडारण क्षेत्र का निरीक्षण पूरा हुआ। दाना सुरक्षित पाया गया।' : 'Visual storage inspection completed. Grain condition confirmed normal.'),
      inspectorName || 'Kisan Operator'
    );
    setSubmitted(true);
    setTimeout(() => {
      setSubmitted(false);
      onClose();
    }, 1200);
  };

  return (
    <div className="krishi-modal-overlay" onClick={onClose}>
      <div className="krishi-modal-card" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="krishi-modal-header">
          <div className="krishi-modal-header-title">
            <ShieldAlert size={22} color={alert.severity === 'critical' ? '#dc2626' : '#d97706'} />
            <span>{t.alertExplanationHeader}</span>
            {isDemo && (
              <span className="krishi-demo-badge" style={{ marginLeft: 8 }}>DEMO</span>
            )}
          </div>
          <button className="krishi-modal-close-btn" onClick={onClose} aria-label={t.cancel}>
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <div className="krishi-modal-body">
          {/* Alert Title & Location Banner */}
          <div style={{
            background: alert.severity === 'critical' ? '#fee2e2' : '#fef3c7',
            border: `1.5px solid ${alert.severity === 'critical' ? '#fecaca' : '#fde68a'}`,
            borderRadius: 14,
            padding: 16
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={{
                fontSize: 12,
                fontWeight: 700,
                color: alert.severity === 'critical' ? '#b91c1c' : '#b45309',
                textTransform: 'uppercase',
                letterSpacing: 0.5
              }}>
                {alert.severity === 'critical' ? 'Urgent Warning' : 'Attention Advisory'} • {alert.zone_id}
              </span>
              <span style={{ fontSize: 11, color: '#64748b' }}>
                {new Date(alert.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            </div>
            <h3 style={{ fontSize: 16, fontWeight: 700, color: '#1e293b', margin: '0 0 6px 0' }}>
              {alert.title}
            </h3>
            <p style={{ fontSize: 13, color: '#475569', margin: 0, lineHeight: 1.45 }}>
              {alert.message}
            </p>
          </div>

          {/* Voice Explanation Trigger */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '4px 0' }}>
            <span style={{ fontSize: 12, color: '#64748b', fontWeight: 500 }}>
              {lang === 'hi' ? 'सलाह को ध्यानपूर्वक सुनें:' : 'Listen to advisory in spoken voice:'}
            </span>
            <button
              type="button"
              className={`krishi-btn-voice ${isSpeaking ? 'speaking' : ''}`}
              onClick={handleVoice}
            >
              {isSpeaking ? <VolumeX size={15} /> : <Volume2 size={15} />}
              <span>{isSpeaking ? t.stopAudio : t.listenAudio}</span>
            </button>
          </div>

          {/* 4-Step Guided Investigation Sequence */}
          <div>
            <h4 style={{ fontSize: 14, fontWeight: 700, color: '#1b4d3e', margin: '0 0 10px 0' }}>
              {t.alertStepsHeader}
            </h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div className="krishi-step-card">
                <div className="krishi-step-num">{lang === 'hi' ? 'जाँच 1' : 'Check 1'}</div>
                <p className="krishi-step-text">{t.alertStep1}</p>
              </div>
              <div className="krishi-step-card">
                <div className="krishi-step-num">{lang === 'hi' ? 'जाँच 2' : 'Check 2'}</div>
                <p className="krishi-step-text">{t.alertStep2}</p>
              </div>
              <div className="krishi-step-card">
                <div className="krishi-step-num">{lang === 'hi' ? 'जाँच 3' : 'Check 3'}</div>
                <p className="krishi-step-text">{t.alertStep3}</p>
              </div>
              <div className="krishi-step-card">
                <div className="krishi-step-num">{lang === 'hi' ? 'जाँच 4' : 'Action 4'}</div>
                <p className="krishi-step-text">{t.alertStep4}</p>
              </div>
            </div>
          </div>

          {/* Scientific & Safe Agriculture Reminder */}
          <div style={{
            background: '#f0fdf4',
            border: '1px solid #bbf7d0',
            borderRadius: 10,
            padding: 12,
            fontSize: 12,
            color: '#166534',
            display: 'flex',
            alignItems: 'center',
            gap: 8
          }}>
            <AlertTriangle size={16} color="#16a34a" style={{ flexShrink: 0 }} />
            <span>
              {lang === 'hi'
                ? 'महत्वपूर्ण: कीट की पुष्टि होने से पहले कीटनाशक का छिड़काव न करें। केवल भौतिक जाँच के बाद उचित निर्णय लें।'
                : 'Safe Storage Note: Do not apply chemical fumigants without visual inspection and confirmed insect presence.'}
            </span>
          </div>

          {/* Inspection Form */}
          <form onSubmit={handleFormSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <h4 style={{ fontSize: 13, fontWeight: 700, color: '#1e293b', margin: '4px 0 0 0' }}>
              {lang === 'hi' ? 'निरीक्षण परिणाम दर्ज करें' : 'Record Storage Inspection Result'}
            </h4>
            <div>
              <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: '#64748b', marginBottom: 4 }}>
                {t.inspectorNameLabel}
              </label>
              <input
                type="text"
                className="krishi-input"
                value={inspectorName}
                onChange={e => setInspectorName(e.target.value)}
                required
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: '#64748b', marginBottom: 4 }}>
                {lang === 'hi' ? 'निरीक्षण विवरण व स्थिति' : 'Inspection Notes & Observations'}
              </label>
              <textarea
                className="krishi-textarea"
                rows={3}
                placeholder={t.inspectionNotesPlaceholder}
                value={inspectionNotes}
                onChange={e => setInspectionNotes(e.target.value)}
              />
            </div>

            {submitted && (
              <div style={{
                background: '#dcfce7',
                color: '#15803d',
                padding: 10,
                borderRadius: 8,
                fontSize: 12,
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: 6
              }}>
                <CheckCircle2 size={16} />
                <span>{t.inspectedSuccess}</span>
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
              <button
                type="button"
                className="krishi-btn-secondary"
                onClick={onClose}
              >
                {t.cancel}
              </button>
              <button
                type="submit"
                className="krishi-btn-primary"
                disabled={submitted}
              >
                <CheckCircle2 size={16} />
                <span>{t.submitInspection}</span>
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};
