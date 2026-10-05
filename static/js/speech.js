/**
 * speech.js – Web Speech Recognition + Audio Playback
 */

let _recognition = null;
let _isListening = false;
let _onResult = null;

export function initSpeech(onResult) {
  _onResult = onResult;
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) return false;

  _recognition = new SpeechRecognition();
  _recognition.lang = "hi-IN";
  _recognition.interimResults = false;
  _recognition.continuous = false;

  _recognition.onresult = (e) => {
    const transcript = e.results[0][0].transcript.trim();
    if (_onResult && transcript) _onResult(transcript);
  };
  _recognition.onend = () => { _isListening = false; _updateMicUI(false); };
  _recognition.onerror = () => { _isListening = false; _updateMicUI(false); };
  return true;
}

export function toggleMic() {
  if (!_recognition) return;
  if (_isListening) {
    _recognition.stop();
    _isListening = false;
    _updateMicUI(false);
  } else {
    _recognition.start();
    _isListening = true;
    _updateMicUI(true);
  }
}

function _updateMicUI(active) {
  const btn = document.getElementById("mic-btn");
  if (!btn) return;
  btn.classList.toggle("listening", active);
}

let _audioCtx = null;
let _currentSource = null;

export async function playAudio(base64mp3) {
  if (!base64mp3) return;
  try {
    if (!_audioCtx) _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (_currentSource) { try { _currentSource.stop(); } catch(_) {} }

    const bytes = Uint8Array.from(atob(base64mp3), c => c.charCodeAt(0));
    const buffer = await _audioCtx.decodeAudioData(bytes.buffer);
    _currentSource = _audioCtx.createBufferSource();
    _currentSource.buffer = buffer;
    _currentSource.connect(_audioCtx.destination);
    _currentSource.start();
  } catch (e) {
    console.warn("[Audio]", e);
  }
}
