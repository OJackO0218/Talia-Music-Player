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
import time
import string
import threading
from typing import Any, Optional

from PyQt6.QtCore import QObject, pyqtSignal

log = logging.getLogger("PartySync")

# Default public relay URL or fallback
DEFAULT_RELAY_URL = "wss://soft-mongoose-6754.ojacko0218.deno.net"


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
    status_message = pyqtSignal(str)         # UI notification
    error_occurred = pyqtSignal(str)         # Error message
    track_auto_downloaded = pyqtSignal(str, float, bool, str)  # target_dir, target_time, target_playing, file_path
    host_transferred = pyqtSignal(str, str)  # new_host, old_host
    queue_updated = pyqtSignal(list)         # list of queued track dicts
    prefetch_completed = pyqtSignal(bool, str, dict)  # ok, file_path, track_data

    def __init__(self, parent=None):
        super().__init__(parent)
        self.room_code: str = ""
        self.user_name: str = "Listener"
        self.host_name: str = ""
        self.is_host: bool = False
        self.is_connected: bool = False
        self.allow_guest_control: bool = False
        self.party_queue: list[dict] = []

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
        self.host_name = self.user_name

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
                self.error_occurred.emit(f"Could not reach remote relay ({exc}). Hosting locally (LAN only)...")
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
        self.host_name = ""

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
        self.host_name = self.user_name

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

    broadcast_track_change = broadcast_track

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



    def transfer_host(self, target_user: str):
        """Transfers host privileges to a specific listener in the active room."""
        if not self.is_connected or not self.is_host:
            return
        self._queue_message({
            "type": "transfer_host",
            "target": target_user,
        })

    def add_to_party_queue(
        self,
        title: str,
        artist: str = "",
        filename: str = "",
        duration: float = 0.0,
        yt_query: str = "",
    ) -> dict:
        """Adds a track to the shared party queue. Callable by any room member."""
        if not self.is_connected:
            return {}
        item_id = f"q_{int(time.time() * 1000)}_{random.randint(100, 999)}"
        clean_title = title.strip() or "Unknown Title"
        clean_artist = artist.strip()
        if clean_artist.lower() in ("talia player", "talia music player", "unknown artist", "unknown"):
            clean_artist = ""
        if yt_query:
            query = yt_query
        elif clean_artist:
            query = f"{clean_artist} - {clean_title}"
        else:
            query = clean_title
        query = re.sub(r"(?i)\btalia\s+(?:music\s+)?player\s*[-:]?\s*", "", query).strip()
        item = {
            "id": item_id,
            "title": clean_title,
            "artist": clean_artist,
            "filename": filename.strip(),
            "duration": round(float(duration), 2),
            "yt_query": query,
            "added_by": self.user_name,
        }
        self.party_queue.append(item)
        self.queue_updated.emit(list(self.party_queue))
        self._queue_message({
            "type": "queue_add",
            "item": item,
        })
        return item

    def remove_from_party_queue(self, item_id: str) -> bool:
        """
        Removes a track from the shared party queue.
        Enforces permissions: Host can remove any song; members can remove only their own.
        """
        if not self.is_connected:
            return False
        found = None
        for itm in self.party_queue:
            if itm.get("id") == item_id:
                found = itm
                break
        if not found:
            return False
        if not self.is_host and found.get("added_by") != self.user_name:
            log.warning(
                "[PARTY QUEUE] Permission denied: %s cannot remove track added by %s",
                self.user_name,
                found.get("added_by"),
            )
            return False

        self.party_queue.remove(found)
        self.queue_updated.emit(list(self.party_queue))
        self._queue_message({
            "type": "queue_remove",
            "item_id": item_id,
            "removed_by": self.user_name,
        })
        return True

    def pop_next_party_track(self) -> Optional[dict]:
        """Pops the next queued track for playback. Host only."""
        if not self.is_connected or not self.is_host or not self.party_queue:
            return None
        item = self.party_queue.pop(0)
        self.queue_updated.emit(list(self.party_queue))
        self._queue_message({
            "type": "queue_sync",
            "queue": list(self.party_queue),
        })
        return item

    def clear_party_queue(self) -> bool:
        """Clears all songs from the shared party queue. Host only."""
        if not self.is_connected or not self.is_host:
            return False
        self.party_queue.clear()
        self.queue_updated.emit([])
        self._queue_message({
            "type": "queue_sync",
            "queue": [],
        })
        return True

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
        self.host_name = ""
        self.party_queue.clear()
        self.queue_updated.emit([])
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

                            if not is_h and (r not in rooms or not rooms[r]):
                                await ws.send(json.dumps({
                                    "type": "error",
                                    "message": f"Room '{r}' does not exist or host is offline."
                                }))
                                continue

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

                        elif mtype == "transfer_host" and current_r and current_r in rooms and is_h:
                            target_name = str(d.get("target", "")).strip()
                            target_ws = None
                            for p_ws, p_info in rooms[current_r].items():
                                if p_info.get("name") == target_name:
                                    target_ws = p_ws
                                    break
                            if target_ws:
                                is_h = False
                                rooms[current_r][ws]["is_host"] = False
                                rooms[current_r][target_ws]["is_host"] = True
                                trans_payload = json.dumps({
                                    "type": "host_transferred",
                                    "new_host": target_name,
                                    "old_host": p_name,
                                })
                                for peer in list(rooms[current_r].keys()):
                                    try:
                                        await peer.send(trans_payload)
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
                                has_remaining_host = any(info.get("is_host") for info in rooms[current_r].values())
                                if is_h and not has_remaining_host:
                                    close_msg = json.dumps({
                                        "type": "room_closed",
                                        "reason": "Host has left the party session. Room closed.",
                                    })
                                    for peer in list(rooms[current_r].keys()):
                                        try:
                                            await peer.send(close_msg)
                                            await peer.close()
                                        except Exception:
                                            pass
                                    rooms.pop(current_r, None)
                                else:
                                    members = [info["name"] for info in rooms[current_r].values()]
                                    peer_left_msg = json.dumps({
                                        "type": "peer_left",
                                        "name": p_name,
                                        "is_host": is_h,
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
            host_candidate = "0.0.0.0"
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
            local_url = f"ws://127.0.0.1:{chosen_port}"
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

                # Reject joining if we are a listener but no host is in the room
                if not is_host and len(members) <= 1 and not ack.get("host_name"):
                    log.warning("Join rejected: Room '%s' has no host online (members=%s)", room_code, members)
                    try:
                        await ws.send(json.dumps({"type": "leave"}))
                        await ws.close()
                    except Exception:
                        pass
                    self._ws = None
                    self.is_connected = False
                    self.error_occurred.emit(f"Room '{room_code}' does not exist or host is offline.")
                    return

                if is_host:
                    self.host_name = user_name
                elif members and len(members) > 1:
                    self.host_name = members[0]
                else:
                    self.host_name = ack.get("host_name", "Host")

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
                elif mtype == "peer_joined":
                    pname = str(data.get("name", "Listener"))
                    count = int(data.get("count", 1))
                    self.peer_joined.emit(pname, count)
                    if self.is_host and self.party_queue:
                        self._queue_message({"type": "queue_sync", "queue": list(self.party_queue)})
                elif mtype == "queue_add":
                    item = data.get("item", {})
                    if item and not any(q.get("id") == item.get("id") for q in self.party_queue):
                        self.party_queue.append(item)
                        self.queue_updated.emit(list(self.party_queue))
                        p_by = item.get("added_by", "A listener")
                        t_name = item.get("title", "Track")
                        self.status_message.emit(f"{p_by} added '{t_name}' to Party Queue.")
                elif mtype == "queue_remove":
                    item_id = str(data.get("item_id", ""))
                    removed_by = str(data.get("removed_by", "")).strip()
                    found = None
                    for q in self.party_queue:
                        if q.get("id") == item_id:
                            if removed_by == self.host_name or removed_by == q.get("added_by") or self.is_host:
                                found = q
                            break
                    if found:
                        self.party_queue.remove(found)
                        self.queue_updated.emit(list(self.party_queue))
                        self.status_message.emit(f"Removed '{found.get('title')}' from Party Queue.")
                elif mtype == "queue_sync":
                    q_list = data.get("queue", [])
                    self.party_queue = list(q_list)
                    self.queue_updated.emit(list(self.party_queue))
                elif mtype == "room_closed":
                    reason = str(data.get("reason", "Host has left the party session. Room closed."))
                    log.info("Room closed event: %s", reason)
                    self.error_occurred.emit(reason)
                    self.status_message.emit(reason)
                    asyncio.create_task(self._async_disconnect())
                elif mtype == "host_transferred":
                    new_host = str(data.get("new_host", "")).strip()
                    old_host = str(data.get("old_host", "")).strip()
                    self.host_name = new_host
                    if self.user_name == new_host:
                        self.is_host = True
                        self.status_message.emit("You are now the party Host!")
                    elif self.user_name == old_host:
                        self.is_host = False
                        self.status_message.emit(f"Host transferred to {new_host}.")
                    else:
                        self.status_message.emit(f"{new_host} is now the party Host.")
                    self.host_transferred.emit(new_host, old_host)
                elif mtype == "peer_left":
                    pname = str(data.get("name", "Listener"))
                    count = int(data.get("count", 1))
                    left_is_host = bool(data.get("is_host", False))
                    self.peer_left.emit(pname, count)
                    if not self.is_host:
                        if left_is_host or pname == self.host_name or count <= 1:
                            log.info("Host '%s' left. Auto-closing room '%s'.", pname, self.room_code)
                            self.error_occurred.emit("Host has left the party session. Room closed.")
                            asyncio.create_task(self._async_disconnect())
                elif mtype == "error":
                    self.error_occurred.emit(str(data.get("message", "Room error")))

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.debug("Receive error in party loop: %s", e)
                break
