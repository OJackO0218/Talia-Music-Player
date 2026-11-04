"""
Talia Discord Rich Presence Service.

Maintains background connection to Discord IPC using pypresence.
Runs in a separate daemon thread with a command queue so it never blocks
the Qt UI loop or audio playback.
"""

import logging
import os
import queue
import re
import threading
import time
from typing import Optional

log = logging.getLogger("DiscordRPC")

DEFAULT_CLIENT_ID = "1566836776113275070"

try:
    from pypresence import ActivityType
    LISTENING_TYPE = ActivityType.LISTENING
except Exception:
    class _FallbackActivityType:
        value = 2
    LISTENING_TYPE = _FallbackActivityType()


def parse_track_info(raw_title: str) -> tuple[str, str]:
    """Splits 'Artist - Title.ext' into clean (title, artist) strings."""
    clean = os.path.splitext(raw_title)[0].strip()
    # Strip any leading track number prefix (e.g. "01. ", "01 - ", "001. ")
    clean = re.sub(r"^\d{1,3}(?:[\.\-_]|\s+-)\s*", "", clean).strip()
    if " - " in clean:
        parts = clean.split(" - ", 1)
        artist = parts[0].strip()
        title = parts[1].strip()
        return (title or clean or "Unknown Track", artist)
    return (clean or "Unknown Track", "")


class DiscordRpcService:
    """Non-blocking Discord Rich Presence manager."""

    def __init__(self, client_id: str = DEFAULT_CLIENT_ID, enabled: bool = True):
        self.client_id = str(client_id).strip() or DEFAULT_CLIENT_ID
        if os.environ.get("TALIA_DISABLE_DISCORD_RPC") == "1":
            self.enabled = False
        else:
            self.enabled = bool(enabled)
        self._rpc = None
        self._connected = False
        self._queue = queue.Queue()
        self._stop_event = threading.Event()
        self._thread = None

        # Playback tracking
        self._last_track = ""
        self._is_playing = False
        self._current_pos = 0.0
        self._current_dur = 0.0
        self._start_epoch = 0
        self._end_epoch = 0
        self._last_sent_payload = None

        if self.enabled:
            self.start()

    def start(self):
        """Starts the background worker thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker, daemon=True, name="DiscordRpcWorker")
        self._thread.start()

    def stop(self):
        """Signals worker to close presence and exit."""
        self._stop_event.set()
        self._queue.put({"action": "stop"})

    def set_enabled(self, enabled: bool):
        self.enabled = bool(enabled)
        if self.enabled:
            self.start()
            self._queue.put({"action": "refresh"})
        else:
            self._queue.put({"action": "clear"})

    def update_playback(self, raw_title: str, is_playing: bool, position: float, duration: float):
        """Pushes playback update to background worker only when state or position changes significantly."""
        if not self.enabled:
            return

        track_changed = (raw_title != self._last_track)
        play_changed = (is_playing != self._is_playing)

        # Detect manual seeks (scrubbing): check if audio position jumped by > 2.0s from expected time
        seeked = False
        now = time.time()
        if is_playing and not track_changed and not play_changed and self._start_epoch > 0:
            expected_pos = now - self._start_epoch
            if abs(position - expected_pos) > 2.0:
                seeked = True

        # If track, play state, and position have not changed, let Discord's local timer run smoothly
        if not track_changed and not play_changed and not seeked:
            return

        self._last_track = raw_title
        self._is_playing = is_playing
        self._current_pos = position
        self._current_dur = duration

        if is_playing and duration > 0:
            start_ts = int(now - max(0.0, position))
            end_ts = int(start_ts + max(1.0, duration))
            self._start_epoch = start_ts
            self._end_epoch = end_ts
        else:
            start_ts = None
            end_ts = None
            self._start_epoch = 0
            self._end_epoch = 0

        self._queue.put({
            "action": "update",
            "title": raw_title,
            "is_playing": is_playing,
            "start": start_ts,
            "end": end_ts,
            "duration": duration,
        })

    def _build_payload(self, title: str, is_playing: bool, start: Optional[int], end: Optional[int]) -> dict:
        if not title or title == "No Track Loaded":
            return {
                "activity_type": LISTENING_TYPE,
                "details": "Talia Music Player",
                "state": "Selecting a track",
                "large_image": "talia_logo",
                "large_text": "Talia Music Player v2.3.0",
                "buttons": [
                    {"label": "Listen Together", "url": "https://github.com/OJackO0218/Talia-Music-Player/releases"},
                ],
            }

        track_title, artist = parse_track_info(title)
        display_artist = artist if artist else "Talia"
        details_str = track_title[:127]
        state_str = (display_artist if is_playing else f"{display_artist} (Paused)")[:127]

        payload = {
            "activity_type": LISTENING_TYPE,
            "details": details_str,
            "state": state_str,
            "large_image": "talia_logo",
            "large_text": "Talia Music Player v2.3.0",
            "small_image": "play" if is_playing else "pause",
            "small_text": "Playing" if is_playing else "Paused",
            "buttons": [
                {"label": "Listen Together", "url": "https://github.com/OJackO0218/Talia-Music-Player/releases"},
            ],
        }
        if is_playing and start is not None and end is not None:
            payload["start"] = start
            payload["end"] = end
        return payload

    def _try_connect(self) -> bool:
        """Attempts to connect to local Discord IPC."""
        if self._connected and self._rpc:
            return True
        try:
            from pypresence import Presence
            self._rpc = Presence(self.client_id)
            self._rpc.connect()
            self._connected = True
            log.info("[DISCORD RPC] Connected to Discord client.")
            return True
        except Exception as e:
            self._connected = False
            self._rpc = None
            log.debug("[DISCORD RPC] Discord not running or pipe closed: %s", e)
            return False

    def _send_payload(self, payload: dict):
        if not self._connected or not self._rpc:
            return
        try:
            self._rpc.update(**payload)
            self._last_sent_payload = payload
        except Exception as exc:
            log.debug("[DISCORD RPC] Failed to update presence: %s", exc)
            self._connected = False
            self._rpc = None

    def _worker(self):
        last_connect_attempt = 0.0

        while not self._stop_event.is_set():
            try:
                # Wait for next command or reconnect timeout
                item = None
                try:
                    item = self._queue.get(timeout=2.0)
                except queue.Empty:
                    pass

                if not self.enabled:
                    if self._connected and self._rpc:
                        try:
                            self._rpc.clear()
                            self._rpc.close()
                        except Exception:
                            pass
                        self._connected = False
                        self._rpc = None
                    continue

                if item and item.get("action") == "stop":
                    break

                if item and item.get("action") == "clear":
                    if self._connected and self._rpc:
                        try:
                            self._rpc.clear()
                        except Exception:
                            pass
                        self._last_sent_payload = None
                    continue

                # Ensure connection to Discord IPC
                now = time.time()
                just_connected = False
                if not self._connected:
                    if now - last_connect_attempt > 15.0:
                        last_connect_attempt = now
                        if self._try_connect():
                            just_connected = True
                    if not self._connected:
                        continue

                # If an update command arrived, send it
                if item and item.get("action") == "update":
                    payload = self._build_payload(
                        item["title"],
                        item["is_playing"],
                        item.get("start"),
                        item.get("end"),
                    )
                    self._send_payload(payload)
                elif just_connected or (item and item.get("action") == "refresh"):
                    # Resend current playback state on connect/refresh
                    payload = self._build_payload(
                        self._last_track,
                        self._is_playing,
                        self._start_epoch if self._is_playing else None,
                        self._end_epoch if self._is_playing else None,
                    )
                    self._send_payload(payload)

            except Exception as e:
                log.debug("[DISCORD RPC] Worker loop error: %s", e)

        # Cleanup on exit
        if self._connected and self._rpc:
            try:
                self._rpc.clear()
                self._rpc.close()
            except Exception:
                pass
            self._connected = False
            self._rpc = None
