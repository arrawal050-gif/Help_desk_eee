"""core/config.py – Server & directory path constants."""
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
PANOS_DIR  = STATIC_DIR / "panos"
MAPS_DIR   = STATIC_DIR / "maps"

HOST       = "0.0.0.0"
PORT       = 8000
START_NODE = "16_Entrance_from_out_side"

TTS_VOICE  = "hi-IN-SwaraNeural"
TTS_PITCH  = "+18Hz"
TTS_RATE   = "+10%"
