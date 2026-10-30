# Talia Automated Synchronized Lyrics Fetcher

Automated synchronized lyrics fetcher for Talia Music Player. It scans music libraries, extracts embedded metadata, searches public synchronized lyrics databases (mirroring Spotify and Musixmatch timestamps), and saves `.lrc` files directly beside audio files for instant discovery in Talia.

---

## Features

* **Multi-Provider Search**: Automatically queries LRCLIB, Musixmatch, Deezer, and NetEase for high-precision timestamped lyrics (`[mm:ss.xx]`).
* **Embedded Metadata Extraction**: Uses `mutagen` to extract exact Title, Artist, Album, and Duration directly from ID3/FLAC/Vorbis/MP4 tags, avoiding failed matches from messy filenames.
* **Smart Filename Fallback**: If tags are missing, cleans release tags (`1080p`, `Official Video`, `Remastered`) to construct an accurate search query.
* **Auto-Watcher Mode**: Continuously monitors the target music folder in the background. Whenever you drop new songs into the folder or any subfolder, it automatically fetches and writes the `.lrc` file without manual intervention.
* **Cyberpunk GUI & CLI**: Includes both an interactive PyQt6 desktop interface (`gui_fetcher.py`) and a command-line utility (`fetch_lyrics.py`).

---

## How to Run

### 1. Graphical Interface (Recommended)
Double-click **`run_fetcher.bat`** or run:
```bash
python gui_fetcher.py
```
* **Browse**: Select your music folder (defaults to Talia's active music folder).
* **Fetch All Missing Lyrics**: Scans and downloads `.lrc` files for all untagged songs.
* **Auto-Watch Folder**: Check this box to leave the fetcher monitoring in the background while you add songs.

### 2. Command Line Interface
Scan a folder and download all missing `.lrc` files:
```bash
python fetch_lyrics.py --folder "C:\path\to\music"
```

Force overwrite existing `.lrc` files:
```bash
python fetch_lyrics.py --folder "C:\path\to\music" --force
```

Run in live continuous watcher mode:
```bash
python fetch_lyrics.py --folder "C:\path\to\music" --watch
```
