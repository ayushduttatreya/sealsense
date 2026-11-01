import React, { useState } from 'react';
import {
  HelpCircle, BookOpen, Wrench, PhoneCall, ChevronDown,
  Volume2, VolumeX
} from 'lucide-react';
import { translations, type FarmerLanguage } from '../../lib/farmerTranslations';
import { speakAdvisory, stopSpeaking } from '../../lib/voiceAssistant';

interface Props {
  lang: FarmerLanguage;
  onSetLang: (lang: FarmerLanguage) => void;
}

export const FarmerHelp: React.FC<Props> = ({ lang, onSetLang }) => {
  const t = translations[lang];
  const [openFaq, setOpenFaq] = useState<number | null>(0);
  const [isSpeaking, setIsSpeaking] = useState(false);

  const toggleFaq = (idx: number) => {
    setOpenFaq(prev => (prev === idx ? null : idx));
  };

  const handleVoiceHelp = () => {
    if (isSpeaking) {
      stopSpeaking();
      setIsSpeaking(false);
    } else {
      setIsSpeaking(true);
      const text = lang === 'hi'
        ? 'SealSense किसान गाइड। साइलो में CO₂ बढ़ने का मतलब है अनाज में नमी या कीड़ों के कारण सांस लेने की गति तेज होना। हवा की नमी दाने की नमी नहीं है। असामान्य आवाज सुनने पर पहले दाना देखें, कीटनाशक बिना सोचे न डालें।'
        : 'SealSense Farmer Guide. Rising CO₂ in your silo indicates moisture or biological activity before mould appears. Air humidity is not grain moisture. If unusual sounds are heard, inspect the grain physically before spraying chemicals.';
      speakAdvisory(
        text,
        lang,
        () => setIsSpeaking(true),
        () => setIsSpeaking(false)
      );
    }
  };

  return (
    <div className="krishi-container">
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h2 className="krishi-greeting-title">
            <HelpCircle size={22} color="#1b4d3e" />
            <span>{t.helpTitle}</span>
          </h2>
          <p className="krishi-greeting-sub">
            {lang === 'hi' ? 'सेंसर को समझें और अनाज को सुरक्षित रखें' : 'Sensor Education & Storage Troubleshooting'}
          </p>
        </div>

        {/* Voice Advisory Trigger */}
        <button
          type="button"
          className={`krishi-btn-voice ${isSpeaking ? 'speaking' : ''}`}
          onClick={handleVoiceHelp}
        >
          {isSpeaking ? <VolumeX size={15} /> : <Volume2 size={15} />}
          <span>{isSpeaking ? t.stopAudio : (lang === 'hi' ? 'गाइड सुनें' : 'Listen Guide')}</span>
        </button>
      </div>

      {/* Language Preference Card */}
      <div style={{
        background: '#ffffff',
        border: '1.5px solid var(--krishi-card-border)',
        borderRadius: 'var(--krishi-radius-card)',
        padding: 16,
        boxShadow: 'var(--krishi-shadow)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: 12
      }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 700, color: '#1e293b' }}>
            {lang === 'hi' ? 'भाषा चुनें (Select Language)' : 'Language Selection'}
          </div>
          <div style={{ fontSize: 12, color: '#64748b' }}>
            {lang === 'hi' ? 'हिंदी व अंग्रेजी भाषा समर्थन' : 'Bilingual English & Hindi support'}
          </div>
        </div>

        <div className="krishi-lang-toggle">
          <button
            type="button"
            className={`krishi-lang-opt ${lang === 'hi' ? 'active' : ''}`}
            onClick={() => onSetLang('hi')}
          >
            हिंदी
          </button>
          <button
            type="button"
            className={`krishi-lang-opt ${lang === 'en' ? 'active' : ''}`}
            onClick={() => onSetLang('en')}
          >
            English
          </button>
        </div>
      </div>

      {/* Sensor Education Section */}
      <div>
        <h3 className="krishi-section-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <BookOpen size={18} color="#1b4d3e" />
          <span>{t.educationSection}</span>
        </h3>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {/* FAQ 1: CO2 */}
          <div className="krishi-faq-card" onClick={() => toggleFaq(0)}>
            <div className="krishi-faq-q">
              <span>{t.faq1Q}</span>
              <ChevronDown
                size={18}
                style={{
                  transform: openFaq === 0 ? 'rotate(180deg)' : 'none',
                  transition: 'transform 0.2s ease',
                  flexShrink: 0
                }}
              />
            </div>
            {openFaq === 0 && (
              <div className="krishi-faq-a">
                {t.faq1A}
              </div>
            )}
          </div>

          {/* FAQ 2: Air Humidity vs Grain Moisture */}
          <div className="krishi-faq-card" onClick={() => toggleFaq(1)}>
            <div className="krishi-faq-q">
              <span>{t.faq2Q}</span>
              <ChevronDown
                size={18}
                style={{
                  transform: openFaq === 1 ? 'rotate(180deg)' : 'none',
                  transition: 'transform 0.2s ease',
                  flexShrink: 0
                }}
              />
            </div>
            {openFaq === 1 && (
              <div className="krishi-faq-a">
                {t.faq2A}
              </div>
            )}
          </div>

          {/* FAQ 3: Acoustic Microphone */}
          <div className="krishi-faq-card" onClick={() => toggleFaq(2)}>
            <div className="krishi-faq-q">
              <span>{t.faq3Q}</span>
              <ChevronDown
                size={18}
                style={{
                  transform: openFaq === 2 ? 'rotate(180deg)' : 'none',
                  transition: 'transform 0.2s ease',
                  flexShrink: 0
                }}
              />
            </div>
            {openFaq === 2 && (
              <div className="krishi-faq-a">
                {t.faq3A}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Troubleshooting Section */}
      <div>
        <h3 className="krishi-section-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Wrench size={18} color="#1b4d3e" />
          <span>{t.troubleshootingSection}</span>
        </h3>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 12, padding: 14 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: '#1e293b', marginBottom: 4 }}>
              🔴 {lang === 'hi' ? 'सेंसर डिस्कनेक्ट (Sensor Offline)' : 'Sensor Offline'}
            </div>
            <div style={{ fontSize: 12, color: '#475569', lineHeight: 1.45 }}>
              {t.deviceOfflineHelp}
            </div>
          </div>

          <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 12, padding: 14 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: '#1e293b', marginBottom: 4 }}>
              🟡 {lang === 'hi' ? 'धीमा सिग्नल (Stale Data)' : 'Stale Data Signal'}
            </div>
            <div style={{ fontSize: 12, color: '#475569', lineHeight: 1.45 }}>
              {t.deviceStaleHelp}
            </div>
          </div>
        </div>
      </div>

      {/* Kisan Helpline Contact Support */}
      <div style={{
        background: 'linear-gradient(135deg, #f0fdf4 0%, #eaf3ec 100%)',
        border: '1.5px solid #bbf7d0',
        borderRadius: 'var(--krishi-radius-card)',
        padding: 20,
        boxShadow: 'var(--krishi-shadow)'
      }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 12 }}>
          <div style={{
            width: 44,
            height: 44,
            borderRadius: 12,
            background: '#1b4d3e',
            color: '#ffffff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0
          }}>
            <PhoneCall size={22} />
          </div>
          <div>
            <h4 style={{ fontSize: 15, fontWeight: 700, color: '#164032', margin: '0 0 4px 0' }}>
              {t.contactSupport}
            </h4>
            <p style={{ fontSize: 12, color: '#23634f', margin: 0, lineHeight: 1.4 }}>
              {lang === 'hi'
                ? 'सरकारी कृषि वैज्ञानिकों से मुफ्त अनाज संरक्षण सलाह के लिए कॉल करें।'
                : 'Direct access to government agricultural grain storage experts.'}
            </p>
          </div>
        </div>

        <a
          href="tel:18001801551"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
            width: '100%',
            background: '#1b4d3e',
            color: '#ffffff',
            textDecoration: 'none',
            padding: '12px 16px',
            borderRadius: 'var(--krishi-radius-btn)',
            fontWeight: 700,
            fontSize: 14,
            boxSizing: 'border-box'
          }}
        >
          <PhoneCall size={16} />
          <span>{t.supportPhone}</span>
        </a>
      </div>
    </div>
  );
};
