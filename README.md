# Talia Music Player & Visualizer

<img width="317" height="315" alt="Talia Character" src="https://github.com/user-attachments/assets/f19277f1-6acb-4f5e-8b62-ed3fafcd33d5" />

A lightweight transparent desktop character and audio visualizer with eye tracking, synchronized lyrics overlay, YouTube song search & auto-downloader, and low-latency audio reactivity for local files and desktop audio.

---

## Download & Installation

### Option A: Portable Application (Recommended - No Python Needed)
1. Download **[Talia-Windows-x64.zip](https://github.com/OJackO0218/Talia-Music-Player/releases/latest)** from the Releases page.
2. Extract the archive to any folder.
3. Run **`Talia.exe`**.

---

### Option B: Run from Source
1. Clone the repository:
   ```bash
   git clone https://github.com/OJackO0218/Talia-Music-Player.git
   cd Talia-Music-Player
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Launch Talia:
   ```bash
   python src/main.py
   ```

---

## Controls

### Interactive Mouse Controls on Talia
* **Single Click**: Play / Pause.
* **Double Click (Right Side)**: Skip to next track.
* **Double Click (Left Side)**: Rewind / previous track.
* **Triple Click**: Open Minimal Player window.
* **Hold for 0.7s**: Toggle Move Mode (unlocks dragging and resizing).
* **Hold for 2s**: Exit application.

### Mouse Wheel
* **Normal Mode**: Adjusts playback volume (synced to pupil saturation).
* **Move Mode Active**: Resizes Talia character smoothly from 150px up to 4K.

---

## Global Hotkeys

| Hotkey | Action |
|---|---|
| **`[F7]`** | Toggle Synced Lyrics Overlay on / off |
| **`[F8]`** | Toggle Move Mode (drag/resize Talia & lyrics) |
| **`[F9]`** | Toggle Hide / Show Talia and lyrics |
| **`[F10]`** | Switch Audio Mode (Local Player vs Desktop Audio) |
| **`[F11]`** | Toggle Eco Mode (< 1% CPU power-saving) |
| **`[Ctrl + []`** | Shift lyrics 0.25s earlier |
| **`[Ctrl + ]]`** | Shift lyrics 0.25s later |

---

## Interface: Player & Settings

### Minimal Player Window (3 Clicks on Talia)
A compact (380x560) floating window designed for clean day-to-day playback:
* **Playback & Volume**: Track title, timeline scrub slider, Rewind, Play/Pause, Next, Shuffle, and volume slider.
* **Song Selection**: Real-time song search with instant filtering, clean track list, and queue management (`+ Queue`, `Queue (N)`, `Clear`).
* **Download Songs**: Built-in YouTube search, match selection, and one-click library download.
* **Top Bar**: Fast mode toggles (`Lock Window`, `Player Mode`, `Lyrics`, `Eco Mode`) and the **`⚙ Settings`** button.

### Full Settings Center (Click `⚙ Settings`)
A comprehensive customization hub containing:
* **Playback Modes**: Quick toggles for window lock, audio source, lyrics visibility, and Eco Mode.
* **Music Folder**: Active directory display, folder picker, explorer shortcut, and library re-scan.
* **Lyrics Customization**: Font selector dropdown, custom color picker, word highlight glow animation toggle, and manual/auto-sync offset tools.
* **Visualizer Engine**: Visualizer styles (`Cyber Bars`, `Neon Wave`, `Radial Core`, `Dual Mirror`) and color palette themes.
* **Character & Display**: Eye sensitivity, character scale, opacity, bass pop reaction, and widescreen mode.
* **System Actions**: Save settings, controls guide, asset reloader, and clean application exit.

---

## Built-in Song Search & Auto-Downloader

1. Open the Player window (triple click Talia).
2. Under **Download Songs**, enter a track title or paste a YouTube URL and click **Search**.
3. Select the desired track from the results and click **+ Add to Library**.
4. Talia automatically:
   * Downloads and converts audio to 160kbps Opus format.
   * Places it inside your music folder.
   * Fetches synchronized `.lrc` lyrics from LRCLIB and caches them locally.
   * Refreshes the tracklist and selects the new song.

---

## Synchronized Lyrics & Custom Fonts

* **Line-by-Line Overlay**: Displays synced lyrics on top of your games and apps without stealing window focus or blocking clicks.
* **Singalong Word Glow**: Highlights words in real-time as they are sung.
* **Custom Font Dropdown**: Drop any `.ttf` or `.otf` font file into `assets/fonts/`, open **Settings**, and pick it from the **Font** dropdown. Click **Reload** to refresh detected fonts instantly.
* **Sync Offset Controls**: Adjust timing on the fly (`-0.5s`, `-0.1s`, `+0.1s`, `+0.5s`, `Reset`, or `Auto-Sync`).

---

## Audio Modes

Switch modes at any time with **`[F10]`** or via the interface:

1. **Local Player**:
   * Streams audio directly from your selected folder.
   * Full timeline scrubbing, lyrics synchronization, and queue prioritization.
2. **Desktop Audio (WASAPI Loopback)**:
   * Real-time visualizer reactivity to active desktop audio (Spotify, browsers, games, Discord).
   * Talia clicks pass global media signals (Play/Pause, Next, Previous) to Windows.

---

## Specifications & Performance

* **RAM Footprint**: Under 200 MB (uses SoundFile block streaming and single-track 15-second head preloading).
* **CPU Usage**: Under 1% in Eco Mode (`[F11]`).
* **Supported Audio Formats**: `.mp3`, `.wav`, `.flac`, `.ogg`, `.m4a`, `.opus`.
* **OS**: Windows 10 / 11 (64-bit).
