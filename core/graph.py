"""
core/graph.py
Canonical 17-node topological graph for SVVV EEE Block + Dijkstra path solver.
"""
import heapq
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# ── Locked Calibration: Strictly loaded from scene_calibration.json ───────────
CALIBRATION_FILE = Path(__file__).resolve().parent / "scene_calibration.json"

def load_locked_calibrations() -> Dict[str, Any]:
    if CALIBRATION_FILE.exists():
        with open(CALIBRATION_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    raise FileNotFoundError("Locked scene_calibration.json missing!")

LOCKED_SCENE_CALIBRATION: Dict[str, Any] = load_locked_calibrations()

STATIC_NODES_CALIBRATION: Dict[str, Dict[str, float]] = LOCKED_SCENE_CALIBRATION.get("static_nodes", {})
DYNAMIC_LANDING_CALIBRATION: Dict[str, Dict[str, Any]] = LOCKED_SCENE_CALIBRATION.get("dynamic_landing_nodes", {})

# Unified SCENE_CALIBRATION dictionary for general lookup and backward compatibility
SCENE_CALIBRATION: Dict[str, Any] = {}
for k, v in STATIC_NODES_CALIBRATION.items():
    SCENE_CALIBRATION[k] = {"yaw": v.get("yaw", 0.0), "pitch": v.get("pitch", 0.0)}

for k, v in DYNAMIC_LANDING_CALIBRATION.items():
    SCENE_CALIBRATION[k] = {
        "yaw": v.get("default_yaw", 0.0),
        "pitch": v.get("default_pitch", 0.0),
        "default": {"yaw": v.get("default_yaw", 0.0), "pitch": v.get("default_pitch", 0.0)},
        "branches": v.get("branches", {})
    }

# ── Node registry ─────────────────────────────────────────────────────────────
NODES: Dict[str, Dict[str, Any]] = {
    "16_Entrance_from_out_side": {
        "title": "College Main Campus Entrance (Exterior)",
        "floor": 0, "floor_name": "Ground Floor (Exterior)",
        "image": "/static/panos/16_Entrance_from_out_side.jpg",
        "yaw": 90.0, "pitch": 0.0,
        "edges": [("01_main_entrance_floor1", 2.5)],
    },
    "01_main_entrance_floor1": {
        "title": "Main Building Foyer / Entrance",
        "floor": 0, "floor_name": "Ground Floor",
        "image": "/static/panos/01_main_entrance_floor1.jpg",
        "yaw": 180.0, "pitch": 0.0,
        "edges": [
            ("16_Entrance_from_out_side", 2.5),
            ("02_lab1", 2.0),
            ("03_lab2", 2.0),
            ("05_corridor_floor1", 3.0),
        ],
    },
    "02_lab1": {
        "title": "Lab 1 (Basic Electrical & Electronics)",
        "floor": 0, "floor_name": "Ground Floor",
        "image": "/static/panos/02_lab1.jpg",
        "yaw": -90.0, "pitch": 0.0,
        "edges": [("01_main_entrance_floor1", 2.0)],
    },
    "03_lab2": {
        "title": "Lab 2 (Hardware Practical Lab)",
        "floor": 0, "floor_name": "Ground Floor",
        "image": "/static/panos/03_lab2.jpg",
        "yaw": -90.0, "pitch": 0.0,
        "edges": [("01_main_entrance_floor1", 2.0)],
    },
    "04_lab3": {
        "title": "Lab 3 (Systems & Software Lab)",
        "floor": 0, "floor_name": "Ground Floor",
        "image": "/static/panos/04_lab3.jpg",
        "yaw": -90.0, "pitch": 0.0,
        "edges": [("05_corridor_floor1", 2.2)],
    },
    "05_corridor_floor1": {
        "title": "Ground Floor Main Corridor",
        "floor": 0, "floor_name": "Ground Floor",
        "image": "/static/panos/05_corridor_floor1.jpg",
        "yaw": 180.0, "pitch": 0.0,
        "edges": [
            ("01_main_entrance_floor1", 3.0),
            ("04_lab3", 2.2),
            ("06_stairs_floor1", 3.2),
        ],
    },
    "06_stairs_floor1": {
        "title": "Ground Floor Main Staircase",
        "floor": 0, "floor_name": "Ground Floor",
        "image": "/static/panos/06_stairs_floor1.jpg",
        "yaw": 0.0, "pitch": 0.0,
        "edges": [
            ("05_corridor_floor1", 3.2),
            ("07_stairs_floor2", 4.5),
        ],
    },
    "07_stairs_floor2": {
        "title": "First Floor Staircase Landing",
        "floor": 1, "floor_name": "1st Floor",
        "image": "/static/panos/07_stairs_floor2.jpg",
        "yaw": 270.0, "pitch": 0.0,
        "edges": [
            ("06_stairs_floor1", 4.5),
            ("08_corridor_floor2", 3.0),
            ("10_stairs_floor3", 4.8),
        ],
    },
    "08_corridor_floor2": {
        "title": "First Floor Main Corridor",
        "floor": 1, "floor_name": "1st Floor",
        "image": "/static/panos/08_corridor_floor2.jpg",
        "yaw": 0.0, "pitch": 0.0,
        "edges": [
            ("07_stairs_floor2", 3.0),
            ("09_lab9", 2.2),
            ("17_Mitsubishi_Lab", 2.4),
        ],
    },
    "09_lab9": {
        "title": "Lab 9 (Algorithms & Simulation)",
        "floor": 1, "floor_name": "1st Floor",
        "image": "/static/panos/09_lab9.jpg",
        "yaw": -90.0, "pitch": 0.0,
        "edges": [("08_corridor_floor2", 2.2)],
    },
    "17_Mitsubishi_Lab": {
        "title": "Mitsubishi & PLC Automation Center of Excellence",
        "floor": 1, "floor_name": "1st Floor",
        "image": "/static/panos/17_Mitsubishi_Lab.jpg",
        "yaw": 0.0, "pitch": 0.0,
        "edges": [("08_corridor_floor2", 2.4)],
    },
    "10_stairs_floor3": {
        "title": "Second Floor Staircase Landing",
        "floor": 2, "floor_name": "2nd Floor",
        "image": "/static/panos/10_stairs_floor3.jpg",
        "yaw": 270.0, "pitch": 0.0,
        "edges": [
            ("07_stairs_floor2", 4.8),
            ("11_Bosch_lab", 2.5),
            ("12_corridor_floor3", 3.0),
        ],
    },
    "11_Bosch_lab": {
        "title": "Bosch Automotive & Embedded Systems Lab",
        "floor": 2, "floor_name": "2nd Floor",
        "image": "/static/panos/11_Bosch_lab.jpg",
        "yaw": 180.0, "pitch": 0.0,
        "edges": [("10_stairs_floor3", 2.5)],
    },
    "12_corridor_floor3": {
        "title": "Second Floor Corridor (outside Lab 10)",
        "floor": 2, "floor_name": "2nd Floor",
        "image": "/static/panos/12_corridor_floor3.jpg",
        "yaw": 0.0, "pitch": 0.0,
        "edges": [
            ("10_stairs_floor3", 3.0),
            ("13_lab10", 2.0),
            ("14_corridor_floor3", 3.0),
        ],
    },
    "13_lab10": {
        "title": "Lab 10 (VLSI & Computing)",
        "floor": 2, "floor_name": "2nd Floor",
        "image": "/static/panos/13_lab10.jpg",
        "yaw": -90.0, "pitch": 0.0,
        "edges": [("12_corridor_floor3", 2.0)],
    },
    "14_corridor_floor3": {
        "title": "Second Floor Corridor (outside Robotics Lab)",
        "floor": 2, "floor_name": "2nd Floor",
        "image": "/static/panos/14_corridor_floor3.jpg",
        "yaw": 0.0, "pitch": 0.0,
        "edges": [
            ("12_corridor_floor3", 3.0),
            ("15_Robotics_Lab", 2.5),
        ],
    },
    "15_Robotics_Lab": {
        "title": "Robotics & e-Yantra / VLSI Lab",
        "floor": 2, "floor_name": "2nd Floor",
        "image": "/static/panos/15_Robotics_Lab.jpg",
        "yaw": 0.0, "pitch": 0.0,
        "edges": [("14_corridor_floor3", 2.5)],
    },
}

# Apply LOCKED_SCENE_CALIBRATION yaw/pitch onto node registry
for _id, _calib in SCENE_CALIBRATION.items():
    if _id in NODES and isinstance(_calib, dict):
        _y = _calib.get("yaw") if "yaw" in _calib else _calib.get("default", {}).get("yaw", 0.0)
        _p = _calib.get("pitch") if "pitch" in _calib else _calib.get("default", {}).get("pitch", 0.0)
        NODES[_id]["yaw"] = _y
        NODES[_id]["pitch"] = _p

STAIRCASE_NODES = {
    "06_stairs_floor1", "07_stairs_floor2", "10_stairs_floor3"
}

# Floor name map
FLOOR_NAMES = {0: "Ground Floor", 1: "1st Floor", 2: "2nd Floor"}


def dijkstra(start: str, target: str) -> Optional[List[str]]:
    """Return ordered list of node IDs from start -> target, or None."""
    if start not in NODES or target not in NODES:
        return None
    if start == target:
        return [start]

    dist: Dict[str, float] = {start: 0.0}
    prev: Dict[str, Optional[str]] = {start: None}
    pq = [(0.0, start)]

    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, float("inf")):
            continue
        if u == target:
            break
        for v, w in NODES[u]["edges"]:
            nd = d + w
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))

    # Reconstruct
    path, cur = [], target
    while cur is not None:
        path.append(cur)
        cur = prev.get(cur)
    path.reverse()
    return path if path[0] == start else None


def build_route(start: str, target: str, target_branch: Optional[str] = None, final_destination_id: Optional[str] = None) -> Dict[str, Any]:
    """Return full route dict with steps, floor-transition flags, etc."""
    from core.resolver import get_staircase_branch_yaw

    path = dijkstra(start, target) or [start, target]
    steps = []
    for i, node_id in enumerate(path):
        node = NODES[node_id]
        is_final = (i == len(path) - 1)
        next_node = NODES.get(path[i + 1]) if not is_final else None
        floor_transition = False
        floor_direction = None
        if next_node and next_node["floor"] != node["floor"]:
            floor_transition = True
            floor_direction = "up" if next_node["floor"] > node["floor"] else "down"
            to_floor = FLOOR_NAMES.get(next_node["floor"], next_node["floor_name"])
        else:
            to_floor = None

        step_yaw = node["yaw"]
        step_pitch = node["pitch"]

        # ── Destination-Aware Staircase Branch Resolution ──────────────────────
        if node_id in STAIRCASE_NODES:
            dest_key = f"{final_destination_id or ''} {target or ''}"
            is_wr = (target_branch == "to_washroom") or ("washroom" in dest_key.lower()) or ("toilet" in dest_key.lower())
            stair_branch = get_staircase_branch_yaw(node_id, dest_key, is_washroom=is_wr)
            if stair_branch:
                step_yaw = stair_branch["yaw"]
                step_pitch = stair_branch["pitch"]
        # ── Dynamic Branch Calculation on Landing Nodes (Fallback) ─────────────
        elif node_id in DYNAMIC_LANDING_CALIBRATION:
            landing_entry = DYNAMIC_LANDING_CALIBRATION[node_id]
            step_yaw = landing_entry.get("default_yaw", step_yaw)
            step_pitch = landing_entry.get("default_pitch", step_pitch)
            branches = landing_entry.get("branches", {})

            if is_final:
                # Arrived at staircase landing: check destination/washroom branch
                matched = None
                for b_key, b_info in branches.items():
                    if target_branch and (b_key == target_branch or b_info.get("target_id") == target_branch):
                        matched = b_info
                        break
                    if b_info.get("target_id") == target:
                        matched = b_info
                        break
                if matched:
                    step_yaw = matched.get("yaw", step_yaw)
                    step_pitch = matched.get("pitch", step_pitch)
            elif next_node:
                # In transit through staircase landing: frame next immediate route node
                next_node_id = path[i + 1]
                matched = None
                for b_key, b_info in branches.items():
                    if b_info.get("target_id") == next_node_id:
                        matched = b_info
                        break
                    if next_node_id in b_info.get("next_nodes", []):
                        matched = b_info
                        break
                if matched:
                    step_yaw = matched.get("yaw", step_yaw)
                    step_pitch = matched.get("pitch", step_pitch)
        elif isinstance(calib_entry := SCENE_CALIBRATION.get(node_id), dict) and "branches" in calib_entry:
            if is_final and target_branch and target_branch in calib_entry["branches"]:
                b_info = calib_entry["branches"][target_branch]
                step_yaw = b_info.get("yaw", step_yaw)
                step_pitch = b_info.get("pitch", step_pitch)
            elif next_node:
                next_node_id = path[i + 1]
                for b_key, b_info in calib_entry["branches"].items():
                    if next_node_id in b_info.get("next_nodes", []) or b_info.get("target_id") == next_node_id:
                        step_yaw = b_info.get("yaw", step_yaw)
                        step_pitch = b_info.get("pitch", step_pitch)
                        break

        steps.append({
            "index": i,
            "total": len(path),
            "pano_id": node_id,
            "title": node["title"],
            "floor": node["floor"],
            "floor_name": node["floor_name"],
            "image": node["image"],
            "yaw": step_yaw,
            "pitch": step_pitch,
            "target_branch": target_branch if is_final else None,
            "is_staircase": node_id in STAIRCASE_NODES,
            "floor_transition": floor_transition,
            "floor_direction": floor_direction,
            "to_floor_name": to_floor,
            "is_final": is_final,
        })

    total_dist = sum(
        next(w for v, w in NODES[path[i]]["edges"] if v == path[i + 1])
        for i in range(len(path) - 1)
        if path[i] in NODES and any(v == path[i + 1] for v, _ in NODES[path[i]]["edges"])
    )
    return {"path": path, "total_distance": round(total_dist, 2), "steps": steps}
