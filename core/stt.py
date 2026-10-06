"""
core/stt.py
Speech-to-Text transcriber using Groq Whisper (ultra-fast, ~150ms) or OpenAI Whisper API.
Accurately transcribes Indian English / Hindi / Hinglish phonetics and proper nouns.
"""
import os
from pathlib import Path
from typing import Optional
import httpx

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass


def _is_valid_key(k: Optional[str]) -> bool:
    if not k:
        return False
    k = k.strip()
    if len(k) < 15 or "your_" in k.lower() or "placeholder" in k.lower() or "api_key" in k.lower():
        return False
    return True


async def transcribe_audio_bytes(audio_bytes: bytes, filename: str = "voice.wav") -> str:
    """
    Transcribes audio using Groq Whisper (whisper-large-v3) or OpenAI Whisper (whisper-1).
    Biased towards Hindi and Hinglish campus entities:
    Sakhi, Bosch Lab, Robotics Lab, Lalit Sir, Electrical Engineering Block, washroom, 307.
    """
    if not audio_bytes or len(audio_bytes) < 100:
        print("[Whisper STT Warning] Audio payload empty or too short.")
        return ""

    groq_key = os.getenv("GROQ_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    providers = []
    if _is_valid_key(groq_key):
        providers.append(("groq", "https://api.groq.com/openai/v1/audio/transcriptions", groq_key, "whisper-large-v3"))
    if _is_valid_key(openai_key):
        providers.append(("openai", "https://api.openai.com/v1/audio/transcriptions", openai_key, "whisper-1"))

    if not providers:
        print("[Whisper STT Warning] No valid GROQ_API_KEY or OPENAI_API_KEY set.")
        return ""

    # Detect container format from magic bytes or extension to prevent Whisper demuxer errors
    content_type = "audio/wav"
    safe_filename = filename or "voice.wav"

    if audio_bytes.startswith(b"\x1a\x45\xdf\xa3") or safe_filename.endswith(".webm"):
        content_type = "audio/webm"
        if not safe_filename.endswith(".webm"):
            safe_filename = "voice.webm"
    elif audio_bytes.startswith(b"RIFF") or safe_filename.endswith(".wav"):
        content_type = "audio/wav"
        if not safe_filename.endswith(".wav"):
            safe_filename = "voice.wav"
    elif audio_bytes.startswith(b"OggS") or safe_filename.endswith(".ogg"):
        content_type = "audio/ogg"
        if not safe_filename.endswith(".ogg"):
            safe_filename = "voice.ogg"

    for provider_name, url, key, model in providers:
        headers = {"Authorization": f"Bearer {key}"}
        files = {
            "file": (safe_filename, audio_bytes, content_type),
            "model": (None, model),
            "language": (None, "hi"),  # Biased towards Hindi / Indian English phonetics
            "prompt": (None, "Sakhi, Bosch Lab, Robotics Lab, Lalit Sir, Electrical Engineering Block, washroom, 307")
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, headers=headers, files=files)
                if response.status_code == 200:
                    data = response.json()
                    transcript = data.get("text", "").strip()
                    print(f"[Whisper STT Result via {provider_name}]: '{transcript}'")
                    return transcript
                else:
                    print(f"[Whisper STT {provider_name} Error]: HTTP {response.status_code} - {response.text}")
        except Exception as e:
            print(f"[Whisper STT {provider_name} Exception]: {e}")

    return ""
