"""
main.py – Unified FastAPI server for Sakhi EEE Campus Kiosk.
Serves static files, handles /api/query (resolve + route + TTS), /api/health,
and live visual calibration admin endpoints (/admin, /api/calibration).
"""
import json
import re
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.config import BASE_DIR, STATIC_DIR, HOST, PORT, START_NODE
from core.graph import NODES, SCENE_CALIBRATION, build_route
from core.resolver import resolve
from core.tts import synthesize, generate_tour_segments

app = FastAPI(title="Sakhi EEE Kiosk", version="2.0.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

CALIBRATION_FILE = BASE_DIR / "core" / "scene_calibration.json"
if not CALIBRATION_FILE.exists() and Path("core/scene_calibration.json").exists():
    CALIBRATION_FILE = Path("core/scene_calibration.json")

# ── Static files ──────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/admin")
@app.get("/admin/")
@app.get("/admin.html")
@app.get("/calibrate.html")
async def admin_page():
    return FileResponse(str(STATIC_DIR / "calibrate.html"))


@app.get("/api/health")
async def health():
    return {"status": "ok", "nodes": len(NODES), "system": "Sakhi EEE Kiosk v2"}


# ── Calibration endpoints ──────────────────────────────────────────────────────
@app.get("/api/calibration")
def get_calibration():
    if not CALIBRATION_FILE.exists():
        raise HTTPException(status_code=404, detail="Calibration file not found")
    with open(CALIBRATION_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/calibration/nodes")
def get_calibration_nodes():
    """Returns list of nodes with full metadata (title, floor, image) plus current calibration."""
    calib = {}
    for node_id, data in NODES.items():
        calib[node_id] = {"yaw": data.get("yaw", 0.0), "pitch": data.get("pitch", 0.0)}

    if CALIBRATION_FILE.exists():
        try:
            with open(CALIBRATION_FILE, "r", encoding="utf-8") as f:
                _raw = json.load(f)
                if "static_nodes" in _raw or "dynamic_landing_nodes" in _raw:
                    for _k, _v in _raw.get("static_nodes", {}).items():
                        if _k in NODES:
                            calib[_k] = {"yaw": _v.get("yaw", 0.0), "pitch": _v.get("pitch", 0.0)}
                    for _k, _v in _raw.get("dynamic_landing_nodes", {}).items():
                        if _k in NODES:
                            calib[_k] = {
                                "yaw": _v.get("default_yaw", 0.0),
                                "pitch": _v.get("default_pitch", 0.0),
                                "default": {"yaw": _v.get("default_yaw", 0.0), "pitch": _v.get("default_pitch", 0.0)},
                                "branches": _v.get("branches", {})
                            }
                else:
                    for _k, _v in _raw.items():
                        if _k in NODES and isinstance(_v, dict):
                            calib[_k] = _v
        except Exception:
            pass

    node_list = []
    for node_id, data in NODES.items():
        node_calib = calib.get(node_id, {})
        if "default" in node_calib:
            yaw = node_calib["default"].get("yaw", data.get("yaw", 0.0))
            pitch = node_calib["default"].get("pitch", data.get("pitch", 0.0))
        else:
            yaw = node_calib.get("yaw", data.get("yaw", 0.0))
            pitch = node_calib.get("pitch", data.get("pitch", 0.0))

        item = {
            "id": node_id,
            "title": data.get("title", node_id),
            "floor": data.get("floor", 0),
            "floor_name": data.get("floor_name", "Ground Floor"),
            "image": data.get("image", f"/static/panos/{node_id}.jpg"),
            "yaw": float(yaw),
            "pitch": float(pitch),
        }
        if "branches" in node_calib:
            item["branches"] = node_calib["branches"]
        if "default" in node_calib:
            item["default"] = node_calib["default"]

        node_list.append(item)

    # Sort nodes logically: Exterior first, then Floor 0, 1, 2, ordered by id
    node_list.sort(key=lambda n: (n["floor"], n["id"]))
    return {"nodes": node_list, "calibration": calib}


@app.post("/api/calibration/save")
async def save_calibration(request: Request, admin_override: bool = False):
    """
    Guarded save endpoint. Requires admin_override parameter or header.
    Writes updated calibration JSON to disk preserving static_nodes and dynamic_landing_nodes:
    1. core/scene_calibration.json
    2. Synchronizes static/js/viewer.js
    3. Synchronizes core/scene_calibration_locked_backup.json
    4. Updates in-memory NODES and SCENE_CALIBRATION immediately
    """
    try:
        data = await request.json()
        if not isinstance(data, dict):
            raise HTTPException(status_code=400, detail="Data must be an object of node_id -> {yaw, pitch}")

        # Guard: Check for explicit admin override
        has_override = (
            admin_override or
            request.headers.get("x-admin-override") == "true" or
            data.get("admin_override") is True or
            data.get("_admin_override") is True
        )
        if not has_override:
            raise HTTPException(
                status_code=403,
                detail="Calibration dataset is permanently LOCKED. Admin override parameter (?admin_override=true or header 'X-Admin-Override: true') required to modify orientations."
            )

        # Preserve existing locked branches if request omitted them
        existing_calib = {}
        if CALIBRATION_FILE.exists():
            try:
                with open(CALIBRATION_FILE, "r", encoding="utf-8") as f:
                    existing_calib = json.load(f)
            except Exception:
                pass

        new_static = dict(existing_calib.get("static_nodes", {}))
        new_dynamic = dict(existing_calib.get("dynamic_landing_nodes", {}))

        for k, v in data.items():
            if k in ["_metadata", "admin_override", "_admin_override", "static_nodes", "dynamic_landing_nodes"] or not isinstance(v, dict):
                continue
            if k in new_dynamic or "branches" in v:
                curr = new_dynamic.get(k, {})
                def_yaw = float(v.get("default", {}).get("yaw", v.get("default_yaw", v.get("yaw", curr.get("default_yaw", 0.0)))))
                def_pitch = float(v.get("default", {}).get("pitch", v.get("default_pitch", v.get("pitch", curr.get("default_pitch", 0.0)))))
                branches = dict(curr.get("branches", {}))
                if "branches" in v:
                    for b_k, b_v in v["branches"].items():
                        branches[b_k] = {
                            "target_id": b_v.get("target_id", branches.get(b_k, {}).get("target_id", "")),
                            "yaw": round(float(b_v.get("yaw", 0.0)), 1),
                            "pitch": round(float(b_v.get("pitch", 0.0)), 1),
                        }
                new_dynamic[k] = {
                    "default_yaw": round(def_yaw, 1),
                    "default_pitch": round(def_pitch, 1),
                    "branches": branches
                }
            else:
                new_static[k] = {
                    "yaw": round(float(v.get("yaw", 0.0)), 1),
                    "pitch": round(float(v.get("pitch", 0.0)), 1)
                }

        normalized = {
            "static_nodes": new_static,
            "dynamic_landing_nodes": new_dynamic
        }

        # 1. Save canonical JSON with indent=2
        with open(CALIBRATION_FILE, "w", encoding="utf-8") as f:
            json.dump(normalized, f, indent=2)

        # 2. Synchronize static/js/viewer.js on disk (as Object.freeze)
        viewer_js = STATIC_DIR / "js" / "viewer.js"
        if viewer_js.exists():
            v_content = viewer_js.read_text(encoding="utf-8")
            replacement_js = f"// Auto-synced from core/scene_calibration.json - LOCKED\nexport const SCENE_CALIBRATION = Object.freeze({json.dumps(normalized, indent=2)});"
            v_content = re.sub(
                r"(?://[^\n]*\n)?export const SCENE_CALIBRATION = (?:Object\.freeze\()?\{.*?\}(?:\);|;)",
                replacement_js,
                v_content,
                flags=re.DOTALL
            )
            viewer_js.write_text(v_content, encoding="utf-8")

        # 3. Synchronize backup copy
        backup_file = BASE_DIR / "core" / "scene_calibration_locked_backup.json"
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(normalized, f, indent=2)

        # 4. Update in-memory graph objects immediately (no restart strictly required)
        from core import graph
        graph.LOCKED_SCENE_CALIBRATION = normalized
        graph.STATIC_NODES_CALIBRATION = new_static
        graph.DYNAMIC_LANDING_CALIBRATION = new_dynamic
        graph.SCENE_CALIBRATION.clear()
        for _k, _v in new_static.items():
            graph.SCENE_CALIBRATION[_k] = dict(_v)
            if _k in graph.NODES:
                graph.NODES[_k]["yaw"] = _v.get("yaw", 0.0)
                graph.NODES[_k]["pitch"] = _v.get("pitch", 0.0)
        for _k, _v in new_dynamic.items():
            graph.SCENE_CALIBRATION[_k] = {
                "yaw": _v.get("default_yaw", 0.0),
                "pitch": _v.get("default_pitch", 0.0),
                "default": {"yaw": _v.get("default_yaw", 0.0), "pitch": _v.get("default_pitch", 0.0)},
                "branches": _v.get("branches", {})
            }
            if _k in graph.NODES:
                graph.NODES[_k]["yaw"] = _v.get("default_yaw", 0.0)
                graph.NODES[_k]["pitch"] = _v.get("default_pitch", 0.0)

        return {
            "status": "success",
            "message": "Calibrations successfully saved to disk!",
            "saved_count": len(normalized),
            "calibration": normalized
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── WebSocket Dispatcher for Hands-Free Kiosk ─────────────────────────────────
active_connections: list[WebSocket] = []


@app.websocket("/ws/kiosk")
async def kiosk_websocket(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            text = await websocket.receive_text()
            try:
                msg = json.loads(text)
                action = msg.get("action")
                if action == "voice_query":
                    q = msg.get("query", "")
                    if q:
                        await execute_voice_query_and_broadcast(q)
                elif action == "ping":
                    await websocket.send_json({"action": "pong"})
            except Exception:
                pass
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        if websocket in active_connections:
            active_connections.remove(websocket)


async def broadcast_kiosk_command(data: dict):
    """Broadcast JSON command to all active kiosk WebSocket connections."""
    for ws in list(active_connections):
        try:
            await ws.send_json(data)
        except Exception:
            if ws in active_connections:
                active_connections.remove(ws)


async def execute_voice_query_and_broadcast(query: str, start: Optional[str] = START_NODE) -> dict:
    """Core pipeline: resolve -> route -> synthesize -> broadcast to frontend kiosk."""
    start_node = start if start in NODES else START_NODE
    entity = resolve(query)

    # 1. Unresolved query: Do NOT silently route to entrance foyer. Return helpful clarification prompt.
    if not entity:
        spoken = "Sakhi ko samajh nahi aaya. Kripya lab, room number ya teacher ka naam dobara boliye."
        audio = await synthesize(spoken)
        packet = {
            "action": "not_found",
            "query": query,
            "matched": False,
            "display_title": "Destination Not Found",
            "spoken_hinglish": spoken,
            "audio_base64": audio,
            "tour_segments": [],
            "tourSegments": [],
            "target_pano_id": None,
            "target_branch": None,
            "final_destination_id": None,
            "destination_entity": None,
            "route": None,
        }
        await broadcast_kiosk_command(packet)
        return packet

    # 2. Persona identity query: speak answer without navigation tour
    if entity.get("id") == "sakhi_persona":
        spoken = entity.get("spoken_hinglish", "Main Sakhi hoon, aapki smart campus guide!")
        audio = await synthesize(spoken)
        packet = {
            "action": "speak_only",
            "query": query,
            "matched": True,
            "display_title": entity.get("name", "Sakhi"),
            "spoken_hinglish": spoken,
            "audio_base64": audio,
            "tour_segments": [],
            "tourSegments": [],
            "target_pano_id": None,
            "target_branch": None,
            "final_destination_id": "sakhi_persona",
            "destination_entity": entity,
            "route": None,
        }
        await broadcast_kiosk_command(packet)
        return packet

    # 3. Valid Campus Destination: Generate route & multi-phase tour
    target = entity.get("linked_pano_id") or entity.get("pano_id")
    spoken = entity.get("spoken_hinglish", entity["name"])
    display = entity["name"]
    target_branch = entity.get("target_branch")

    if target not in NODES:
        target = "01_main_entrance_floor1"

    final_dest_id = entity.get("id") if entity else target
    route = build_route(start_node, target, target_branch=target_branch, final_destination_id=final_dest_id)

    tour_entity = dict(entity)
    tour_entity["target_pano_id"] = target

    tour_segments = await generate_tour_segments(tour_entity, route.get("path", [start_node, target]))
    audio = tour_segments[0]["audio_base64"] if tour_segments else await synthesize(spoken)

    packet = {
        "action": "start_tour",
        "query": query,
        "matched": True,
        "display_title": display,
        "spoken_hinglish": spoken,
        "audio_base64": audio,
        "tour_segments": tour_segments,
        "tourSegments": tour_segments,
        "target_pano_id": target,
        "target_branch": target_branch,
        "final_destination_id": final_dest_id,
        "destination_entity": entity,
        "route": route,
    }

    # Broadcast directly to the kiosk screen for zero-touch auto-execution
    await broadcast_kiosk_command(packet)
    return packet


# ── Query endpoint ─────────────────────────────────────────────────────────────
class QueryBody(BaseModel):
    query: str
    start: Optional[str] = START_NODE
    broadcast: Optional[bool] = False


@app.post("/api/query")
async def query_handler(body: QueryBody):
    start = body.start if body.start in NODES else START_NODE
    entity = resolve(body.query)

    # 1. Unresolved query
    if not entity:
        spoken = "Sakhi ko samajh nahi aaya. Kripya lab, room number ya teacher ka naam dobara boliye."
        audio = await synthesize(spoken)
        res = {
            "action": "not_found",
            "query": body.query,
            "matched": False,
            "display_title": "Destination Not Found",
            "spoken_hinglish": spoken,
            "audio_base64": audio,
            "tour_segments": [],
            "tourSegments": [],
            "target_pano_id": None,
            "target_branch": None,
            "final_destination_id": None,
            "destination_entity": None,
            "route": None,
        }
        if body.broadcast:
            await broadcast_kiosk_command(res)
        return JSONResponse(res)

    # 2. Persona identity query
    if entity.get("id") == "sakhi_persona":
        spoken = entity.get("spoken_hinglish", "Main Sakhi hoon, aapki smart campus guide!")
        audio = await synthesize(spoken)
        res = {
            "action": "speak_only",
            "query": body.query,
            "matched": True,
            "display_title": entity.get("name", "Sakhi"),
            "spoken_hinglish": spoken,
            "audio_base64": audio,
            "tour_segments": [],
            "tourSegments": [],
            "target_pano_id": None,
            "target_branch": None,
            "final_destination_id": "sakhi_persona",
            "destination_entity": entity,
            "route": None,
        }
        if body.broadcast:
            await broadcast_kiosk_command(res)
        return JSONResponse(res)

    # 3. Valid Campus Destination
    target = entity.get("linked_pano_id") or entity.get("pano_id")
    spoken = entity.get("spoken_hinglish", entity["name"])
    display = entity["name"]
    target_branch = entity.get("target_branch")

    if target not in NODES:
        target = "01_main_entrance_floor1"

    final_dest_id = entity.get("id") if entity else target
    route = build_route(start, target, target_branch=target_branch, final_destination_id=final_dest_id)

    # Generate synchronized multi-phase tour segments
    tour_entity = dict(entity)
    tour_entity["target_pano_id"] = target

    tour_segments = await generate_tour_segments(tour_entity, route.get("path", [start, target]))
    audio = tour_segments[0]["audio_base64"] if tour_segments else await synthesize(spoken)

    res = {
        "action": "start_tour",
        "query": body.query,
        "matched": True,
        "display_title": display,
        "spoken_hinglish": spoken,
        "audio_base64": audio,
        "tour_segments": tour_segments,
        "tourSegments": tour_segments,
        "target_pano_id": target,
        "target_branch": target_branch,
        "final_destination_id": final_dest_id,
        "destination_entity": entity,
        "route": route,
    }

    if body.broadcast:
        await broadcast_kiosk_command(res)

    return JSONResponse(res)


@app.post("/api/voice_query")
async def voice_query_endpoint(body: QueryBody):
    """Triggered by voice_listener daemon; automatically broadcasts to connected kiosk screens."""
    res = await execute_voice_query_and_broadcast(body.query, body.start)
    return JSONResponse(res)


@app.post("/api/kiosk/broadcast")
async def kiosk_broadcast_endpoint(data: dict):
    """Generic status/chime broadcast endpoint for external voice daemon."""
    await broadcast_kiosk_command(data)
    return {"status": "ok", "clients": len(active_connections)}


@app.post("/api/tts")
async def tts_endpoint(body: dict):
    text = body.get("text", "")
    audio = await synthesize(text)
    return {"audio_base64": audio}


if __name__ == "__main__":
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
