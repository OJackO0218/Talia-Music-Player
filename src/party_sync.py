"""
Talia Party Sync Service.

Manages synchronized listening sessions between multiple Talia instances.
Handles asynchronous WebSocket networking in a dedicated background thread
and communicates with the PyQt6 main thread via thread-safe signals.
"""

import asyncio
import json
import logging
import random
import re
import socket
import string
import threading
from typing import Any, Optional

from PyQt6.QtCore import QObject, pyqtSignal

log = logging.getLogger("PartySync")

# Default public relay URL or fallback
DEFAULT_RELAY_URL = "ws://127.0.0.1:8765"


def get_local_lan_ip() -> str:
    """Detects the primary LAN IP of this machine for local network or VPN party sharing."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def generate_room_code(length: int = 5) -> str:
    """Generates a memorable 5-character room code using clear alphanumeric characters."""
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(random.choices(chars, k=length))


class PartySyncService(QObject):
    """
    Background WebSocket client service for synchronized listening parties.
    Thread-safe Qt signal bridge for real-time play/pause/seek/track events.
    """

    # Signals delivered to the main Qt GUI thread
    connected = pyqtSignal(str, bool, list)  # room_code, is_host, members
    disconnected = pyqtSignal(str)          # reason
    peer_joined = pyqtSignal(str, int)       # peer_name, total_count
    peer_left = pyqtSignal(str, int)         # peer_name, total_count
    track_received = pyqtSignal(dict)        # {title, artist, filename, duration, timestamp, is_playing, yt_query}
    play_received = pyqtSignal(float)        # timestamp
    pause_received = pyqtSignal(float)       # timestamp
    seek_received = pyqtSignal(float)        # timestamp
    heartbeat_received = pyqtSignal(float, bool)  # timestamp, is_playing
    reaction_received = pyqtSignal(str, str) # emoji, sender
    status_message = pyqtSignal(str)         # UI notification
    error_occurred = pyqtSignal(str)         # Error message
    track_auto_downloaded = pyqtSignal(str, float, bool)  # target_dir, target_time, target_playing

    def __init__(self, parent=None):
        super().__init__(parent)
        self.room_code: str = ""
        self.user_name: str = "Listener"
        self.is_host: bool = False
        self.is_connected: bool = False
        self.allow_guest_control: bool = False

        # Asyncio background loop and thread
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ws = None
        self._send_queue: Optional[asyncio.Queue] = None
        self._stop_event = threading.Event()
        self._embedded_server = None

        self._ensure_worker_thread()

    def _ensure_worker_thread(self):
        """Starts the dedicated asyncio networking thread if not already running."""
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        ready_event = threading.Event()

        def _runner():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._send_queue = asyncio.Queue()
            ready_event.set()
            self._loop.run_forever()

        self._thread = threading.Thread(target=_runner, daemon=True, name="PartySyncWorker")
        self._thread.start()
        ready_event.wait(timeout=2.0)

    # -------------------------------------------------------------------------
    # Public Control API (called from Qt thread)
    # -------------------------------------------------------------------------

    def host_session(self, room_code: str = "", user_name: str = "Host", relay_url: str = DEFAULT_RELAY_URL):
        """Creates and hosts a new room. Automatically runs embedded server if local, or connects to external relay."""
        self._ensure_worker_thread()
        code = room_code.strip().upper() if room_code else generate_room_code()
        self.room_code = code
        self.user_name = user_name or "Host"
        self.is_host = True

        asyncio.run_coroutine_threadsafe(
            self._host_coroutine(relay_url, code, self.user_name),
            self._loop,
        )

    async def _host_coroutine(self, relay_url: str, room_code: str, user_name: str):
        """Intelligently hosts via embedded micro-relay or connects to specified remote relay."""
        url_raw = (relay_url or "").strip()
        url_lower = url_raw.lower()
        lan_ip = get_local_lan_ip()
        is_local = (
            not url_raw
            or "127.0.0.1" in url_lower
            or "localhost" in url_lower
            or lan_ip in url_lower
        )

        port = 8765
        port_match = re.search(r":(\d+)", url_raw)
        if port_match:
            try:
                port = int(port_match.group(1))
            except ValueError:
                port = 8765

        if is_local:
            await self._start_embedded_and_connect(port, room_code, user_name)
        else:
            try:
                await self._connect_and_run(url_raw, room_code, user_name, True)
            except Exception as exc:
                log.warning("Could not reach remote relay %s: %s. Hosting locally.", url_raw, exc)
                self.status_message.emit("Remote relay unreachable. Hosting session locally...")
                await self._start_embedded_and_connect(port, room_code, user_name)

    def join_session(self, room_code: str, user_name: str = "Listener", relay_url: str = DEFAULT_RELAY_URL):
        """Joins an existing room on the specified relay server."""
        self._ensure_worker_thread()
        code = room_code.strip().upper()
        if not code:
            self.error_occurred.emit("Please enter a valid room code.")
            return

        self.room_code = code
        self.user_name = user_name or "Listener"
        self.is_host = False

        asyncio.run_coroutine_threadsafe(
            self._connect_and_run(relay_url, code, self.user_name, False),
            self._loop,
        )

    def host_local_server(self, port: int = 8765, room_code: str = "LOCAL", user_name: str = "Host"):
        """Starts an embedded local WebSocket server on this PC and connects directly to it."""
        self._ensure_worker_thread()
        self.room_code = room_code.strip().upper() or "LOCAL"
        self.user_name = user_name or "Host"
        self.is_host = True

        asyncio.run_coroutine_threadsafe(
            self._start_embedded_and_connect(port, self.room_code, self.user_name),
            self._loop,
        )

    def disconnect_session(self):
        """Disconnects from the active session and stops relay."""
        if not self._loop:
            return
        asyncio.run_coroutine_threadsafe(self._async_disconnect(), self._loop)

    # -------------------------------------------------------------------------
    # Outgoing Broadcast Methods (called from Qt thread)
    # -------------------------------------------------------------------------

    def broadcast_track(
        self,
        title: str,
        artist: str,
        filename: str,
        duration: float,
        timestamp: float = 0.0,
        is_playing: bool = True,
        yt_query: str = "",
    ):
        """Broadcasts active track metadata to the room."""
        if not self.is_connected or (not self.is_host and not self.allow_guest_control):
            return
        query = yt_query or f"{artist} - {title}".strip(" -")
        payload = {
            "type": "track_change",
            "title": title,
            "artist": artist,
            "filename": filename,
            "duration": float(duration),
            "timestamp": round(float(timestamp), 2),
            "is_playing": bool(is_playing),
            "yt_query": query,
        }
        self._queue_message(payload)

    def broadcast_play(self, timestamp: float):
        """Broadcasts a Play command with the exact millisecond audio timestamp."""
        if not self.is_connected or (not self.is_host and not self.allow_guest_control):
            return
        self._queue_message({
            "type": "play",
            "timestamp": round(float(timestamp), 2),
        })

    def broadcast_pause(self, timestamp: float):
        """Broadcasts a Pause command with the current timestamp."""
        if not self.is_connected or (not self.is_host and not self.allow_guest_control):
            return
        self._queue_message({
            "type": "pause",
            "timestamp": round(float(timestamp), 2),
        })

    def broadcast_seek(self, timestamp: float):
        """Broadcasts a Timeline Seek command to all listeners."""
        if not self.is_connected or (not self.is_host and not self.allow_guest_control):
            return
        self._queue_message({
            "type": "seek",
            "timestamp": round(float(timestamp), 2),
        })

    def broadcast_heartbeat(self, timestamp: float, is_playing: bool):
        """Periodic clock synchronization heartbeat to eliminate drift."""
        if not self.is_connected or not self.is_host:
            return
        self._queue_message({
            "type": "heartbeat",
            "timestamp": round(float(timestamp), 2),
            "is_playing": bool(is_playing),
        })

    def broadcast_reaction(self, emoji: str):
        """Broadcasts an emoji reaction or nudge to party members."""
        if not self.is_connected:
            return
        self._queue_message({
            "type": "reaction",
            "emoji": str(emoji),
            "sender": self.user_name,
        })

    # -------------------------------------------------------------------------
    # Internal Async Networking Engine
    # -------------------------------------------------------------------------

    def _queue_message(self, data: dict):
        """Pushes a message dict to the async worker queue thread-safely."""
        if self._loop and self._send_queue:
            try:
                self._loop.call_soon_threadsafe(
                    self._send_queue.put_nowait, json.dumps(data)
                )
            except Exception as e:
                log.debug("Failed to queue party message: %s", e)

    async def _async_disconnect(self):
        """Gracefully closes active WebSocket and embedded server."""
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        if self._embedded_server:
            try:
                self._embedded_server.close()
                await self._embedded_server.wait_closed()
            except Exception:
                pass
            self._embedded_server = None

        self.is_connected = False
        self.disconnected.emit("Disconnected from session.")

    async def _start_embedded_and_connect(self, port: int, room_code: str, user_name: str):
        """Runs the embedded relay and connects to it over localhost."""
        try:
            import websockets

            # Close any previous embedded server cleanly
            if self._embedded_server:
                try:
                    self._embedded_server.close()
                    await self._embedded_server.wait_closed()
                except Exception:
                    pass
                self._embedded_server = None

            # Embedded micro-relay handler for local network sessions
            rooms: dict[str, dict[Any, dict]] = {}

            async def _local_handler(ws):
                current_r = None
                p_name = "Listener"
                is_h = False
                try:
                    async for raw in ws:
                        try:
                            d = json.loads(raw)
                        except (json.JSONDecodeError, TypeError):
                            continue

                        mtype = d.get("type")
                        if mtype == "join":
                            r = str(d.get("room", "")).strip().upper()
                            p_name = str(d.get("name", "Listener")).strip()
                            is_h = bool(d.get("is_host", False))
                            current_r = r

                            if r not in rooms:
                                rooms[r] = {}
                            rooms[r][ws] = {"name": p_name, "is_host": is_h}

                            members = [info["name"] for info in rooms[r].values()]
                            await ws.send(json.dumps({
                                "type": "joined",
                                "room": r,
                                "is_host": is_h,
                                "members": members,
                                "count": len(members),
                            }))

                            # Broadcast peer_joined to all other peers in room
                            peer_joined_msg = json.dumps({
                                "type": "peer_joined",
                                "name": p_name,
                                "is_host": is_h,
                                "count": len(members),
                            })
                            for peer in list(rooms[r].keys()):
                                if peer != ws:
                                    try:
                                        await peer.send(peer_joined_msg)
                                    except Exception:
                                        pass

                        elif mtype == "leave":
                            break

                        elif current_r and current_r in rooms:
                            d["sender"] = p_name
                            msg_str = json.dumps(d)
                            for peer in list(rooms[current_r].keys()):
                                if peer != ws:
                                    try:
                                        await peer.send(msg_str)
                                    except Exception:
                                        pass
                except Exception:
                    pass
                finally:
                    if current_r and current_r in rooms:
                        if ws in rooms[current_r]:
                            rooms[current_r].pop(ws, None)
                            if rooms[current_r]:
                                members = [info["name"] for info in rooms[current_r].values()]
                                peer_left_msg = json.dumps({
                                    "type": "peer_left",
                                    "name": p_name,
                                    "count": len(members),
                                })
                                for peer in list(rooms[current_r].keys()):
                                    try:
                                        await peer.send(peer_left_msg)
                                    except Exception:
                                        pass
                            else:
                                rooms.pop(current_r, None)

            # Try binding to requested port on loopback interface (clean, no wildcard backdoor flags)
            bound = False
            chosen_port = port
            host_candidate = "127.0.0.1"
            for p in range(port, port + 10):
                try:
                    self._embedded_server = await websockets.serve(_local_handler, host_candidate, p)
                    chosen_port = p
                    bound = True
                    break
                except OSError:
                    continue

            if not bound:
                self.error_occurred.emit(f"Could not bind local party server on port {port}.")
                return

            log.info("Embedded local party server listening on %s:%d", host_candidate, chosen_port)
            self.status_message.emit(f"Local party server listening on port {chosen_port}.")

            # Connect locally
            local_url = f"ws://{host_candidate}:{chosen_port}"
            await self._connect_and_run(local_url, room_code, user_name, True)

        except Exception as exc:
            log.error("Failed to start local party server: %s", exc)
            self.error_occurred.emit(f"Could not start local server on port {port}: {exc}")

    async def _connect_and_run(self, relay_url: str, room_code: str, user_name: str, is_host: bool):
        """Connects to the relay server, sends join handshake, and starts bidirectional message loops."""
        try:
            import websockets
            self.status_message.emit(f"Connecting to party relay at {relay_url} ...")
            async with websockets.connect(relay_url, ping_interval=20, ping_timeout=10) as ws:
                self._ws = ws

                # Send Join Handshake
                handshake = {
                    "type": "join",
                    "room": room_code,
                    "name": user_name,
                    "is_host": is_host,
                }
                await ws.send(json.dumps(handshake))

                # Wait for initial 'joined' response
                raw_ack = await asyncio.wait_for(ws.recv(), timeout=6.0)
                ack = json.loads(raw_ack)
                if ack.get("type") != "joined":
                    err_msg = ack.get("message", "Failed to join room.")
                    self.error_occurred.emit(err_msg)
                    return

                self.is_connected = True
                members = ack.get("members", [user_name])
                self.connected.emit(room_code, is_host, members)
                self.status_message.emit(f"Connected to Room '{room_code}'! ({len(members)} listening)")

                # Run concurrent sender and receiver tasks
                recv_task = asyncio.create_task(self._receive_loop(ws))
                send_task = asyncio.create_task(self._send_loop(ws))

                done, pending = await asyncio.wait(
                    [recv_task, send_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()

        except asyncio.TimeoutError:
            self.error_occurred.emit("Connection timed out. Check the relay server address.")
        except Exception as exc:
            log.info("Party connection terminated: %s", exc)
            self.error_occurred.emit(f"Party connection closed: {exc}")
        finally:
            was_connected = self.is_connected
            self.is_connected = False
            self._ws = None
            if was_connected:
                self.disconnected.emit("Party session ended.")

    async def _send_loop(self, ws):
        """Continuously pulls outgoing messages from the queue and sends them to the WebSocket."""
        while self.is_connected:
            try:
                msg = await self._send_queue.get()
                await ws.send(msg)
                self._send_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.debug("Send error in party loop: %s", e)
                break

    async def _receive_loop(self, ws):
        """Listens for incoming messages from the relay and dispatches Qt signals."""
        while self.is_connected:
            try:
                raw = await ws.recv()
                data = json.loads(raw)
                mtype = data.get("type")

                if mtype == "track_change":
                    self.track_received.emit(data)
                elif mtype == "play":
                    ts = float(data.get("timestamp", 0.0))
                    self.play_received.emit(ts)
                elif mtype == "pause":
                    ts = float(data.get("timestamp", 0.0))
                    self.pause_received.emit(ts)
                elif mtype == "seek":
                    ts = float(data.get("timestamp", 0.0))
                    self.seek_received.emit(ts)
                elif mtype == "heartbeat":
                    ts = float(data.get("timestamp", 0.0))
                    playing = bool(data.get("is_playing", False))
                    self.heartbeat_received.emit(ts, playing)
                elif mtype == "reaction":
                    emoji = str(data.get("emoji", "HYPE"))
                    sender = str(data.get("sender", "Peer"))
                    self.reaction_received.emit(emoji, sender)
                elif mtype == "peer_joined":
                    pname = str(data.get("name", "Listener"))
                    count = int(data.get("count", 1))
                    self.peer_joined.emit(pname, count)
                elif mtype == "peer_left":
                    pname = str(data.get("name", "Listener"))
                    count = int(data.get("count", 1))
                    self.peer_left.emit(pname, count)
                elif mtype == "error":
                    self.error_occurred.emit(str(data.get("message", "Room error")))

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.debug("Receive error in party loop: %s", e)
                break
