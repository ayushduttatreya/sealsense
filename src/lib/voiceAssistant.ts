/**
 * Voice Assistant Utility for Farmer View
 * Uses browser SpeechSynthesis API with Hindi (hi-IN) and English (en-IN / en-US) voice selection.
 */

export function isSpeechSupported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window;
}

export function stopSpeaking(): void {
  if (isSpeechSupported()) {
    window.speechSynthesis.cancel();
  }
}

export function speakAdvisory(
  text: string,
  lang: 'en' | 'hi',
  onStart?: () => void,
  onEnd?: () => void
): boolean {
  if (!isSpeechSupported()) {
    return false;
  }

  // Cancel any ongoing speech
  window.speechSynthesis.cancel();

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = lang === 'hi' ? 'hi-IN' : 'en-IN';
  utterance.rate = 0.95; // Slightly slower, clear conversational pace for farmers
  utterance.pitch = 1.0;

  // Try to find a matching natural voice
  const voices = window.speechSynthesis.getVoices();
  if (voices && voices.length > 0) {
    if (lang === 'hi') {
      const hiVoice = voices.find(v => v.lang.startsWith('hi') || v.name.toLowerCase().includes('hindi') || v.name.toLowerCase().includes('lekha'));
      if (hiVoice) utterance.voice = hiVoice;
    } else {
      const enInVoice = voices.find(v => v.lang === 'en-IN' || v.name.toLowerCase().includes('india') || v.name.toLowerCase().includes('rishi'));
      if (enInVoice) utterance.voice = enInVoice;
    }
  }

  utterance.onstart = () => {
    if (onStart) onStart();
  };

  utterance.onend = () => {
    if (onEnd) onEnd();
  };

  utterance.onerror = () => {
    if (onEnd) onEnd();
  };

  try {
    window.speechSynthesis.speak(utterance);
    return true;
  } catch (e) {
    console.warn('Speech synthesis error:', e);
    if (onEnd) onEnd();
    return false;
  }
}
