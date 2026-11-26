# Talia Music Player & Visualizer (v2.6.0)

<img width="317" height="315" alt="Talia Character" src="https://github.com/user-attachments/assets/f19277f1-6acb-4f5e-8b62-ed3fafcd33d5" />

A lightweight transparent desktop character and audio visualizer with eye tracking, synchronized lyrics overlay, endless ★ Random Mix discovery, integrated Lyrics & Calibration Studio, Spotify playlist importing, Listen Together party sync, and low-latency audio reactivity for local files and desktop audio.

---

# Is it Safe?


Yes it's safe, I even submitted it to Microsoft for further analysis.

<img width="1792" height="813" alt="image" src="https://github.com/user-attachments/assets/9940d2ce-1b4c-445e-bc7f-eec610005757" />


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
* **Single Click**: Play / Pause (or start **★ Random Mix** when active).
* **Double Click (Right Side)**: Skip to next track.
* **Double Click (Left Side)**: Rewind / previous track.
* **Triple Click**: Open Player Control Panel.
* **Middle Click**: Save current **★ Random Mix** song permanently to `music/Downloaded Songs/`.
* **Middle / Right Click & Drag**: Reposition Talia anywhere on screen.
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

### Main Panel & Tabs (3 Clicks on Talia)
A compact (380x460) cyberpunk sliding panel beside Talia:
* **Playback & Transport**: Track title, seek scrubber, Rewind, Play/Pause, Next, Shuffle, and smooth volume slider.
* **Playlists & `★ Random Mix`**: Switch between `All Tracks`, `Queue`, `★ Favourites`, folders, custom playlists, or **`★ Random Mix`** (taste-based track discovery with a customizable **Exclude ▾** checklist, 2-ahead buffer, 2-previous retention, and instant permanent saving).
* **Spotify Playlist Sync & Listen Together**: Import public Spotify playlists into Opus 160kbps + `.lrc`, or host/join synchronized listening rooms over Cloud Relay or LAN.

### Settings & Integrated Tools
* **Clean Settings Window**: Tabbed configuration (`General`, `Lyrics & Fonts`, `Visualizer`, `Updates & App`) with live X/Y placement, font customization, subtitle shadow box toggle, Eco Mode, and one-click GitHub auto-updates.
* **Lyrics & Calibration Studio**: Built right into Talia (`Settings > Lyrics & Fonts` or right-click any song -> *Calibrate this song lyric*) — live playback scrubber, double-click cue preview, **`[Space]` beat snap**, background vocal auto-alignment, online candidate search, and folder batch sync.

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

---

## Credits & Attribution

* **Original Character Artwork**: Created by **[Dreamoon-Q](https://x.com/dreamoon131)** ([@dreamoon131](https://x.com/dreamoon131) on X / Twitter). Used under the artist's explicit permission.
* **Character Rigging, Slicing & Visual Modifications**: Live2D layered eye-tracking rig, expression morphs (blinking, drowsy, asleep states), sprite slicing, and animation assets modified by **JackO**.
