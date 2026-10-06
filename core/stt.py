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

    if groq_key:
        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {groq_key}"}
        model = "whisper-large-v3"
    elif openai_key:
        url = "https://api.openai.com/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {openai_key}"}
        model = "whisper-1"
    else:
        raise ValueError("Neither GROQ_API_KEY nor OPENAI_API_KEY found in environment.")

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

    files = {
        "file": (safe_filename, audio_bytes, content_type),
        "model": (None, model),
        "language": (None, "hi"),  # Biased towards Hindi / Indian English phonetics
        "prompt": (None, "Sakhi, Bosch Lab, Robotics Lab, Lalit Sir, Electrical Engineering Block, washroom, 307")
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(url, headers=headers, files=files)
        response.raise_for_status()
        data = response.json()
        transcript = data.get("text", "").strip()
        print(f"[Whisper STT Result]: '{transcript}'")
        return transcript
