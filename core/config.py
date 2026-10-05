"""core/config.py – Server & directory path constants."""
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
PANOS_DIR  = STATIC_DIR / "panos"
MAPS_DIR   = STATIC_DIR / "maps"

import os

HOST       = os.getenv("HOST", "0.0.0.0")
PORT       = int(os.getenv("PORT", "8000"))
START_NODE = os.getenv("START_NODE", "16_Entrance_from_out_side")

TTS_VOICE  = os.getenv("TTS_VOICE", "hi-IN-SwaraNeural")
TTS_PITCH  = os.getenv("TTS_PITCH", "+18Hz")
TTS_RATE   = os.getenv("TTS_RATE", "+10%")

