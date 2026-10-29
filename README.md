# Talia Music Player & Visualizer



<img width="317" height="315" alt="image" src="https://github.com/user-attachments/assets/f19277f1-6acb-4f5e-8b62-ed3fafcd33d5" />



A transparent desktop audio visualizer with eye tracking, tactile controls, and low-latency audio reactivity for desktop audio (osu!, Spotify, games) and local playlists.

---

## Quick Install

### Prerequisites
- **Windows 10 / 11** (64-bit)
- **Python 3.10+** (Ensure **"Add python.exe to PATH"** is checked during installation)

### Setup
1. **Clone or Download** this repository:
   ```bash
   git clone https://github.com/OJackO0218/Talia-Music-Player.git
   cd Talia-Music-Player
   ```
2. **Double-click `install.bat`**:
   - Installs dependencies (`requirements.txt`).
   - Compiles native launcher (`Talia.exe`).
   - Creates Desktop and Start Menu shortcuts.
3. **Launch**:
   - Run `Talia.exe` (automatically runs as Administrator) or use the Desktop shortcut.

---

## Controls & Behavior

### 1. Interactive Desktop Controls
- **1 Click on Talia**: 
  - Toggles **Play / Pause** (displays a cyber mute indicator inside the mouth when paused).
- **2 Clicks on Talia**: 
  - Skips to the next track.
- **3 Clicks on Talia**: 
  - Opens the **Controller Settings Panel**.
- **Holding Talia**:
  - **Hold for 0.7s**: Tactile button press unlocks **Drag Mode** to reposition or resize.
  - **Hold for 2s**: Initiates power-down sequence and closes the application cleanly.

---

### 2. Volume & Eye Saturation
- **Scroll Mouse Wheel on Talia (when Move Mode is OFF)**:
  - **Live / Desktop Audio Mode**: Adjusts laptop master system audio directly (native Windows volume HUD) while syncing eye saturation.
  - **Built-in Player Mode**: Adjusts Talia local music playback volume.
  - **50% Volume**: Default eye saturation.
  - **Below 50%**: Eyes gradually desaturate toward grayscale (0% = mute).
  - **Above 50%**: Eyes hyper-saturate with a cyan neon glow.

---

### 3. Audio Modes
Toggle modes anytime with **`[F10]`** or via the Controller panel:

1. **Desktop Audio Reactive Mode (osu!, Spotify, Games, YouTube)**:
   - Reacts to any desktop audio playing through your system via WASAPI loopback.
   - Clicks on Talia send global media Play/Pause and Skip signals to active apps.
2. **Built-in Music Player**:
   - Plays local audio from the `music/` folder.
   - Supports: **`.opus`**, **`.mp3`**, **`.wav`**, **`.flac`**, **`.ogg`**, and **`.m4a`**.
   - Drop songs into `music/` to load them automatically.

---

### 4. Move Talia Mode (`[F8]` or Hold 0.7s)
- **`MOVE TALIA: OFF`** *(Default)*: Talia is locked in place and clickable for controls.
- **`MOVE TALIA: ON`**: Dashed border appears. Click and drag to reposition anywhere on your screens, or scroll the mouse wheel to resize (150px to 4K).

---

### 5. Global Hotkeys
| Hotkey | Action |
|---|---|
| **`[F8]`** | Toggle **Move Talia Mode** (Lock / Reposition & Resize) |
| **`[F9]`** | Toggle **Show / Hide** Talia Overlay |
| **`[F10]`** | Toggle **Audio Source Mode** (Desktop Audio vs Built-in Player) |
