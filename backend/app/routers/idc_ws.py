"""
IDC WebSocket handler — real-time annotation and comment sync.
Each IDC session has its own room. All connected clients receive broadcasts.

Message protocol (JSON):
  Client → Server:
    { "type": "join",       "session_id": int, "emp_id": str, "emp_name": str, "discipline": str }
    { "type": "annotation", "action": "add"|"update"|"delete", "data": {...} }
    { "type": "comment",    "action": "add"|"update",           "data": {...} }
    { "type": "approve",    "discipline": str, "emp_name": str }
    { "type": "freeze" }
    { "type": "cursor",     "x": float, "y": float, "page": int }

  Server → Client (broadcast):
    Same envelope + "from_emp" field
"""
import json
import logging
from collections import defaultdict
from typing import Dict, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter(tags=["IDC WebSocket"])

# session_id → list of (WebSocket, emp_id, emp_name, discipline)
_rooms: Dict[int, List[dict]] = defaultdict(list)


def _peers(session_id: int) -> List[dict]:
    return _rooms[session_id]


async def _broadcast(session_id: int, message: dict, exclude_ws: WebSocket = None):
    dead = []
    for peer in _peers(session_id):
        if peer["ws"] is exclude_ws:
            continue
        try:
            await peer["ws"].send_json(message)
        except Exception:
            dead.append(peer)
    for d in dead:
        _rooms[session_id].remove(d)


async def _send_roster(session_id: int):
    roster = [
        {"emp_id": p["emp_id"], "emp_name": p["emp_name"], "discipline": p["discipline"]}
        for p in _peers(session_id)
    ]
    await _broadcast(session_id, {"type": "roster", "users": roster})


@router.websocket("/idc/ws/{session_id}")
async def idc_websocket(websocket: WebSocket, session_id: int):
    await websocket.accept()
    emp_id = ""
    emp_name = ""
    discipline = ""
    peer_entry = None

    try:
        async for raw in websocket.iter_text():
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            mtype = msg.get("type")

            if mtype == "join":
                emp_id = msg.get("emp_id", "")
                emp_name = msg.get("emp_name", "Unknown")
                discipline = msg.get("discipline", "")
                peer_entry = {"ws": websocket, "emp_id": emp_id, "emp_name": emp_name, "discipline": discipline}
                _rooms[session_id].append(peer_entry)
                await websocket.send_json({"type": "joined", "session_id": session_id})
                await _send_roster(session_id)
                await _broadcast(session_id, {
                    "type": "user_joined",
                    "emp_id": emp_id, "emp_name": emp_name, "discipline": discipline,
                }, exclude_ws=websocket)

            elif mtype in ("annotation", "comment", "approve", "freeze", "cursor"):
                payload = {"type": mtype, "from_emp": emp_id, "from_name": emp_name, "discipline": discipline}
                payload.update({k: v for k, v in msg.items() if k != "type"})
                await _broadcast(session_id, payload, exclude_ws=websocket)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("IDC WS error: %s", e)
    finally:
        if peer_entry and peer_entry in _rooms[session_id]:
            _rooms[session_id].remove(peer_entry)
        await _send_roster(session_id)
        await _broadcast(session_id, {
            "type": "user_left",
            "emp_id": emp_id, "emp_name": emp_name,
        })
