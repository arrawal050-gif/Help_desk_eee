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


def dispatch_audio_to_kiosk(audio_bytes: bytes):
    """Sends raw recorded WAV audio to /api/voice_query for Cloud Whisper transcription & tour trigger."""
    if not audio_bytes:
        return

    print("\n[VoiceListener] -> Uploading raw audio to Cloud Whisper API...")
    broadcast_status("speaking", "Sakhi sun rahi hai...")

    try:
        with httpx.Client(timeout=15.0) as client:
            files = {"audio": ("mic.wav", audio_bytes, "audio/wav")}
            resp = client.post(VOICE_QUERY_URL, files=files)
            if resp.status_code == 200:
                data = resp.json()
                transcript = data.get("transcript", "")
                dest_title = data.get("display_title", transcript)
                print(f"[VoiceListener Cloud Whisper] Transcript: '{transcript}' -> Destination: {dest_title}")
            else:
                print(f"[VoiceListener Error] Server returned code {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[VoiceListener Error] Failed to upload audio: {e}")
        broadcast_status("idle", "")



# ── Audio Capture Backends ───────────────────────────────────────────────────
def listen_with_speech_recognition():
    """
    Primary pipeline using Python SpeechRecognition library.
    Uses Google SR only for lightweight wake-word detection.
    On wake-word: hands off to capture_query_with_vad() for full VAD-based capture,
    then uploads complete audio to Cloud Whisper (whisper-large-v3 / whisper-1).
    """
    import speech_recognition as sr

    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 250         # lower = picks up softer speech
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 0.5          # 0.5s silence = end of wake-word phrase
    recognizer.non_speaking_duration = 0.3

    # Look for USB microphone or default microphone
    device_index = None
    mic_names = sr.Microphone.list_microphone_names()
    print("[VoiceListener] Available audio inputs:")
    for i, name in enumerate(mic_names):
        print(f"  [{i}] {name}")
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

    def _capture_and_dispatch():
        """
        Run VAD capture on a separate thread so SR listen loop stays free.
        Falls back to the existing Google-SR transcript if sounddevice is missing.
        """
        try:
            wav_bytes = capture_query_with_vad(device_index=device_index)
            if wav_bytes:
                dispatch_audio_to_kiosk(wav_bytes)
            else:
                print("[VoiceListener] VAD captured no speech.")
                broadcast_status("idle", "")
        except Exception as e:
            print(f"[VoiceListener VAD Error]: {e}")
            broadcast_status("idle", "")

    while _RUNNING:
        try:
            with mic as source:
                broadcast_status("idle", "")
                # Only listen long enough to catch the wake word (~4 s phrase limit)
                audio = recognizer.listen(source, timeout=3.0, phrase_time_limit=4)

            try:
                # Lightweight Google SR – only used to detect the wake word
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

                # Check for wake word
                has_wake, query_part = parse_wake_word_and_query(transcript)
                if has_wake:
                    print(f"[VoiceListener] *** Wake Word Detected! Query snippet: '{query_part}' ***")
                    play_chime()
                    broadcast_status("listening", "Sakhi sun rahi hai... boliye")

                    if query_part and len(query_part) > 3:
                        # One-breath query: "Sakhi, Bosch lab kahan hai?"
                        # Send what we already have to Cloud Whisper (the full SR audio contains it)
                        try:
                            dispatch_audio_to_kiosk(audio.get_wav_data())
                        except Exception:
                            dispatch_query_to_kiosk(transcript)
                    else:
                        # Bare "Sakhi" – launch VAD capture on background thread
                        # so the SR listener loop can restart immediately
                        print("[VoiceListener] Bare wake word – launching VAD capture thread...")
                        threading.Thread(target=_capture_and_dispatch, daemon=True).start()

                else:
                    # Direct campus keyword match without wake word – be responsive
                    clean_tr = transcript.lower()
                    if any(k in clean_tr for k in ["bosch", "mitsubishi", "robotics", "eyantra",
                                                    "washroom", "toilet", "307", "207", "lalit", "lab"]):
                        print(f"[VoiceListener Direct Keyword Match] -> '{transcript}'")
                        play_chime()
                        dispatch_query_to_kiosk(transcript)

            except sr.UnknownValueError:
                pass  # background silence
            except sr.RequestError as e:
                print(f"[VoiceListener ASR API Error]: {e}")
                time.sleep(1.0)

        except sr.WaitTimeoutError:
            pass  # idle pulse
        except Exception as e:
            if _RUNNING:
                print(f"[VoiceListener Audio Error]: {e}")
                time.sleep(1.0)



def capture_query_with_vad(
    device_index=None,
    sample_rate: int = 16000,
    silence_threshold: float = 0.018,    # RMS below this = silence
    silence_seconds: float = 2.0,        # stop after this many seconds of silence
    grace_seconds: float  = 0.4,         # ignore pauses shorter than this (breath gap)
    max_seconds: float    = 8.0,         # hard cap – always stops
    block_ms: int         = 30,          # ms per audio block (~30 ms ≈ 33 polls/s)
) -> Optional[bytes]:
    """
    VAD-based query capture using sounddevice.
    Records continuously after wake word detection.
    Stops when VAD_SILENCE_SECONDS of continuous silence is detected after speech onset.
    Returns raw 16-bit PCM WAV bytes, or None if no speech was heard.
    """
    import sounddevice as sd
    import numpy as np
    import io
    import wave

    block_size   = int(sample_rate * block_ms / 1000)
    grace_blocks = int(grace_seconds * 1000 / block_ms)
    silence_target_blocks = int(silence_seconds * 1000 / block_ms)
    max_blocks   = int(max_seconds * 1000 / block_ms)

    print(f"[VAD Capture] Waiting for speech… (silence={silence_seconds}s, max={max_seconds}s)")
    broadcast_status("listening", "Sakhi sun rahi hai... boliye")

    pcm_chunks = []
    has_speech       = False
    silence_count    = 0
    total_blocks     = 0

    try:
        sd_kwargs = {"samplerate": sample_rate, "channels": 1, "dtype": "float32"}
        if device_index is not None:
            sd_kwargs["device"] = device_index

        with sd.InputStream(blocksize=block_size, **sd_kwargs) as stream_sd:
            while _RUNNING and total_blocks < max_blocks:
                data, _ = stream_sd.read(block_size)
                total_blocks += 1
                rms = float(np.sqrt(np.mean(data ** 2)))

                if rms > silence_threshold:
                    # ── Active speech ──────────────────────────────────────────
                    has_speech    = True
                    silence_count = 0
                    pcm_chunks.append(data.copy())
                    if total_blocks % 10 == 0:  # log every ~300 ms
                        print(f"[VAD] Speech active  rms={rms:.4f}")
                else:
                    # ── Silence frame ─────────────────────────────────────────
                    if has_speech:
                        silence_count += 1
                        pcm_chunks.append(data.copy())   # keep trailing silence for natural transcription
                        if silence_count > grace_blocks:
                            remain_s = round((silence_target_blocks - silence_count) * block_ms / 1000, 1)
                            if silence_count >= silence_target_blocks:
                                print(f"[VAD] {silence_seconds}s silence detected – finalising.")
                                break
                            elif silence_count % 5 == 0:
                                print(f"[VAD] Silence {silence_count * block_ms / 1000:.1f}s / {silence_seconds}s")
                    # Pre-speech silence: keep waiting, don't record

    except Exception as e:
        print(f"[VAD Capture Error]: {e}")
        return None

    if not pcm_chunks or not has_speech:
        print("[VAD Capture] No speech detected.")
        return None

    # Pack into 16-bit WAV bytes
    pcm_all   = np.concatenate(pcm_chunks)
    pcm_int16 = (pcm_all * 32767).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_int16.tobytes())

    wav_bytes = buf.getvalue()
    duration  = len(pcm_all) / sample_rate
    print(f"[VAD Capture] Captured {duration:.2f}s of audio ({len(wav_bytes)//1024} KB)")
    return wav_bytes


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
