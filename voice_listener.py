"""
voice_listener.py
Persistent Hands-Free Voice Capture Daemon for Raspberry Pi 5 ("Sakhi").
Captures continuous audio from USB microphone, detects wake word ("Sakhi" / "सखी"),
plays an audible feedback chime, and dispatches queries to the FastAPI / WebSocket kiosk backend.
"""

import os
import sys
import time
import re
import signal
import json
import subprocess
import threading
from pathlib import Path
from typing import Optional, Tuple

import httpx

# Ensure UTF-8 on all platforms
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ── Configuration ─────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
CHIME_PATH = BASE_DIR / "static" / "audio" / "ding.wav"
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
VOICE_QUERY_URL = f"{API_BASE_URL}/api/voice_query"
BROADCAST_URL = f"{API_BASE_URL}/api/kiosk/broadcast"
HEALTH_URL = f"{API_BASE_URL}/api/health"

WAKE_WORDS = [
    "sakhi", "सखी", "hey sakhi", "sakhee", "saki", "saakhi", "sakee"
]

_RUNNING = True


def handle_sig(sig, frame):
    global _RUNNING
    print(f"\n[VoiceListener] Received signal {sig}. Exiting gracefully...")
    _RUNNING = False


signal.signal(signal.SIGINT, handle_sig)
signal.signal(signal.SIGTERM, handle_sig)


# ── Audio Chime Player ────────────────────────────────────────────────────────
def play_chime():
    """Play the gentle high-pitch ding through speakers and trigger browser chime."""
    # 1. Trigger local system audio output (ALSA on Raspberry Pi 5, or Windows)
    def _local_play():
        try:
            if sys.platform == "linux" or sys.platform == "linux2":
                # Raspberry Pi 5 standard ALSA player
                if subprocess.run(["which", "aplay"], capture_output=True).returncode == 0:
                    subprocess.run(["aplay", "-q", str(CHIME_PATH)], check=False)
                    return
                if subprocess.run(["which", "paplay"], capture_output=True).returncode == 0:
                    subprocess.run(["paplay", str(CHIME_PATH)], check=False)
                    return
            elif sys.platform == "win32":
                try:
                    import winsound
                    winsound.PlaySound(str(CHIME_PATH), winsound.SND_FILENAME | winsound.SND_ASYNC)
                    return
                except Exception:
                    pass
        except Exception as e:
            print(f"[VoiceListener Chime Warning] Local audio output: {e}")

    threading.Thread(target=_local_play, daemon=True).start()

    # 2. Inform the kiosk frontend via WebSocket to also play browser-side chime
    try:
        httpx.post(
            BROADCAST_URL,
            json={"action": "play_chime"},
            timeout=1.0
        )
    except Exception:
        pass


def broadcast_status(status: str, text: str):
    """Notify connected kiosk screens of Sakhi's current state."""
    try:
        httpx.post(
            BROADCAST_URL,
            json={"action": "status", "status": status, "text": text},
            timeout=1.5
        )
    except Exception:
        pass


# ── Wake Word & Query Parser ──────────────────────────────────────────────────
def parse_wake_word_and_query(text: str) -> Tuple[bool, str]:
    """
    Parses incoming speech transcript.
    Returns (wake_word_detected, query_content).
    """
    if not text:
        return False, ""

    clean = text.lower().strip()
    
    # Check for direct wake word prefix or containment
    for ww in WAKE_WORDS:
        pattern = rf"\b{re.escape(ww)}\b"
        match = re.search(pattern, clean, flags=re.IGNORECASE)
        if match:
            # Wake word is detected
            # Extract whatever query came after or around it
            query_part = clean[match.end():].strip()
            # Remove leading punctuation (e.g. comma, hyphen)
            query_part = re.sub(r"^[,.\-?!:;\s]+", "", query_part).strip()
            return True, query_part

    # Also check Hindi script representation "सखी"
    if "सखी" in text:
        idx = text.find("सखी")
        query_part = text[idx + len("सखी"):].strip()
        query_part = re.sub(r"^[,.\-?!:;\s]+", "", query_part).strip()
        return True, query_part

    return False, ""


def dispatch_query_to_kiosk(query: str):
    """Sends the destination query to FastAPI to trigger the synchronized tour."""
    if not query:
        return

    print(f"\n[VoiceListener] -> Dispatching query to Kiosk: '{query}'")
    broadcast_status("speaking", "Sakhi rasta dikha rahi hai...")

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(VOICE_QUERY_URL, json={"query": query, "broadcast": True})
            if resp.status_code == 200:
                data = resp.json()
                dest_title = data.get("display_title", query)
                print(f"[VoiceListener] Successfully triggered tour for: {dest_title}")
            else:
                print(f"[VoiceListener] Server returned code {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[VoiceListener Error] Failed to dispatch query: {e}")
        broadcast_status("idle", "")


# ── Audio Capture Backends ───────────────────────────────────────────────────
def listen_with_speech_recognition():
    """
    Primary pipeline using Python SpeechRecognition library.
    Listens continuously on USB Microphone, handles ambient noise,
    and supports both single-utterance and two-turn queries.
    """
    import speech_recognition as sr

    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 250     # Lower = picks up softer speech
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 0.6      # 0.6s silence = end of phrase (was 0.8)
    recognizer.non_speaking_duration = 0.4  # Faster response at end of speech

    # Look for USB microphone or default microphone
    device_index = None
    mic_names = sr.Microphone.list_microphone_names()
    print("[VoiceListener] Available audio inputs:")
    for i, name in enumerate(mic_names):
        print(f"  [{i}] {name}")
        # Prefer USB Microphone on Raspberry Pi
        if "usb" in name.lower() and device_index is None:
            device_index = i

    if device_index is not None:
        print(f"[VoiceListener] Selected USB Audio Input: [{device_index}] {mic_names[device_index]}")
        mic = sr.Microphone(device_index=device_index)
    else:
        print("[VoiceListener] Using default system audio input.")
        mic = sr.Microphone()

    with mic as source:
        print("[VoiceListener] Calibrating microphone for ambient room noise (1 sec)...")
        recognizer.adjust_for_ambient_noise(source, duration=1.0)
        print("[VoiceListener] Ready! Say 'Sakhi' or 'Sakhi, Bosch Lab kahan hai?'...")

    state_awaiting_query = False
    state_timestamp = 0.0

    while _RUNNING:
        try:
            # Check timeout for awaiting query (e.g. 7 seconds after wake word chime)
            if state_awaiting_query and (time.time() - state_timestamp > 7.0):
                print("[VoiceListener] Listening window timed out. Resetting to wake word standby.")
                broadcast_status("idle", "")
                state_awaiting_query = False

            with mic as source:
                # Short phrase limit keeps response fast and responsive
                listen_limit = 6 if state_awaiting_query else 4
                broadcast_status("listening" if state_awaiting_query else "idle", 
                                 "Sakhi sun rahi hai..." if state_awaiting_query else "")
                
                audio = recognizer.listen(source, timeout=3.0, phrase_time_limit=listen_limit)

            try:
                # Transcribe using Google Speech API with Hindi/Hinglish + English recognition
                # Try Hindi first (covers most campus queries), then English as fallback
                transcript = None
                for lang in ["hi-IN", "en-IN"]:
                    try:
                        transcript = recognizer.recognize_google(audio, language=lang)
                        break
                    except sr.UnknownValueError:
                        continue
                    except sr.RequestError:
                        raise
                if not transcript:
                    raise sr.UnknownValueError()
                print(f"[VoiceListener Heard] '{transcript}'")

                if state_awaiting_query:
                    # User already said wake word, this utterance is their destination query
                    dispatch_query_to_kiosk(transcript)
                    state_awaiting_query = False
                    continue

                # Check for wake word in transcript
                has_wake, query_part = parse_wake_word_and_query(transcript)
                if has_wake:
                    print(f"[VoiceListener] *** Wake Word Detected! (Query snippet: '{query_part}') ***")
                    play_chime()
                    broadcast_status("listening", "Sakhi sun rahi hai...")

                    if query_part and len(query_part) > 2:
                        # User asked the question in one breath: "Sakhi, Bosch Lab kahan hai?"
                        dispatch_query_to_kiosk(query_part)
                    else:
                        # User only said "Sakhi" - chime and wait for destination prompt
                        state_awaiting_query = True
                        state_timestamp = time.time()
                else:
                    # Check if spoken transcript directly matches a known campus location even without wake word
                    # to make kiosk extra responsive
                    clean_tr = transcript.lower()
                    if any(k in clean_tr for k in ["bosch", "mitsubishi", "robotics", "eyantra", "washroom", "toilet", "307", "207", "lalit", "lab"]):
                        print(f"[VoiceListener Direct Keyword Match] -> '{transcript}'")
                        play_chime()
                        dispatch_query_to_kiosk(transcript)

            except sr.UnknownValueError:
                # Normal background silence / inaudible noise
                pass
            except sr.RequestError as e:
                print(f"[VoiceListener ASR API Error]: {e}")
                time.sleep(1.0)

        except sr.WaitTimeoutError:
            # Listening loop idle pulse
            pass
        except Exception as e:
            if _RUNNING:
                print(f"[VoiceListener Audio Error]: {e}")
                time.sleep(1.0)


def fallback_sounddevice_listener():
    """
    Fallback audio capture using sounddevice + simple energy thresholding.
    Used if speech_recognition package is not installed.
    """
    import sounddevice as sd
    import numpy as np

    print("[VoiceListener Fallback] Running sounddevice energy listener...")
    sample_rate = 16000
    block_duration = 0.5  # seconds
    block_size = int(sample_rate * block_duration)

    while _RUNNING:
        try:
            recording = sd.rec(block_size, samplerate=sample_rate, channels=1, dtype='float32')
            sd.wait()
            energy = np.linalg.norm(recording)
            if energy > 15.0:
                print(f"[VoiceListener Fallback Activity Detected] Energy: {energy:.2f}")
                # Play chime and broadcast listening status
                play_chime()
                broadcast_status("listening", "Sakhi sun rahi hai...")
                time.sleep(1.0)
        except Exception as e:
            print(f"[VoiceListener Fallback Error]: {e}")
            time.sleep(2.0)


def wait_for_server():
    """Wait for FastAPI server to be online before capturing."""
    print(f"[VoiceListener] Checking FastAPI server at {HEALTH_URL}...")
    for _ in range(30):
        try:
            r = httpx.get(HEALTH_URL, timeout=1.0)
            if r.status_code == 200:
                print("[VoiceListener] FastAPI server is ONLINE.")
                return True
        except Exception:
            time.sleep(0.8)
    print("[VoiceListener Warning] Server not reachable yet; starting listener anyway.")
    return False


# ── Main Entrypoint ──────────────────────────────────────────────────────────
def main():
    print("=" * 65)
    print("    SAKHI  -  Raspberry Pi 5 Hands-Free Voice Listener")
    print("    Wake Word: 'Sakhi' / 'सखी'")
    print("=" * 65)

    wait_for_server()

    # Select available audio backend
    try:
        import speech_recognition
        listen_with_speech_recognition()
    except ImportError:
        print("[VoiceListener Warning] 'speech_recognition' package not installed.")
        print("To install: pip install SpeechRecognition sounddevice")
        try:
            import sounddevice
            fallback_sounddevice_listener()
        except ImportError:
            print("[VoiceListener Warning] 'sounddevice' also not installed.")
            print("[VoiceListener] Running in daemon standby mode (monitoring server)...")
            while _RUNNING:
                time.sleep(2.0)


if __name__ == "__main__":
    main()
