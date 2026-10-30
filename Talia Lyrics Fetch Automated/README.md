# Talia Automated Synchronized Lyrics Fetcher

Automated synchronized lyrics fetcher and interactive calibrator for Talia Music Player. It scans music libraries, extracts embedded metadata, searches public synchronized lyrics databases (mirroring Spotify and Musixmatch timestamps), and saves `.lrc` files directly beside audio files for instant discovery in Talia.

---

## Features

* **Multi-Provider Search**: Automatically queries LRCLIB, Musixmatch, Deezer, and NetEase for high-precision timestamped lyrics (`[mm:ss.xx]`).
* **Duration Proximity Scoring**: Matches audio track length against candidate submissions to prioritize authentic releases and filter out stretched or half-speed uploads.
* **Interactive Sync Calibrator**:
  * Embedded audio player with seek bar and live timecode readout.
  * **Tap-to-Sync (Spacebar)**: Tap when the first vocal word is sung to align lyrics with millisecond precision.
  * **Online Candidate Search**: Inspect and switch between alternative submissions directly from the UI.
  * **Non-Destructive Boundary Health Checks**: Validates outro margins and guards against destructive shifts on tracks with instrumental intros.
* **Embedded Metadata Extraction**: Uses `mutagen` to extract exact Title, Artist, Album, and Duration directly from ID3/FLAC/Vorbis/MP4 tags.
* **Smart Filename Fallback**: Cleans release qualifiers (`1080p`, `Official Video`, `Remastered`, YouTube hashes) to construct clean search queries.
* **Auto-Watcher Mode**: Continuously monitors the target music folder in the background. Whenever you drop new songs into the folder, it automatically fetches and writes the `.lrc` file without manual intervention.
* **Cyberpunk GUI & CLI**: Includes both an interactive PyQt6 desktop interface (`gui_fetcher.py`) and a command-line utility (`fetch_lyrics.py`).

---

## Installation & Setup

1. Make sure Python 3.10+ is installed on your system.
2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

---

## How to Run

### 1. Graphical Interface (Recommended)
Double-click **`run_fetcher.bat`** or run:
```bash
python gui_fetcher.py
```
* **Batch Folder Sync**: Select your music folder and download `.lrc` files for all tracks with one click.
* **Auto-Watch Folder**: Leave the fetcher monitoring in the background while you add songs.
* **Sync Calibrator**: Play any track, tap Spacebar to align, or search for alternate online candidates.

### 2. Command Line Interface
Scan a folder and download all missing `.lrc` files:
```bash
python fetch_lyrics.py --folder "C:\path\to\music"
```

Force overwrite existing `.lrc` files (creates `.lrc.bak` backups):
```bash
python fetch_lyrics.py --folder "C:\path\to\music" --force
```

Run in live continuous watcher mode:
```bash
python fetch_lyrics.py --folder "C:\path\to\music" --watch
```
