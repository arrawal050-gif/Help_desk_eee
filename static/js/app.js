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
const $voiceHud = document.getElementById("voice-status-hud");
const $voiceText = document.getElementById("voice-status-text");
let _hudFadeTimer = null;

export function showVoiceStatus(status, text) {
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

// ── Startup & Initialization ──────────────────────────────────────────────────
window.addEventListener("DOMContentLoaded", () => {
  initScreenWakeLock();
  connectKioskWebSocket();

  // Expose helpers globally
  window.sakhiKiosk = {
    showVoiceStatus,
    playChimeSound,
    reconnect: connectKioskWebSocket,
  };
});
