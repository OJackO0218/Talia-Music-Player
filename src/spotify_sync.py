"""
Talia Spotify Sync Service.

Fetches Spotify playlists, albums, and tracks directly without requiring
developer keys or logins. Selected tracks are searched, converted to
high-quality Opus audio, paired with synchronized LRC lyrics, and loaded
into Talia's player.
"""

import base64
import html
import json
import logging
import os
import re
import urllib.parse
import urllib.request
from typing import Any, Optional

from PyQt6.QtCore import QObject, pyqtSignal

log = logging.getLogger("SpotifySync")

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
SAVED_PLAYLISTS_FILE = os.path.join(PROJECT_ROOT, "assets", "saved_spotify_playlists.json")

DEFAULT_CURATED_PLAYLISTS = [
    {
        "name": "Today's Top Hits",
        "url": "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
        "category": "Popular",
    },
    {
        "name": "Lo-Fi Chill & Focus",
        "url": "https://open.spotify.com/playlist/37i9dQZF1DXdLEN7aqioXM",
        "category": "Chill",
    },
    {
        "name": "Gaming Energy Beats",
        "url": "https://open.spotify.com/playlist/37i9dQZF1DXdfO26QVUwfN",
        "category": "Gaming",
    },
    {
        "name": "Rock Classics",
        "url": "https://open.spotify.com/playlist/37i9dQZF1DWXRqgorJj26U",
        "category": "Rock",
    },
]


class SpotifySyncService(QObject):
    """Handles Spotify playlist metadata fetching and saved playlist management."""

    playlist_loaded = pyqtSignal(dict)         # {title, owner, total, tracks: [...]}
    saved_playlists_updated = pyqtSignal(list) # list of saved playlist dicts
    fetch_error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.access_token: Optional[str] = None
        self.client_id: str = ""
        self.client_secret: str = ""
        self._saved_playlists: list[dict] = self._load_saved_playlists_from_disk()

    # -------------------------------------------------------------------------
    # 1. Zero-Setup Public Scraper (Paste URL -> Instant Track List)
    # -------------------------------------------------------------------------

    def extract_spotify_entity(self, url_or_id: str) -> tuple[Optional[str], Optional[str]]:
        """
        Extracts entity type ('playlist', 'album', 'track') and 22-char ID
        from a URL, URI, or raw string.
        """
        text = url_or_id.strip()
        # Direct 22-char ID defaults to playlist
        if re.match(r"^[a-zA-Z0-9]{22}$", text):
            return "playlist", text

        # Spotify URI: spotify:track:..., spotify:playlist:...
        uri_match = re.search(r"spotify:(playlist|album|track):([a-zA-Z0-9]{22})", text)
        if uri_match:
            return uri_match.group(1), uri_match.group(2)

        # Standard Web URL: https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?...
        url_match = re.search(r"/(playlist|album|track)/([a-zA-Z0-9]{22})", text)
        if url_match:
            return url_match.group(1), url_match.group(2)

        return None, None

    def extract_playlist_id(self, url_or_id: str) -> Optional[str]:
        """Extracts the 22-character Spotify ID for compatibility."""
        _, pid = self.extract_spotify_entity(url_or_id)
        return pid

    def fetch_playlist_by_url(self, url: str) -> Optional[dict]:
        """
        Fetches playlist, album, or track metadata without requiring Spotify API keys.
        Uses Spotify's public embed manifest.
        """
        entity_type, pid = self.extract_spotify_entity(url)
        if not entity_type or not pid:
            self.fetch_error.emit("Invalid Spotify link. Please paste a valid playlist, album, or song URL.")
            return None

        embed_url = f"https://open.spotify.com/embed/{entity_type}/{pid}"

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        try:
            req = urllib.request.Request(embed_url, headers=headers)
            with urllib.request.urlopen(req, timeout=12.0) as resp:
                page_html = resp.read().decode("utf-8", errors="ignore")

            # Extract Next.js embedded hydration payload
            match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', page_html)
            if not match:
                self.fetch_error.emit("Could not parse Spotify playlist. Ensure the playlist is public.")
                return None

            data = json.loads(match.group(1))
            props = data.get("props", {}).get("pageProps", {})
            state = props.get("state", {}) or props
            entity = state.get("data", {}).get("entity", {}) or props.get("entity", {})

            # Case A: Single Track
            if entity_type == "track":
                t_title = re.sub(r"\s+", " ", html.unescape(entity.get("title") or entity.get("name") or "Track")).strip()
                artists = entity.get("artists", [])
                artist_names = ", ".join(a.get("name", "") for a in artists if a.get("name"))
                t_artist = re.sub(r"\s+", " ", html.unescape(artist_names or entity.get("subtitle") or "")).strip()
                t_dur_ms = int(entity.get("duration", 0))

                query = f"{t_artist} - {t_title}" if t_artist else t_title
                track_item = {
                    "track_number": 1,
                    "total_tracks": 1,
                    "title": t_title,
                    "artist": t_artist,
                    "duration_ms": t_dur_ms,
                    "duration_str": self._format_ms(t_dur_ms),
                    "query": query,
                    "selected": True,
                }
                result = {
                    "id": pid,
                    "title": t_title,
                    "owner": t_artist,
                    "total": 1,
                    "tracks": [track_item],
                    "source_url": url,
                }
                self.playlist_loaded.emit(result)
                return result

            # Case B: Playlist or Album
            title = re.sub(r"\s+", " ", html.unescape(entity.get("title") or entity.get("name") or "Spotify Playlist")).strip()
            subtitle = re.sub(r"\s+", " ", html.unescape(entity.get("subtitle") or "")).strip()
            raw_track_list = entity.get("trackList", [])

            total_items = len(raw_track_list)
            parsed_tracks = []
            for idx, item in enumerate(raw_track_list, start=1):
                t_title = re.sub(r"\s+", " ", html.unescape(item.get("title") or "")).strip()
                t_artist = re.sub(r"\s+", " ", html.unescape(item.get("subtitle") or "")).strip()
                t_dur_ms = int(item.get("duration", 0))

                if not t_title:
                    continue

                query = f"{t_artist} - {t_title}" if t_artist else t_title
                parsed_tracks.append({
                    "track_number": idx,
                    "total_tracks": total_items,
                    "title": t_title,
                    "artist": t_artist,
                    "duration_ms": t_dur_ms,
                    "duration_str": self._format_ms(t_dur_ms),
                    "query": query,
                    "selected": True,
                })

            result = {
                "id": pid,
                "title": title,
                "owner": subtitle,
                "total": len(parsed_tracks),
                "tracks": parsed_tracks,
                "source_url": url,
            }

            self.playlist_loaded.emit(result)
            return result

        except Exception as exc:
            log.error("Failed to fetch Spotify playlist: %s", exc)
            self.fetch_error.emit(f"Error loading Spotify link: {exc}")
            return None

    # -------------------------------------------------------------------------
    # 2. Saved Playlists Library (Zero Keys, Persistent Across Sessions)
    # -------------------------------------------------------------------------

    def get_saved_playlists(self) -> list[dict]:
        """Returns the current list of saved & curated playlists."""
        return list(self._saved_playlists)

    def save_custom_playlist(self, name: str, url: str) -> bool:
        """Adds a custom user playlist to the saved library."""
        name = name.strip()
        url = url.strip()
        if not name or not url:
            return False

        # Avoid duplicates by URL
        for p in self._saved_playlists:
            if p.get("url") == url:
                p["name"] = name
                self._save_to_disk()
                self.saved_playlists_updated.emit(self._saved_playlists)
                return True

        self._saved_playlists.append({
            "name": name,
            "url": url,
            "category": "My Playlists",
        })
        self._save_to_disk()
        self.saved_playlists_updated.emit(self._saved_playlists)
        return True

    def delete_saved_playlist(self, url: str) -> bool:
        """Removes a playlist from the saved library by URL."""
        original_count = len(self._saved_playlists)
        self._saved_playlists = [p for p in self._saved_playlists if p.get("url") != url]
        if len(self._saved_playlists) != original_count:
            self._save_to_disk()
            self.saved_playlists_updated.emit(self._saved_playlists)
            return True
        return False

    def _load_saved_playlists_from_disk(self) -> list[dict]:
        try:
            if os.path.exists(SAVED_PLAYLISTS_FILE):
                with open(SAVED_PLAYLISTS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list) and len(data) > 0:
                        return data
        except Exception as e:
            log.warning("Could not read saved playlists file: %s", e)
        return list(DEFAULT_CURATED_PLAYLISTS)

    def _save_to_disk(self):
        try:
            os.makedirs(os.path.dirname(SAVED_PLAYLISTS_FILE), exist_ok=True)
            with open(SAVED_PLAYLISTS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._saved_playlists, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.warning("Could not persist saved playlists: %s", e)

    # -------------------------------------------------------------------------
    # 3. Optional Developer API (Client Credentials - Advanced Only)
    # -------------------------------------------------------------------------

    def authenticate_api(self, client_id: str, client_secret: str) -> bool:
        """Optional developer credentials authentication."""
        client_id = client_id.strip()
        client_secret = client_secret.strip()
        if not client_id or not client_secret:
            self.fetch_error.emit("Please provide both Client ID and Client Secret.")
            return False

        auth_str = f"{client_id}:{client_secret}"
        b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")

        token_url = "https://accounts.spotify.com/api/token"
        headers = {
            "Authorization": f"Basic {b64_auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode("utf-8")

        try:
            req = urllib.request.Request(token_url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                self.access_token = res_data.get("access_token")
                self.client_id = client_id
                self.client_secret = client_secret
                log.info("[SPOTIFY] Successfully authenticated with Client Credentials.")
                return True
        except Exception as exc:
            log.error("[SPOTIFY] Authentication failed: %s", exc)
            self.fetch_error.emit(f"Spotify Authentication Failed: {exc}")
            return False

    @staticmethod
    def _format_ms(ms: int) -> str:
        """Converts milliseconds to MM:SS format string."""
        if ms <= 0:
            return "--:--"
        total_seconds = int(ms // 1000)
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes:02d}:{seconds:02d}"
