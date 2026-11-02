"""
Talia Listen Together - Cloud WebSocket Relay Server.

Lightweight, production-ready relay server for synchronizing Talia music player
sessions anywhere in the world across firewalls and NAT without port forwarding.

Deployable for free on:
- Render.com (via render.yaml or Web Service)
- Railway.app
- Fly.io
- Glitch.com
- Any VPS / Docker container
"""

import asyncio
import json
import logging
import os
from aiohttp import web

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("TaliaCloudRelay")

# In-memory room registry: room_code -> { WebSocketResponse: {"name": str, "is_host": bool} }
rooms: dict[str, dict[web.WebSocketResponse, dict]] = {}


async def health_check(request: web.Request) -> web.Response:
    """HTTP health check and status report for cloud hosts and monitoring."""
    total_listeners = sum(len(members) for members in rooms.values())
    return web.json_response({
        "status": "online",
        "service": "Talia Listen Together Cloud Relay",
        "active_rooms": len(rooms),
        "total_listeners": total_listeners,
        "rooms": [
            {"code": r, "members": [p["name"] for p in members.values()], "count": len(members)}
            for r, members in rooms.items()
        ],
    })


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    """Handles real-time room joining, heartbeat, and playback broadcast routing."""
    ws = web.WebSocketResponse(heartbeat=25.0, max_msg_size=1024 * 1024)
    await ws.prepare(request)

    current_room = None
    peer_name = "Listener"
    is_host = False

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except (json.JSONDecodeError, TypeError):
                    continue

                mtype = data.get("type")

                # --- 1. JOIN ROOM ---
                if mtype == "join":
                    raw_room = str(data.get("room", "")).strip().upper()
                    if not raw_room:
                        await ws.send_json({"type": "error", "message": "Missing room code."})
                        continue

                    current_room = raw_room
                    peer_name = str(data.get("name", "Listener")).strip() or "Listener"
                    is_host = bool(data.get("is_host", False))

                    if current_room not in rooms:
                        rooms[current_room] = {}
                    rooms[current_room][ws] = {"name": peer_name, "is_host": is_host}

                    members = [p["name"] for p in rooms[current_room].values()]
                    log.info("[JOIN] '%s' joined room '%s' (is_host=%s, total=%d)", peer_name, current_room, is_host, len(members))

                    # Send ACK with member list to joining client
                    await ws.send_json({
                        "type": "joined",
                        "room": current_room,
                        "is_host": is_host,
                        "members": members,
                        "count": len(members),
                    })

                    # Broadcast peer_joined to all other listeners in this room
                    peer_joined_payload = json.dumps({
                        "type": "peer_joined",
                        "name": peer_name,
                        "is_host": is_host,
                        "count": len(members),
                    })
                    for peer in list(rooms[current_room].keys()):
                        if peer != ws and not peer.closed:
                            try:
                                await peer.send_str(peer_joined_payload)
                            except Exception:
                                pass

                # --- 2. LEAVE ROOM ---
                elif mtype == "leave":
                    break

                # --- 3. BROADCAST ROOM MESSAGES ---
                elif current_room and current_room in rooms:
                    data["sender"] = peer_name
                    msg_str = json.dumps(data)
                    for peer in list(rooms[current_room].keys()):
                        if peer != ws and not peer.closed:
                            try:
                                await peer.send_str(msg_str)
                            except Exception:
                                pass

            elif msg.type in (web.WSMsgType.CLOSE, web.WSMsgType.CLOSING, web.WSMsgType.CLOSED):
                break
            elif msg.type == web.WSMsgType.ERROR:
                log.warning("WebSocket connection error: %s", ws.exception())
                break

    finally:
        # Gracefully handle disconnect and update peers
        if current_room and current_room in rooms:
            if ws in rooms[current_room]:
                rooms[current_room].pop(ws, None)
                if rooms[current_room]:
                    members = [p["name"] for p in rooms[current_room].values()]
                    log.info("[LEAVE] '%s' left room '%s' (%d remaining)", peer_name, current_room, len(members))
                    peer_left_payload = json.dumps({
                        "type": "peer_left",
                        "name": peer_name,
                        "count": len(members),
                    })
                    for peer in list(rooms[current_room].keys()):
                        if not peer.closed:
                            try:
                                await peer.send_str(peer_left_payload)
                            except Exception:
                                pass
                else:
                    rooms.pop(current_room, None)
                    log.info("[ROOM CLOSED] Room '%s' is now empty.", current_room)

    return ws


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    app.router.add_get("/ws", websocket_handler)
    # Also route any WebSocket connection requesting root path
    app.router.add_route("*", "/{tail:.*}", websocket_handler)
    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8765))
    host = os.environ.get("HOST", "0.0.0.0")
    log.info("Starting Talia Cloud Relay on %s:%d ...", host, port)
    web.run_app(create_app(), host=host, port=port)
