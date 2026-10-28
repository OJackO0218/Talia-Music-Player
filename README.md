# Talia Music Player & Visualizer

## Quick 1-Click Easy Install

### Prerequisites
- **Windows 10 / 11** (64-bit)
- **Python 3.10+** (Make sure **"Add python.exe to PATH"** is checked during Python installation)

### Setup:
1. **Download or Clone** this repository:
   ```bash
   git clone https://github.com/OJackO0218/Talia-Music-Player.git
   cd Talia-Music-Player
   ```
2. **Double-click `install.bat`**:
   - Automatically installs required dependencies (`requirements.txt`).
   - Generates the high-resolution Windows app icon (`assets/icons/app_icon.ico`).
   - Compiles the zero-console native Windows launcher (`Talia.exe`).
   - Creates **Desktop** and **Start Menu** shortcuts.
3. **Launch**:
   - Double-click the **`Talia Visualizer`** shortcut on your Desktop or run **`Talia.exe`**!


## Controls & Behavior

### 1. Interactive Desktop Controls
- **1 Click on Talia**: 
  - Toggles **Play / Pause** `[▶ / ⏸]`.
- **2 Clicks on Talia**: 
  - Skips the current song.
- **3 Clicks on Talia**: 
  - Opens the **Controller Settings Panel**.
- **Holding Talia (Drag Mode & Sinking Shutdown)**:
  - **At 1.0s Mark ("Button Punch")**: Talia punches down signaling that Drag Mode is ready.
  - **Release between 1.0s & 3.0s**: Toggles **Drag Mode** (cyan dashed border appears so you can drag and reposition Talia anywhere).
  - **3.0s – 3.6s (Power-Down)**: power off at 3.6s.

---

### 2. Volume & Cold Machine Eye Saturation
- **Scroll Mouse Wheel on Talia (when Move Mode is OFF)**: Adjust in-app playback volume (5% steps):
  - **At 50% Volume**: Normal original anime eye colors.
  - **Below 50%**: Eyes gradually desaturate to grayscale cold machine eyes (0% = complete mute).
  - **Above 50%**: Eyes hyper-saturate with an electric cyan neon iris glow.

---

### 3. Audio Modes (Built-in Player & Desktop Audio Reactive)
Switch between two audio modes at any time with **`[F10]`** or the **`[ 🎧 AUDIO SOURCE ]`** button:

1. **Desktop Audio Reactive Mode (osu!, Spotify, Games, YouTube)**:
   - Reacts to desktop audio.
   - Global signal to stop/play songs or videos.
3. **Built-in Music Player**:
   - Plays local audio files from your `music/` playlist folder.
   - Supports: **`.opus`**, **`.mp3`**, **`.wav`**, **`.flac`**, **`.ogg`**, and **`.m4a`**.
   - Simply drop your **`.opus`** files directly into the `music/` folder; they are detected and played natively with zero setup

---

### 4. Move Talia Mode (`[F8]` or Hold for 1s)
- **` MOVE TALIA: OFF`** *(Default)*: Talia is locked in place and fully clickable for music controls. No dashed border.
- **` MOVE TALIA: ON`**: A dashed cyan border appears around her. You can click and drag her anywhere across your monitors, or scroll your mouse wheel to resize her from **150px** up to **3840px** (4K).


### 5. Global Hotkeys
| Hotkey | Action |
|---|---|
| **`[F8]`** | Toggle **Move Talia Mode** (Lock / Move & Resize) |
| **`[F9]`** | Toggle **Show / Hide** Talia Overlay |
| **`[F10]`** | Toggle **Audio Source Mode** (Desktop Audio vs Built-in Player) |
