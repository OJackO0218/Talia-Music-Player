"""
Talia Party Sync Relay Server.

A lightweight, zero-dependency WebSocket relay server that routes synchronized
playback packets, track information, and reactions between peers in the same room.
Can be run locally or deployed to any cloud host (Render, Railway, Replit, VPS).
"""

import argparse
import asyncio
import json
import logging
import sys

try:
    import websockets
except ImportError:
    print("Error: 'websockets' library is required. Install via: pip install websockets")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("TaliaRelay")

# Map: room_code -> dict of {websocket: client_info}
ROOMS: dict[str, dict[websockets.WebSocketServerProtocol, dict]] = {}


async def broadcast_to_room(room_code: str, message: str, sender_ws=None):
    """Sends a message to all connected clients in a room (optionally excluding sender)."""
    room = ROOMS.get(room_code)
    if not room:
        return

    dead_sockets = set()
    for ws in list(room.keys()):
        if ws == sender_ws:
            continue
        try:
            await ws.send(message)
        except Exception:
            dead_sockets.add(ws)

    for dead in dead_sockets:
        if dead in room:
            client_info = room.pop(dead)
            log.info("Removed stale connection in room %s (%s)", room_code, client_info.get("name"))

    if not room:
        ROOMS.pop(room_code, None)
        log.info("Room %s is now empty and closed.", room_code)


async def handler(websocket):
    """Handles an incoming WebSocket connection lifecycle."""
    current_room = None
    client_name = "Anonymous"
    is_host = False

    try:
        async for raw_message in websocket:
            try:
                data = json.loads(raw_message)
            except (json.JSONDecodeError, TypeError):
                continue

            msg_type = data.get("type")

            # 1. Join room
            if msg_type == "join":
                room_code = str(data.get("room", "")).strip().upper()
                client_name = str(data.get("name", "Listener")).strip()
                is_host = bool(data.get("is_host", False))

                if not room_code:
                    await websocket.send(json.dumps({"type": "error", "message": "Invalid room code"}))
                    continue

                current_room = room_code
                if not is_host and (current_room not in ROOMS or not ROOMS[current_room]):
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": f"Room '{current_room}' does not exist or host is offline."
                    }))
                    continue

                if current_room not in ROOMS:
                    ROOMS[current_room] = {}

                ROOMS[current_room][websocket] = {
                    "name": client_name,
                    "is_host": is_host,
                }

                log.info("Peer '%s' (Host=%s) joined room %s. Total: %d",
                         client_name, is_host, current_room, len(ROOMS[current_room]))

                # Acknowledge join to the connecting client
                members = [info["name"] for info in ROOMS[current_room].values()]
                await websocket.send(json.dumps({
                    "type": "joined",
                    "room": current_room,
                    "is_host": is_host,
                    "members": members,
                    "count": len(members),
                }))

                # Notify other peers in the room
                await broadcast_to_room(
                    current_room,
                    json.dumps({
                        "type": "peer_joined",
                        "name": client_name,
                        "is_host": is_host,
                        "count": len(members),
                    }),
                    sender_ws=websocket,
                )

            # 2. Leave room
            elif msg_type == "leave":
                break

            # 3. Relay playback events (play, pause, seek, track_change, heartbeat, reaction)
            elif current_room and current_room in ROOMS:
                # Add sender info
                data["sender"] = client_name
                await broadcast_to_room(current_room, json.dumps(data), sender_ws=websocket)

    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as exc:
        log.warning("Connection error: %s", exc)
    finally:
        if current_room and current_room in ROOMS:
            if websocket in ROOMS[current_room]:
                ROOMS[current_room].pop(websocket)
                log.info("Peer '%s' left room %s", client_name, current_room)

                # Notify remaining members
                if current_room in ROOMS and ROOMS[current_room]:
                    members = [info["name"] for info in ROOMS[current_room].values()]
                    await broadcast_to_room(
                        current_room,
                        json.dumps({
                            "type": "peer_left",
                            "name": client_name,
                            "count": len(members),
                        }),
                    )
                else:
                    ROOMS.pop(current_room, None)
                    log.info("Room %s closed.", current_room)


async def main():
    parser = argparse.ArgumentParser(description="Talia Party Sync Relay Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on (default: 8765)")
    args = parser.parse_args()

    log.info("Starting Talia Party Sync Relay on %s:%d ...", args.host, args.port)
    async with websockets.serve(handler, args.host, args.port):
        log.info("Relay ready. Waiting for room connections.")
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Relay stopped by user.")
