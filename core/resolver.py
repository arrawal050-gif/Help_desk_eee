"""
core/resolver.py
<10ms fuzzy Hinglish alias & token matcher.
Resolves natural language queries to pano_id + spoken_hinglish response.
"""
import json
import re
from pathlib import Path
from typing import Optional, Dict, Any

_ENTITIES_PATH = Path(__file__).resolve().parent / "entities.json"

from core.persona import get_persona_identity_reply

# ── Graph Vertex -> Pano / Entity Mapping ─────────────────────────────────────
GRAPH_VERTEX_MAP: Dict[str, Dict[str, Any]] = {
    # 2nd Floor
    "n_2f_bosch": {"pano_id": "11_Bosch_lab", "target_id": "lab_bosch", "floor": 2},
    "n_2f_robotics": {"pano_id": "15_Robotics_Lab", "target_id": "lab_eyantra", "floor": 2},
    "n_2f_vlsi": {"pano_id": "15_Robotics_Lab", "target_id": "lab_eyantra", "floor": 2},
    "n_2f_eyantra": {"pano_id": "15_Robotics_Lab", "target_id": "lab_eyantra", "floor": 2},
    "n_2f_lab10": {"pano_id": "13_lab10", "target_id": "lab_10", "floor": 2},
    "n_2f_cmos": {"pano_id": "12_corridor_floor3", "target_id": "lab_cmos", "floor": 2},
    "n_2f_control": {"pano_id": "14_corridor_floor3", "target_id": "lab_control", "floor": 2},
    "n_2f_cr307": {"pano_id": "10_stairs_floor3", "target_id": "cr_307", "floor": 2},
    "n_2f_cr305": {"pano_id": "12_corridor_floor3", "target_id": "cr_305", "floor": 2},
    "n_2f_stairs": {"pano_id": "10_stairs_floor3", "target_id": "10_stairs_floor3", "floor": 2},
    "n_2f_wr_boys": {"pano_id": "10_stairs_floor3", "target_id": "wr_boys_2f", "target_branch": "to_washroom", "floor": 2},
    # 1st Floor
    "n_1f_mitsubishi": {"pano_id": "17_Mitsubishi_Lab", "target_id": "lab_mitsubishi", "floor": 1},
    "n_1f_lab9": {"pano_id": "09_lab9", "target_id": "lab_09", "floor": 1},
    "n_1f_lab5": {"pano_id": "08_corridor_floor2", "target_id": "lab_05", "floor": 1},
    "n_1f_lab6": {"pano_id": "08_corridor_floor2", "target_id": "lab_06", "floor": 1},
    "n_1f_lab7": {"pano_id": "08_corridor_floor2", "target_id": "lab_07", "floor": 1},
    "n_1f_lab8": {"pano_id": "08_corridor_floor2", "target_id": "lab_08", "floor": 1},
    "n_1f_cr207": {"pano_id": "07_stairs_floor2", "target_id": "cr_207", "floor": 1},
    "n_1f_cr208": {"pano_id": "07_stairs_floor2", "target_id": "cr_208", "floor": 1},
    "n_1f_cr209": {"pano_id": "07_stairs_floor2", "target_id": "cr_209", "floor": 1},
    "n_1f_cr210": {"pano_id": "07_stairs_floor2", "target_id": "cr_210", "floor": 1},
    "n_1f_stairs": {"pano_id": "07_stairs_floor2", "target_id": "07_stairs_floor2", "floor": 1},
    "n_1f_wr_girls": {"pano_id": "07_stairs_floor2", "target_id": "wr_girls_1f", "target_branch": "to_washroom", "floor": 1},
    # Ground Floor
    "n_g_entrance": {"pano_id": "16_Entrance_from_out_side", "target_id": "16_Entrance_from_out_side", "floor": 0},
    "n_g_foyer": {"pano_id": "01_main_entrance_floor1", "target_id": "01_main_entrance_floor1", "floor": 0},
    "n_g_lab1": {"pano_id": "02_lab1", "target_id": "lab_01", "floor": 0},
    "n_g_lab2": {"pano_id": "03_lab2", "target_id": "lab_02", "floor": 0},
    "n_g_lab3": {"pano_id": "04_lab3", "target_id": "lab_03", "floor": 0},
    "n_g_lab4": {"pano_id": "05_corridor_floor1", "target_id": "lab_04", "floor": 0},
    "n_g_corridor": {"pano_id": "05_corridor_floor1", "target_id": "05_corridor_floor1", "floor": 0},
    "n_g_cr107": {"pano_id": "06_stairs_floor1", "target_id": "cr_107", "floor": 0},
    "n_g_cr108": {"pano_id": "06_stairs_floor1", "target_id": "cr_108", "floor": 0},
    "n_g_stairs": {"pano_id": "06_stairs_floor1", "target_id": "06_stairs_floor1", "floor": 0},
    "n_g_wr_boys": {"pano_id": "06_stairs_floor1", "target_id": "wr_boys_gf", "target_branch": "to_washroom", "floor": 0},
}

# ── Index ─────────────────────────────────────────────────────────────────────
_INDEX = []   # list of {item, name_norm, aliases_norm}

def _norm(text: str) -> str:
    t = text.lower().strip()
    t = re.sub(r"[^\w\s\u0900-\u097F]", " ", t)
    return re.sub(r"\s+", " ", t).strip()

def _build_index():
    global _INDEX
    data = json.loads(_ENTITIES_PATH.read_text(encoding="utf-8"))
    _INDEX = []
    for cat in ("faculty", "laboratories", "classrooms", "washrooms"):
        for item in data.get(cat, []):
            aliases = list(item.get("aliases", []))
            if "id" in item:
                aliases.append(item["id"])
            if "pano_id" in item:
                aliases.append(item["pano_id"])
            if "linked_pano_id" in item:
                aliases.append(item["linked_pano_id"])
            _INDEX.append({
                "item": item,
                "name_norm": _norm(item["name"]),
                "aliases_norm": [_norm(a) for a in aliases],
            })

_build_index()


def get_staircase_branch_yaw(stair_node_id: str, final_destination_id: Optional[str] = None, is_washroom: bool = False) -> Optional[Dict[str, Any]]:
    """
    Universal Destination Goal Resolver for staircase landings.
    Reads dynamically from core.graph.DYNAMIC_LANDING_CALIBRATION so admin calibrations are 100% synced!
    """
    from core.graph import DYNAMIC_LANDING_CALIBRATION
    dest = (final_destination_id or "").lower()

    node_calib = DYNAMIC_LANDING_CALIBRATION.get(stair_node_id, {})
    branches = node_calib.get("branches", {})

    def _branch_res(branch_key: str, default_yaw: float, default_pitch: float) -> Dict[str, Any]:
        b = branches.get(branch_key, {})
        return {
            "yaw": float(b.get("yaw", default_yaw)),
            "pitch": float(b.get("pitch", default_pitch)),
            "branch": branch_key
        }

    # --- GROUND FLOOR STAIR FOOT (06_stairs_floor1) ---
    if stair_node_id == "06_stairs_floor1":
        if (is_washroom or "washroom" in dest or "toilet" in dest) and not ("girls" in dest or "1f" in dest or "2f" in dest):
            return _branch_res("to_washroom", 233.6, -1.1)
        return _branch_res("to_stairs", 170.0, 10.0)

    # --- 1ST FLOOR LANDING (07_stairs_floor2) ---
    if stair_node_id == "07_stairs_floor2":
        if (is_washroom or "washroom" in dest or "toilet" in dest) and ("girls" in dest or "1f" in dest or "floor1" in dest or "wr_girls" in dest):
            return _branch_res("to_washroom", 154.3, -4.1)
        if any(k in dest for k in ["mitsubishi", "17_", "lab9", "lab_09", "09_", "08_", "lab5", "lab6", "lab7", "lab8", "207", "208", "209", "210", "floor1", "first floor", "1f", "corridor"]):
            return _branch_res("to_corridor", 89.9, -8.0)
        return _branch_res("to_stairs", 7.6, -2.4)

    # --- 2ND FLOOR LANDING (10_stairs_floor3) ---
    if stair_node_id == "10_stairs_floor3":
        if is_washroom or "washroom" in dest or "toilet" in dest:
            return _branch_res("to_washroom", 153.6, -6.4)
        if "bosch" in dest or "11_" in dest:
            return _branch_res("to_bosch", 212.4, -0.8)
        return _branch_res("to_corridor", 91.9, -4.7)

    return None


# ── Stop words stripped before fuzzy matching ─────────────────────────────────
_STOP_WORDS = frozenset([
    "sakhi", "sakhee", "saakhi", "saki",
    "kahan", "kidhar", "jana", "jaana", "chahiye",
    "mujhe", "mujhko", "hame", "batao", "bata", "dikhao",
    "where", "is", "the", "a", "an", "to", "of",
    "show", "take", "go", "find", "hai", "he", "ka", "ki", "ke",
    "please", "kya", "aur",
])


def _normalize_for_fuzzy(text: str) -> str:
    """Strip stop-words & punctuation for cleaner fuzzy token comparison."""
    t = _norm(text)
    tokens = [w for w in t.split() if w not in _STOP_WORDS]
    return " ".join(tokens)


def _fuzzy_best(query_clean: str) -> Optional[tuple]:
    """
    Compare query tokens against all alias tokens using difflib ratio.
    Returns (score, entry) for best match above THRESHOLD, or None.
    THRESHOLD 0.82 catches: 'bosh'→'bosch', 'mitsubisi'→'mitsubishi', etc.
    """
    import difflib
    THRESHOLD = 0.82
    q_tokens = [w for w in query_clean.split() if len(w) > 2]
    if not q_tokens:
        return None

    best_score, best_entry = 0.0, None

    for entry in _INDEX:
        for alias in entry["aliases_norm"]:
            alias_tokens = alias.split()
            for qt in q_tokens:
                for at in alias_tokens:
                    if len(at) < 3:
                        continue
                    ratio = difflib.SequenceMatcher(None, qt, at).ratio()
                    if ratio > best_score:
                        best_score = ratio
                        best_entry = entry

    if best_score >= THRESHOLD and best_entry:
        return (best_score, best_entry)
    return None


def resolve(query: str) -> Optional[Dict[str, Any]]:
    """
    Return matched entity dict or None.
    Strategy:
      -1. Persona identity query check
       0. Direct Graph Vertex ID map check
       1. Exact / substring / containment alias match (weighted by length)
       2. Fuzzy phonetic token match via difflib (catches ASR mistranscriptions)
       3. Stop-word-filtered token overlap fallback
    """
    raw_q = query.strip().lower()

    # Pass -1: Persona Identity Queries
    persona_reply = get_persona_identity_reply(raw_q)
    if persona_reply:
        return {
            "id": "sakhi_persona",
            "name": "Sakhi (सखी)",
            "formal_name": "Sakhi - EEE Campus Kiosk AI Guide",
            "spoken_hinglish": persona_reply,
            "floor": 0,
            "pano_id": "01_main_entrance_floor1",
            "description": "Main A.R. Labs dwara viksit ek smart AI campus guide aur dost hoon."
        }

    # Pass 0: Graph Vertex Map direct lookup
    if raw_q in GRAPH_VERTEX_MAP:
        mapping = GRAPH_VERTEX_MAP[raw_q]
        for entry in _INDEX:
            it = entry["item"]
            if it.get("id") == mapping.get("target_id") or it.get("pano_id") == mapping.get("pano_id"):
                res = dict(it)
                if "target_branch" in mapping:
                    res["target_branch"] = mapping["target_branch"]
                return res

    q = _norm(query)
    best_score, best = 0, None

    # Pass 1: Exact / substring / containment match
    for entry in _INDEX:
        for alias in entry["aliases_norm"]:
            if q == alias:
                score = 1000 + len(alias) * 3
            elif alias in q:
                score = 500 + len(alias) * 3
            elif q in alias:
                score = len(q) * 2 - (len(alias) - len(q))
            else:
                score = 0

            if score > best_score:
                best_score, best = score, entry

        if q == entry["name_norm"]:
            score = 1000 + len(entry["name_norm"]) * 2
        elif entry["name_norm"] in q:
            score = 500 + len(entry["name_norm"]) * 2
        elif q in entry["name_norm"]:
            score = len(q) * 2 - (len(entry["name_norm"]) - len(q))
        else:
            score = 0

        if score > best_score:
            best_score, best = score, entry

    if best:
        return best["item"]

    # Pass 2: Fuzzy phonetic token matching (handles ASR mistranscriptions)
    # e.g. "bosh lab" → "bosch lab", "mitsubisi" → "mitsubishi"
    q_fuzzy = _normalize_for_fuzzy(query)
    fuzzy_result = _fuzzy_best(q_fuzzy)
    if fuzzy_result:
        _score, fuzzy_entry = fuzzy_result
        print(f"[Resolver Fuzzy] '{query}' → '{fuzzy_entry['item']['name']}' (ratio={_score:.2f})")
        return fuzzy_entry["item"]

    # Pass 3: Stop-word-filtered token overlap fallback
    q_tok = set(q_fuzzy.split())
    if q_tok:
        overlap_score, overlap_best = 0, None
        for entry in _INDEX:
            for alias in entry["aliases_norm"]:
                overlap = len(q_tok & set(alias.split()))
                if overlap > overlap_score:
                    overlap_score, overlap_best = overlap, entry
        if overlap_best:
            return overlap_best["item"]

    return None
