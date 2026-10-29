# Talia Music Player & Visualizer

<img width="317" height="315" alt="image" src="https://github.com/user-attachments/assets/f19277f1-6acb-4f5e-8b62-ed3fafcd33d5" />

A transparent desktop audio visualizer with eye tracking, synchronized lyrics overlay, and low-latency audio reactivity for desktop audio and local playlists.

---

## Download & Installation

### Option A: Portable Application (Recommended - No Python Needed)
1. Download **[Talia-Windows-x64.zip](https://github.com/OJackO0218/Talia-Music-Player/releases/latest)** from the Releases page.
2. Extract the archive to any folder.
3. Run **`Talia.exe`**.

---

### Option B: Run from Source
1. Clone or download the repository:
   ```bash
   git clone https://github.com/OJackO0218/Talia-Music-Player.git
   cd Talia-Music-Player
   ```
2. Run `install.bat` or install requirements manually:
   ```bash
   pip install -r requirements.txt
   python src/main.py
   ```

---

## Controls

### Interactive Mouse Controls on Talia
* **Single Click**: Play / Pause.
* **Double Click (Right Side)**: Skip to next track.
* **Double Click (Left Side)**: Rewind / previous track.
* **Triple Click**: Open Controller Settings panel.
* **Hold for 0.7s (SFX confirmation)**: Toggle Move Mode (unlocks dragging and resizing).
* **Hold for 2s**: Exit application.

### Mouse Wheel
* **Normal Mode**: Adjusts playback volume (reflected in pupil saturation).
* **Move Mode Active**: Scales character size from 150px to 4K resolution.

---

## Synchronized Lyrics & Singalong

* **Real-Time Desktop Overlay**: Synchronized lyrics pop up line-by-line during playback.
* **Singalong Mode**: Progressively highlights each active word as it is sung.
* **Click-Through**: The lyrics overlay ignores mouse clicks during playback so it never blocks desktop interactions.
* **Color Customization**: Choose from neon presets (Neon Purple, Neon Cyan, Neon Pink, Cyber Yellow, Matrix Green, Pure White) or choose any custom color.
* **Automatic Discovery & Caching**: Looks for `.lrc` files located next to tracks in any folder, with automatic retrieval and local caching for untagged files.

---

## Music Library, Search & Queue

* **Recursive Folder Loading**: Select a music directory to load all supported tracks from nested subfolders (`Artist/Album/track.flac`) as well as root-level files.
* **Supported Formats**: `.mp3`, `.wav`, `.flac`, `.ogg`, `.m4a`, and `.opus`.
* **Live Search**: Instant real-time filter by track title, filename, or subfolder path.
* **Playback Queue**:
  * Add songs to the upcoming queue using the `+ QUEUE` button or by right-clicking any track.
  * Right-click options: **Play Now**, **Add to Queue**, **Play Next**, and **Show in Explorer**.
  * Queued songs take priority on finish or skip, then smoothly return to standard playlist order.
  * Click `QUEUE (N)` to view, remove individual items, or clear the queue.

---

## Audio Modes

Toggle modes at any time with **`[F10]`** or through the Controller panel:

1. **Local Music Player**:
   * Plays audio files loaded from your selected folder.
   * Full timeline scrubbing, lyrics synchronization, and queueing.
2. **Desktop Audio (WASAPI Loopback)**:
   * Captures and reacts to active desktop audio (games, browser playback, media players).
   * Talia clicks pass global media signals (Play/Pause, Next Track, Prev Track) to the system.

---

## Global Hotkeys

| Hotkey | Action |
|---|---|
| **`[F7]`** | Toggle Synced Lyrics Overlay on / off |
| **`[F8]`** | Toggle Move Mode (reposition and scale Talia & lyrics) |
| **`[F9]`** | Toggle Hide / Show Talia and lyrics |
| **`[F10]`** | Switch Audio Mode (Local Player vs Desktop Audio) |
