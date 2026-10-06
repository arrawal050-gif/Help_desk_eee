/**
 * app.js – Hands-Free Voice Kiosk Controller for Raspberry Pi 5 ("Sakhi")
 * Connects to ws://<host>/ws/kiosk, handles auto-execution of synchronized tours,
 * displays subtle voice state HUD, keeps display awake, and plays feedback chimes.
 */

// ── Screen Wake Lock (Prevent Screen Blanking on Pi 5) ─────────────────────────
let _wakeLock = null;

async function initScreenWakeLock() {
  if (!("wakeLock" in navigator)) {
    console.log("[Kiosk WakeLock] Screen Wake Lock API not supported in this browser.");
    return;
  }

  async function requestLock() {
    try {
      _wakeLock = await navigator.wakeLock.request("screen");
      console.log("[Kiosk WakeLock] Display keep-awake lock acquired.");
      _wakeLock.addEventListener("release", () => {
        console.log("[Kiosk WakeLock] Wake lock was released.");
      });
    } catch (err) {
      console.warn("[Kiosk WakeLock] Could not acquire lock:", err);
    }
  }

  await requestLock();

  // Re-acquire lock if user switches tabs or window regains visibility
  document.addEventListener("visibilitychange", async () => {
    if (document.visibilityState === "visible") {
      await requestLock();
    }
  });
}

// ── Voice Feedback Chime (Web Audio API & Audio Element) ──────────────────────
const _chimeAudio = new Audio("/static/audio/ding.wav");
_chimeAudio.preload = "auto";

export function playChimeSound() {
  try {
    _chimeAudio.currentTime = 0;
    const playPromise = _chimeAudio.play();
    if (playPromise !== undefined) {
      playPromise.catch((err) => {
        // Fallback: Web Audio API synthesized ding if media element is restricted
        synthesizeWebAudioDing();
      });
    }
  } catch (e) {
    synthesizeWebAudioDing();
  }
}

function synthesizeWebAudioDing() {
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.type = "sine";
    osc.frequency.setValueAtTime(1046.5, ctx.currentTime); // C6 note
    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.45);

    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.45);
  } catch (err) {
    console.warn("[WebAudio Ding]", err);
  }
}

// ── Subtle On-Screen Voice HUD Indicator ──────────────────────────────────────
// NOTE: DOM refs are resolved lazily inside functions (module runs before DOMContentLoaded)
let _hudFadeTimer = null;

export function showVoiceStatus(status, text) {
  const $voiceHud  = document.getElementById("voice-status-hud");
  const $voiceText = document.getElementById("voice-status-text");
  if (!$voiceHud) return;

  clearTimeout(_hudFadeTimer);

  if (status === "idle" || !text) {
    _hudFadeTimer = setTimeout(() => {
      $voiceHud.classList.add("hidden");
      $voiceHud.classList.remove("speaking");
    }, 1200);
    return;
  }

  if ($voiceText) {
    $voiceText.textContent = text;
  }

  $voiceHud.classList.remove("hidden");
  if (status === "speaking") {
    $voiceHud.classList.add("speaking");
  } else {
    $voiceHud.classList.remove("speaking");
  }
}

// ── WebSocket Kiosk Connection ────────────────────────────────────────────────
let _ws = null;
let _reconnectTimer = null;

function connectKioskWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/kiosk`;

  console.log(`[Kiosk WS] Connecting to ${wsUrl}...`);

  try {
    _ws = new WebSocket(wsUrl);

    _ws.onopen = () => {
      console.log("[Kiosk WS] Connected to Sakhi backend dispatcher.");
      if (_reconnectTimer) {
        clearTimeout(_reconnectTimer);
        _reconnectTimer = null;
      }
    };

    _ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleKioskCommand(msg);
      } catch (err) {
        console.warn("[Kiosk WS Parse Error]", err, event.data);
      }
    };

    _ws.onclose = () => {
      console.warn("[Kiosk WS] Connection lost. Reconnecting in 2.5s...");
      scheduleReconnect();
    };

    _ws.onerror = (err) => {
      console.error("[Kiosk WS Error]", err);
      _ws.close();
    };
  } catch (err) {
    console.error("[Kiosk WS Setup Error]", err);
    scheduleReconnect();
  }
}

function scheduleReconnect() {
  if (!_reconnectTimer) {
    _reconnectTimer = setTimeout(() => {
      _reconnectTimer = null;
      connectKioskWebSocket();
    }, 2500);
  }
}

// ── Command Dispatcher ────────────────────────────────────────────────────────
function handleKioskCommand(data) {
  if (!data || !data.action) return;

  console.log("[Kiosk WS Received]", data.action, data);

  switch (data.action) {
    case "start_tour": {
      // Show speaking state
      const title = data.display_title || data.destination_entity?.name || "Destination";
      showVoiceStatus("speaking", `Sakhi bata rahi hai: ${title}`);

      const segments = data.tourSegments || data.tour_segments;
      if (segments && segments.length > 0 && typeof window.playSynchronizedTour === "function") {
        console.log("[Kiosk Auto-Execute] Triggering playSynchronizedTour without mouse/touch interaction!");
        window.playSynchronizedTour(
          segments,
          data.route,
          data.display_title,
          data.destination_entity
        );
      }

      // Hide status after brief duration once playback begins
      setTimeout(() => {
        showVoiceStatus("idle", "");
      }, 5000);
      break;
    }

    case "speak_only":
    case "not_found": {
      const promptText = data.spoken_hinglish || data.display_title || "Sakhi";
      showVoiceStatus("speaking", promptText);

      if (data.audio_base64 && typeof window.playAudio === "function") {
        window.playAudio(data.audio_base64);
      }

      setTimeout(() => {
        showVoiceStatus("idle", "");
      }, 6000);
      break;
    }

    case "status": {
      showVoiceStatus(data.status, data.text);
      if (data.status === "listening") {
        playChimeSound();
      }
      break;
    }

    case "play_chime": {
      playChimeSound();
      showVoiceStatus("listening", "Sakhi sun rahi hai...");
      break;
    }

    case "pong":
      break;

    default:
      console.log("[Kiosk Command Unhandled]", data);
  }
}

// ── Frontend Audio Recorder (MediaRecorder -> Cloud Whisper) ──────────────────
let mediaRecorder = null;
let audioChunks = [];
let _isRecording = false;

export function showKioskStatus(text) {
  showVoiceStatus("listening", text);
}

export function playDirectAudio(base64Audio) {
  if (!base64Audio) return;
  if (typeof window.playAudio === "function") {
    window.playAudio(base64Audio);
    return;
  }
  try {
    const src = base64Audio.startsWith("data:") ? base64Audio : `data:audio/mp3;base64,${base64Audio}`;
    const snd = new Audio(src);
    snd.play().catch(e => console.warn("[playDirectAudio]", e));
  } catch (err) {
    console.warn("[playDirectAudio Error]", err);
  }
}

export async function startVoiceRecording() {
  if (_isRecording) {
    console.log("[VoiceRecorder] Recording already in progress.");
    return;
  }

  const $micBtn = document.getElementById("mic-btn");
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

    // Choose optimal container format
    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : (MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm'
        : (MediaRecorder.isTypeSupported('audio/wav') ? 'audio/wav' : ''));

    mediaRecorder = mimeType
      ? new MediaRecorder(stream, { mimeType })
      : new MediaRecorder(stream);

    audioChunks = [];
    _isRecording = true;

    if ($micBtn) $micBtn.classList.add("listening");
    playChimeSound();
    showKioskStatus("Listening\u2026 (Speak now)");

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.onstop = async () => {
      _isRecording = false;
      if ($micBtn) $micBtn.classList.remove("listening");
      showKioskStatus("Sakhi sun rahi hai\u2026");

      const recType = mediaRecorder.mimeType || 'audio/webm';
      const audioBlob = new Blob(audioChunks, { type: recType });
      const ext = recType.includes('webm') ? 'mic.webm' : 'mic.wav';
      const formData = new FormData();
      formData.append('audio', audioBlob, ext);

      console.log(`[VoiceRecorder] Sending ${(audioBlob.size / 1024).toFixed(1)} KB audio to Cloud Whisper\u2026`);

      try {
        const res = await fetch('/api/voice_query', { method: 'POST', body: formData });
        const data = await res.json();
        console.log("[Voice Response]", data);

        if (data.status === "success" && (data.tourSegments || data.tour_segments)) {
          const segments = data.tourSegments || data.tour_segments;
          showVoiceStatus("speaking", data.display_title || data.entity?.name || "Destination");
          if (typeof window.playSynchronizedTour === "function") {
            window.playSynchronizedTour(segments, data.route, data.display_title, data.entity);
          }
        } else if (data.status === "persona" && data.audio_base64) {
          showVoiceStatus("speaking", data.spoken_text || data.spoken_hinglish || "Sakhi");
          playDirectAudio(data.audio_base64);
        } else if (data.spoken_text && data.audio_base64) {
          showVoiceStatus("speaking", data.spoken_text);
          playDirectAudio(data.audio_base64);
        } else if (data.spoken_text) {
          showVoiceStatus("speaking", data.spoken_text);
        }
      } catch (err) {
        console.error("[VoiceRecorder] Query upload failed:", err);
        showVoiceStatus("idle", "");
      }
    };

    // ── VAD: Dynamic Voice Activity Detection ─────────────────────────────────
    // • Polls RMS amplitude every ~33 ms via Web Audio AnalyserNode.
    // • Speech active  → reset silence counter, keep recording.
    // • Silence ≥ 2 s after speech heard → finalise & upload.
    // • Hard cap 8 s  → always terminates even if VAD stalls.
    // • Grace 400 ms  → ignores brief natural pauses (breath between words).
    const VAD_SILENCE_MS = 2000;   // ms of quiet that triggers stop
    const VAD_MAX_MS     = 8000;   // absolute maximum recording length
    const VAD_INTERVAL   = 33;     // poll every ~33 ms (≈30 fps)
    const VAD_THRESHOLD  = 0.012;  // normalised RMS below which = silence
    const VAD_GRACE_MS   = 400;    // ignore pauses shorter than this

    let vadCtx, analyser, vadBuffer;
    let silenceStart = null;   // timestamp silence began; null = speech active
    let hasSpeech    = false;  // true once we detect at least one speech frame
    let vadInterval, maxTimer;

    // Unified stop helper – cleans up VAD resources then stops MediaRecorder
    const _stopRecording = (reason) => {
      clearInterval(vadInterval);
      clearTimeout(maxTimer);
      if (vadCtx) { try { vadCtx.close(); } catch (_) {} }
      if (mediaRecorder && mediaRecorder.state === "recording") {
        console.log(`[VAD] Stopping: ${reason}`);
        mediaRecorder.stop();
        stream.getTracks().forEach(t => t.stop());
      }
    };

    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      vadCtx   = new AudioCtx();
      analyser = vadCtx.createAnalyser();
      analyser.fftSize = 512;
      vadBuffer = new Float32Array(analyser.fftSize);
      vadCtx.createMediaStreamSource(stream).connect(analyser);

      vadInterval = setInterval(() => {
        if (!mediaRecorder || mediaRecorder.state !== "recording") {
          clearInterval(vadInterval);
          return;
        }

        analyser.getFloatTimeDomainData(vadBuffer);
        let sum = 0;
        for (let i = 0; i < vadBuffer.length; i++) sum += vadBuffer[i] * vadBuffer[i];
        const rms = Math.sqrt(sum / vadBuffer.length);

        if (rms > VAD_THRESHOLD) {
          // ── Active speech frame ──────────────────────────────────────────────
          hasSpeech    = true;
          silenceStart = null;   // reset silence counter
          showKioskStatus("Bol rahe ho\u2026 (recording)");
        } else {
          // ── Silence frame ────────────────────────────────────────────────────
          if (!hasSpeech) return;  // pre-speech silence: keep waiting

          if (silenceStart === null) silenceStart = Date.now();
          const silenceMs = Date.now() - silenceStart;

          if (silenceMs < VAD_GRACE_MS) {
            // Brief breath gap – don't update HUD to avoid flicker
          } else if (silenceMs < VAD_SILENCE_MS) {
            const remaining = Math.ceil((VAD_SILENCE_MS - silenceMs) / 1000);
            showKioskStatus(`Kuch aur bolein? (${remaining}s)\u2026`);
          } else {
            _stopRecording(`${silenceMs}ms silence after speech`);
          }
        }
      }, VAD_INTERVAL);

    } catch (vadErr) {
      // AnalyserNode unavailable (restricted context) – fall back to 5 s fixed timer
      console.warn("[VAD] AnalyserNode setup failed, using 5 s fallback:", vadErr);
      setTimeout(() => _stopRecording("5 s fallback"), 5000);
    }

    // Hard safety cap – fires regardless of VAD outcome
    maxTimer = setTimeout(() => _stopRecording("8 s hard cap"), VAD_MAX_MS);

    // Start buffering in 100 ms chunks (gives VAD fine-grained data)
    mediaRecorder.start(100);

  } catch (err) {
    _isRecording = false;
    if ($micBtn) $micBtn.classList.remove("listening");
    console.error("[VoiceRecorder] Microphone access error:", err);
    alert("Microphone access error. Check browser mic permissions.");
  }
}

// ── Startup & Initialization ──────────────────────────────────────────────────
window.addEventListener("DOMContentLoaded", () => {
  initScreenWakeLock();
  connectKioskWebSocket();

  // Expose helpers globally
  window.sakhiKiosk = {
    showVoiceStatus,
    showKioskStatus,
    playChimeSound,
    playDirectAudio,
    startVoiceRecording,
    reconnect: connectKioskWebSocket,
  };

  window.startVoiceRecording = startVoiceRecording;
  window.showKioskStatus = showKioskStatus;
  window.playDirectAudio = playDirectAudio;
});

