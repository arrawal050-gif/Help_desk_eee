"""
core/tts.py
Neural Hinglish TTS engine using Microsoft Edge TTS.
Voice: hi-IN-SwaraNeural | Pitch: +18Hz | Rate: +10%
Includes MD5-keyed in-memory cache for <5ms repeat latency.
"""
import asyncio
import base64
import hashlib
import re
from typing import Optional

import edge_tts

from core.config import TTS_VOICE, TTS_PITCH, TTS_RATE
from core.persona import format_persona_response

_CACHE: dict = {}


def _clean(text: str) -> str:
    """Strip markdown, HTML, emoji from TTS input while preserving Sakhi's polite tone."""
    formatted = format_persona_response(text)
    t = re.sub(r"[\U00010000-\U0010ffff\U0001F300-\U0001F9FF\U00002600-\U000027BF]+", "", formatted)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"[*`#_~]", "", t)
    return " ".join(t.split()).strip()


async def synthesize(
    text: str,
    voice: str = TTS_VOICE,
    pitch: str = TTS_PITCH,
    rate: str = TTS_RATE,
) -> str:
    """Return base64-encoded MP3 string for the given text."""
    clean = _clean(text)
    key = hashlib.md5(f"{voice}:{pitch}:{rate}:{clean}".encode()).hexdigest()
    if key in _CACHE:
        return _CACHE[key]

    try:
        comm = edge_tts.Communicate(clean, voice=voice, pitch=pitch, rate=rate)
        chunks = b""
        async for c in comm.stream():
            if c["type"] == "audio":
                chunks += c["data"]
        if chunks:
            b64 = base64.b64encode(chunks).decode()
            _CACHE[key] = b64
            return b64
    except Exception as e:
        print(f"[TTS WARN] {e} – retrying without prosody…")

    try:
        comm2 = edge_tts.Communicate(clean, voice=voice)
        chunks = b""
        async for c in comm2.stream():
            if c["type"] == "audio":
                chunks += c["data"]
        if chunks:
            b64 = base64.b64encode(chunks).decode()
            _CACHE[key] = b64
            return b64
    except Exception as e2:
        print(f"[TTS ERROR] {e2}")

    return ""


async def synthesize_speech_base64(
    text: str,
    voice: str = TTS_VOICE,
    pitch: str = TTS_PITCH,
    rate: str = TTS_RATE,
) -> str:
    """Synthesize speech using configured prosody (hi-IN-SwaraNeural by default)."""
    return await synthesize(text, voice=voice, pitch=pitch, rate=rate)


# ── Institutional Facility Directory ──────────────────────────────────────────
INSTITUTIONAL_DETAILS: dict = {
    "lab_bosch": {
        "formal_name": "Bosch Automotive & Embedded Systems Centre of Excellence",
        "description": "yahan par advanced automotive embedded systems, CAN protocol aur ECU diagnostics par practical work hota hai.",
    },
    "lab_mitsubishi": {
        "formal_name": "Mitsubishi Electric & PLC Industrial Automation Lab",
        "description": "yahan par industrial PLC programming, SCADA systems aur factory automation ka practical work hota hai.",
    },
    "lab_eyantra": {
        "formal_name": "IIT Bombay e-Yantra Robotics & VLSI Research Lab",
        "description": "yahan par autonomous robots, embedded microcontrollers aur VLSI chip design ka practical training aur research work hota hai.",
    },
    "lab_01": {
        "formal_name": "Basic Electrical & Electronics Engineering Laboratory",
        "description": "yahan par circuit theory, AC/DC machines aur electrical measurements ke practical experiments conduct hote hain.",
    },
    "lab_02": {
        "formal_name": "Hardware Practical & Electronic Devices Laboratory",
        "description": "yahan par semiconductor devices, amplifiers aur hardware test benches par hands-on experiments hote hain.",
    },
    "lab_03": {
        "formal_name": "Systems & Simulation Software Laboratory",
        "description": "yahan par power systems modeling, MATLAB software aur circuit simulation practicals conduct kiye jaate hain.",
    },
    "lab_04": {
        "formal_name": "Digital Electronics & Microprocessors Laboratory",
        "description": "yahan par digital logic design, microprocessors aur sequential circuits ka practical work hota hai.",
    },
    "lab_05": {
        "formal_name": "Software Engineering & High Performance Computing Lab",
        "description": "yahan par programming algorithms aur engineering software simulation practicals conduct hote hain.",
    },
    "lab_06": {
        "formal_name": "Signal Processing & Telecommunication Laboratory",
        "description": "yahan par analog and digital signals, spectrum analyzers aur communication hardware practicals hote hain.",
    },
    "lab_07": {
        "formal_name": "Digital Signal Processing & Computational Analysis Lab",
        "description": "yahan par DSP processor programming aur signal filtering algorithms ka practical work hota hai.",
    },
    "lab_08": {
        "formal_name": "Computer Architecture & Microarchitecture Lab",
        "description": "yahan par processor design, pipelining aur computer architecture practicals hote hain.",
    },
    "lab_09": {
        "formal_name": "Algorithms, Simulation & Numerical Modeling Lab",
        "description": "yahan par computational algorithm modeling aur engineering software simulations conduct kiye jaate hain.",
    },
    "lab_10": {
        "formal_name": "VLSI Design, Computing & Digital Systems Laboratory",
        "description": "yahan par FPGA architecture, VHDL simulations aur VLSI chip design practicals hote hain.",
    },
    "lab_cmos": {
        "formal_name": "CMOS Microelectronics & Semiconductor Research Lab",
        "description": "yahan par semiconductor device physics, microelectronics aur IC layout design experiments conduct hote hain.",
    },
    "lab_control": {
        "formal_name": "Control Systems & Industrial Instrumentation Laboratory",
        "description": "yahan par feedback control mechanisms, servomotors aur process instrumentation practicals hote hain.",
    },
    "lab_microcontroller": {
        "formal_name": "Advanced Microcontrollers & Embedded Systems Lab",
        "description": "yahan par 8051, ARM Cortex aur IoT sensor interfacing practical work conduct kiya jata hai.",
    },
    "wr_boys_gf": {
        "formal_name": "Ground Floor Boys Washroom Facility",
        "description": "yeh Ground Floor main staircase ke theek bagal mein sthit hai.",
    },
    "wr_girls_1f": {
        "formal_name": "First Floor Girls Washroom Facility",
        "description": "yeh First Floor staircase landing ke theek samne sthit hai.",
    },
    "wr_boys_2f": {
        "formal_name": "Second Floor Boys Washroom Facility",
        "description": "yeh Second Floor staircase landing ke theek bagal mein sthit hai.",
    },
}


def generate_arrival_speech(entity: dict) -> str:
    """
    Context-aware polymorphic arrival dialogue generator.
    Tailors arrival announcement based on entity category (faculty vs lab vs classroom vs amenity).
    """
    category = entity.get("category", "lab").lower()
    dest_id = entity.get("id", "")
    inst_info = INSTITUTIONAL_DETAILS.get(dest_id, {})

    name = entity.get("formal_name") or inst_info.get("formal_name") or entity.get("name", "Destination")
    floor = entity.get("floor", 0)

    floor_str = {
        0: "Ground Floor",
        1: "First Floor",
        2: "Second Floor",
        3: "Third Floor"
    }.get(floor, "is floor")

    if category == "faculty":
        cabin = entity.get("cabin_room", "cabin")
        aliases_str = " ".join(entity.get("aliases", [])).lower()
        honorific = "ma'am" if any(w in aliases_str for w in ["maam", "madam", "महिला"]) else "sir"
        return (
            f"Hum pahunch gaye hain. Yeh {name} {honorific} ka {cabin} hai, jo ki {floor_str} par sthit hai. "
            f"Aap unse unke consultation hours ke dauran yahan mil sakte hain."
        )

    elif category == "lab":
        description = entity.get(
            "description",
            inst_info.get("description", "yahan par advanced practicals aur hands-on project work conduct kiye jaate hain.")
        )
        return (
            f"Hum pahunch gaye hain. Yeh hamara {name} hai, jo ki {floor_str} par sthit hai. "
            f"{description}"
        )

    elif category == "classroom":
        return (
            f"Hum pahunch gaye hain. Yeh {name} hai, jo ki {floor_str} par sthit hai. "
            f"Yahan regular departmental lectures aur tutorial sessions conduct hote hain."
        )

    elif category in ("amenity", "washroom"):
        name_clean = name[:-9].strip() if name.lower().endswith("facility") else name
        return f"Hum pahunch gaye hain. Yeh {floor_str} par {name_clean} facility hai."

    # General Fallback
    return f"Hum pahunch gaye hain. Yeh {name} hai, jo ki {floor_str} par sthit hai."


async def generate_tour_segments(entity: dict, route_nodes: list) -> list:
    """
    Generates 4 distinct, synchronized audio segments mapped to physical node transitions.
    Pacing is calm, warm, and accessible for freshers, parents, and campus guests.
    Returns list of objects:
    [
      { "id": "entry", "phase": "entry", "audio_base64": "...", "text": "...", "nodes": [...], "node_sequence": [...] },
      { "id": "stairs", "phase": "stairs", "audio_base64": "...", "text": "...", "nodes": [...], "node_sequence": [...] },
      { "id": "approach", "phase": "approach", "audio_base64": "...", "text": "...", "nodes": [...], "node_sequence": [...] },
      { "id": "arrival", "phase": "showcase", "audio_base64": "...", "text": "...", "nodes": [...], "node_sequence": [...] }
    ]
    """
    category = entity.get("category", "lab").lower()
    target_floor = entity.get("floor", 0)
    floor_hindi = {0: "Ground Floor", 1: "First Floor", 2: "Second Floor"}.get(target_floor, f"{target_floor}th Floor")
    
    dest_id = entity.get("id", "")
    dest_pano = entity.get("target_pano_id") or entity.get("linked_pano_id") or entity.get("pano_id") or (route_nodes[-1] if route_nodes else "01_main_entrance_floor1")
    
    # Institutional details lookup
    inst_info = INSTITUTIONAL_DETAILS.get(dest_id, {})
    full_name = entity.get("formal_name") or inst_info.get("formal_name") or entity.get("name", "Campus Destination")
    room_short = entity.get("name", full_name)
    desc = entity.get("description") or inst_info.get("description") or "yahan par specialized engineering projects aur practicals conduct kiye jaate hain."

    # Node segmentation
    entry_candidates = ("16_Entrance_from_out_side", "01_main_entrance_floor1", "05_corridor_floor1")
    entry_nodes = [n for n in route_nodes if n in entry_candidates and n != dest_pano]
    if not entry_nodes:
        entry_nodes = [route_nodes[0]] if route_nodes else ["16_Entrance_from_out_side"]

    stair_nodes = [n for n in route_nodes if "stairs" in n and n != dest_pano]
    corridor_nodes = [n for n in route_nodes if n not in entry_nodes and n not in stair_nodes and n != dest_pano]

    segments = []

    # ── Phase 1: Entry ──────────────────────────────────────────────────────────
    if target_floor > 0 or len(route_nodes) > 2:
        entry_text = "Sabse pehle, chaliye hum main entrance ke zariye building ke ground floor corridor mein aage badhte hain."
    else:
        entry_text = "Sabse pehle, chaliye main entrance ke zariye building ke andar chalte hain."

    segments.append({
        "id": "entry",
        "phase": "entry",
        "text": entry_text,
        "nodes": entry_nodes,
        "node_sequence": entry_nodes,
    })

    # ── Phase 2: Transition ─────────────────────────────────────────────────────
    if target_floor > 0 and stair_nodes:
        stairs_text = f"Ab yahan se hum seedhiyan chadkar {floor_hindi} ki taraf chalte hain."
        segments.append({
            "id": "stairs",
            "phase": "stairs",
            "text": stairs_text,
            "nodes": stair_nodes,
            "node_sequence": stair_nodes,
        })
    else:
        transition_nodes = [n for n in route_nodes if n in ("01_main_entrance_floor1", "05_corridor_floor1") and n != dest_pano]
        if not transition_nodes:
            transition_nodes = entry_nodes[-1:]
        segments.append({
            "id": "transition",
            "phase": "transition",
            "text": "Ab hum corridor se aage badhenge.",
            "nodes": transition_nodes,
            "node_sequence": transition_nodes,
        })

    # ── Phase 3: Approach ───────────────────────────────────────────────────────
    if target_floor > 0:
        if stair_nodes and not corridor_nodes:
            # Destination is directly off the landing (e.g. Bosch Lab, Classroom 307, 1F Girls Washroom)
            landing_node = stair_nodes[-1]
            approach_nodes = [landing_node]
            if "bosch" in dest_id.lower() or "bosch" in room_short.lower():
                approach_text = f"{floor_hindi} landing par aane ke baad, seedhe haath par {room_short} ka darwaza hai."
            elif "washroom" in dest_id.lower():
                approach_text = f"{floor_hindi} landing par aane ke baad, samne washroom ka rasta hai."
            elif category == "faculty":
                approach_text = f"{floor_hindi} landing par aane ke baad, samne {room_short} ke cabin ki taraf chalte hain."
            else:
                approach_text = f"{floor_hindi} landing par aane ke baad, samne {room_short} ka pravesh dwar hai."
        elif corridor_nodes:
            # Destination along the corridor (Robotics Lab, Lab 10, Mitsubishi, etc.)
            approach_nodes = corridor_nodes
            if category == "faculty":
                approach_text = f"{floor_hindi} landing par aane ke baad, corridor mein aage badhte hue {room_short} ke cabin ki taraf chalte hain."
            else:
                approach_text = f"{floor_hindi} landing par aane ke baad, corridor mein aage badhte hue {room_short} ki taraf chalte hain."
        else:
            approach_nodes = [dest_pano]
            approach_text = f"{floor_hindi} par pahunchne ke baad, seedhe samne {room_short} ka pravesh dwar hai."
    else:
        # Ground floor destination
        if "washroom" in dest_id.lower():
            approach_nodes = ["06_stairs_floor1"] if "06_stairs_floor1" in route_nodes else entry_nodes[-1:]
            approach_text = "Ground Floor stairs ke theek paas boys washroom ka rasta hai."
        elif "lab1" in dest_pano or "02_lab1" in dest_pano:
            approach_nodes = ["01_main_entrance_floor1"]
            approach_text = "Main entrance foyer mein enter karte hi left side par Lab 1 ka darwaza hai."
        elif "lab2" in dest_pano or "03_lab2" in dest_pano:
            approach_nodes = ["01_main_entrance_floor1"]
            approach_text = "Main entrance foyer mein enter karte hi right side par Lab 2 sthit hai."
        else:
            approach_nodes = corridor_nodes if corridor_nodes else entry_nodes[-1:]
            approach_text = f"Corridor se aage badhte hi, samne {room_short} ka darwaza dikhai dega."

    segments.append({
        "id": "approach",
        "phase": "approach",
        "text": approach_text,
        "nodes": approach_nodes,
        "node_sequence": approach_nodes,
    })

    # ── Phase 4: Showcase (Destination Arrival) ─────────────────────────────────
    arrival_text = generate_arrival_speech(entity)

    segments.append({
        "id": "arrival",
        "phase": "showcase",
        "text": arrival_text,
        "nodes": [dest_pano],
        "node_sequence": [dest_pano],
    })

    # Synthesize audio in parallel for all segments via edge-tts (hi-IN-SwaraNeural)
    tasks = [synthesize_speech_base64(seg["text"]) for seg in segments]
    audios = await asyncio.gather(*tasks)
    for seg, aud in zip(segments, audios):
        seg["audio_base64"] = aud

    return segments
