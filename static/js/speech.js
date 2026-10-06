/**
 * speech.js – Web Speech Recognition with continuous "Sakhi" wake word detection
 * + robust Web Audio API playback for TTS audio.
 *
 * WAKE WORD MODE (always active in background):
 *   - Continuously listens; when "sakhi" is detected, plays chime.
 *   - One-breath: "Sakhi, Bosch lab kahan hai?" fires query immediately.
 *   - Two-turn: bare "Sakhi" → chime → waits 7s for follow-up destination.
 *
 * MIC BUTTON MODE:
 *   - One-shot listen for the query (no wake word required).
 *   - Temporarily pauses wake listener to avoid mic conflicts.
 */

const WAKE_WORDS = ["sakhi", "सखी", "sakhee", "saki", "saakhi", "sakee", "hey sakhi"];
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

let _onResult          = null;   // query callback
let _isListening       = false;  // mic-button manual mode active
let _recognition       = null;   // manual mic SpeechRecognition instance

// ── Wake word state ──────────────────────────────────────────────────────────
let _wakeRecognition   = null;
let _wakeActive        = false;  // wake listener running
let _wakeEnabled       = false;  // should keep running
let _awaitingQuery     = false;  // waiting for follow-up after bare wake word
let _awaitTimer        = null;
let _restartTimer      = null;

// ── Helpers ──────────────────────────────────────────────────────────────────

function _updateMicUI(active) {
  const btn = document.getElementById("mic-btn");
  if (btn) btn.classList.toggle("listening", active);
}

function _showHUD(text) {
  const hud = document.getElementById("voice-status-hud");
  const txt = document.getElementById("voice-status-text");
  if (!hud) return;
  if (!text) { hud.classList.add("hidden"); return; }
  if (txt) txt.textContent = text;
  hud.classList.remove("hidden", "speaking");
}

function _containsWakeWord(transcript) {
  const s = transcript.toLowerCase();
  return WAKE_WORDS.some(w => s.includes(w));
}

function _extractQuery(transcript) {
  const s = transcript.toLowerCase();
  for (const w of WAKE_WORDS) {
    const idx = s.indexOf(w);
    if (idx !== -1) {
      return transcript.slice(idx + w.length).replace(/^[,.\-?!:;\s]+/, "").trim();
    }
  }
  return "";
}

function _playChime() {
  try {
    const a = new Audio("/static/audio/ding.wav");
    a.volume = 0.8;
    const p = a.play();
    if (p) p.catch(_synthesizeDing);
  } catch (_) { _synthesizeDing(); }
}

function _synthesizeDing() {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const osc = ctx.createOscillator();
    const g   = ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(1046.5, ctx.currentTime);
    g.gain.setValueAtTime(0.3, ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.45);
    osc.connect(g); g.connect(ctx.destination);
    osc.start(); osc.stop(ctx.currentTime + 0.45);
    setTimeout(() => { try { ctx.close(); } catch(_) {} }, 1000);
  } catch(_) {}
}

// ── Continuous Wake Word Listener ────────────────────────────────────────────

function _buildWakeRecognition() {
  const r = new SpeechRecognition();
  r.lang = "hi-IN";
  r.continuous = true;
  r.interimResults = true;
  r.maxAlternatives = 3;

  r.onstart = () => {
    _wakeActive = true;
    console.log("[WakeWord] Listener active – say 'Sakhi' to activate.");
  };

  r.onresult = (e) => {
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const res = e.results[i];
      for (let a = 0; a < res.length; a++) {
        const text = res[a].transcript || "";
        const final = res.isFinal;

        // If we're awaiting a follow-up query after bare "Sakhi"
        if (_awaitingQuery && final && !_containsWakeWord(text)) {
          const q = text.trim();
          if (q.length > 1) {
            console.log(`[WakeWord] Follow-up query: "${q}"`);
            _awaitingQuery = false;
            clearTimeout(_awaitTimer); _awaitTimer = null;
            _showHUD("Sakhi samajh rahi hai...");
            setTimeout(() => _showHUD(""), 2000);
            if (_onResult) _onResult(q);
            return;
          }
        }

        if (_containsWakeWord(text)) {
          const queryPart = _extractQuery(text);

          if (queryPart && queryPart.length > 2) {
            // One-breath: "Sakhi, Lab kahan hai?"
            if (!final) continue; // wait for final result
            console.log(`[WakeWord] One-breath: "${queryPart}"`);
            _awaitingQuery = false;
            clearTimeout(_awaitTimer); _awaitTimer = null;
            _playChime();
            _showHUD("Sakhi sun rahi hai...");
            setTimeout(() => {
              _showHUD("");
              if (_onResult) _onResult(queryPart);
            }, 400);
            return;
          } else if (!_awaitingQuery) {
            // Bare "Sakhi" – wait for destination
            console.log("[WakeWord] Bare wake word – waiting for destination...");
            _awaitingQuery = true;
            _playChime();
            _showHUD("Sakhi sun rahi hai... bataiye kahan jaana hai?");
            clearTimeout(_awaitTimer);
            _awaitTimer = setTimeout(() => {
              console.log("[WakeWord] Query window timed out.");
              _awaitingQuery = false;
              _showHUD("");
            }, 7000);
            return;
          }
        }
      }
    }
  };

  r.onend = () => {
    _wakeActive = false;
    if (_wakeEnabled && !_isListening) {
      clearTimeout(_restartTimer);
      _restartTimer = setTimeout(() => {
        if (_wakeEnabled && !_wakeActive && !_isListening) {
          try { _wakeRecognition.start(); }
          catch (_) { setTimeout(_startWakeListener, 2000); }
        }
      }, 500);
    }
  };

  r.onerror = (e) => {
    _wakeActive = false;
    const delay = (e.error === "no-speech" || e.error === "audio-capture") ? 800 : 3000;
    if (e.error !== "no-speech") console.warn(`[WakeWord] Error: ${e.error}`);
    if (_wakeEnabled && !_isListening) {
      clearTimeout(_restartTimer);
      _restartTimer = setTimeout(() => {
        if (_wakeEnabled && !_wakeActive && !_isListening) {
          try { _wakeRecognition.start(); }
          catch (_) { setTimeout(_startWakeListener, 2000); }
        }
      }, delay);
    }
  };

  return r;
}

function _startWakeListener() {
  if (!SpeechRecognition || !_wakeEnabled || _wakeActive || _isListening) return;
  _wakeRecognition = _buildWakeRecognition();
  try {
    _wakeRecognition.start();
  } catch (e) {
    _wakeActive = false;
    console.warn("[WakeWord] Could not start:", e);
    clearTimeout(_restartTimer);
    _restartTimer = setTimeout(_startWakeListener, 3000);
  }
}

function _stopWakeListener() {
  _wakeEnabled = false;
  _wakeActive  = false;
  _awaitingQuery = false;
  clearTimeout(_awaitTimer);
  clearTimeout(_restartTimer);
  _awaitTimer = _restartTimer = null;
  if (_wakeRecognition) {
    try { _wakeRecognition.stop(); } catch(_) {}
    _wakeRecognition = null;
  }
}

// ── Public API ───────────────────────────────────────────────────────────────

/**
 * Initialize speech module.
 * Starts continuous wake word listening immediately.
 * @param {function} onResult  Called with the final destination query string.
 */
export function initSpeech(onResult) {
  _onResult = onResult;
  if (!SpeechRecognition) {
    console.warn("[Speech] SpeechRecognition API not available.");
    return false;
  }
  _wakeEnabled = true;
  _startWakeListener();
  return true;
}

/**
 * Mic button – one-shot manual listen (no wake word needed).
 */
export function toggleMic() {
  if (!SpeechRecognition) return;

  if (_isListening) {
    if (_recognition) { try { _recognition.stop(); } catch(_) {} }
    _isListening = false;
    _updateMicUI(false);
    return;
  }

  // Pause wake listener while mic button is active
  if (_wakeActive && _wakeRecognition) {
    _wakeEnabled = false; // pause
    try { _wakeRecognition.stop(); } catch(_) {}
  }

  _recognition = new SpeechRecognition();
  _recognition.lang = "hi-IN";
  _recognition.continuous = false;
  _recognition.interimResults = false;
  _recognition.maxAlternatives = 2;

  _recognition.onresult = (e) => {
    const raw = e.results[0][0].transcript.trim();
    if (raw && _onResult) {
      // Strip wake word if accidentally included
      const q = _containsWakeWord(raw) ? (_extractQuery(raw) || raw) : raw;
      _onResult(q);
    }
  };

  const _onMicEnd = () => {
    _isListening = false;
    _updateMicUI(false);
    // Resume wake listener
    _wakeEnabled = true;
    clearTimeout(_restartTimer);
    _restartTimer = setTimeout(_startWakeListener, 600);
  };

  _recognition.onend  = _onMicEnd;
  _recognition.onerror = (e) => {
    console.warn("[MicBtn Error]:", e.error);
    _onMicEnd();
  };

  try {
    _recognition.start();
    _isListening = true;
    _updateMicUI(true);
  } catch (e) {
    console.warn("[MicBtn] Start failed:", e);
    _isListening = false;
    _updateMicUI(false);
    _wakeEnabled = true;
    _startWakeListener();
  }
}

// ── Audio Playback ────────────────────────────────────────────────────────────

let _audioCtx      = null;
let _currentSource = null;

/**
 * Decode base64 MP3 and play via Web Audio API.
 */
export async function playAudio(base64mp3) {
  if (!base64mp3) return;
  try {
    if (!_audioCtx) {
      _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (_audioCtx.state === "suspended") {
      await _audioCtx.resume();
    }
    if (_currentSource) {
      try { _currentSource.stop(); } catch(_) {}
      _currentSource = null;
    }
    const bytes  = Uint8Array.from(atob(base64mp3), c => c.charCodeAt(0));
    const buffer = await _audioCtx.decodeAudioData(bytes.buffer);
    _currentSource = _audioCtx.createBufferSource();
    _currentSource.buffer = buffer;
    _currentSource.connect(_audioCtx.destination);
    _currentSource.start();
  } catch (e) {
    console.warn("[Audio playAudio]", e);
  }
}

if (typeof window !== "undefined") {
  window.playAudio = playAudio;
}

