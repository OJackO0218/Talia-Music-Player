# 🎧 Talia Music Player & Cyberpunk Visualizer

Watch real-time, audio-reactive Cyberpunk visualizers pulse directly inside Talia's open mouth while her mechanical eye rig tracks your mouse crosshair across your desktop at 60 FPS! 

Includes tactile feedback inspired by osu! lazer, custom sound effects, desktop audio loopback (for osu!, Spotify, and games), and a native Windows launcher.

---

## ⚡ Quick 1-Click Easy Install

### Prerequisites
- **Windows 10 / 11** (64-bit)
- **Python 3.10+** (Make sure **"Add python.exe to PATH"** is checked during Python installation)

### 🚀 1-Click Setup:
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

---

## 📁 Clean Project Structure

```text
Talia-Music-Player/
├── ⚡ Talia.exe         <-- [Double-click to Run App!]
├── 🔧 install.bat       <-- [1-Click Setup for New Users]
│
├── 📂 music/           <-- [Drop your .opus, .mp3, .wav songs here]
│   └── Cyberpunk Edgerunners/
│
├── 📂 assets/          <-- [Character sprites, audio SFX & icons]
│   ├── eye_parts/      <-- Character sprites & eye rig layers
│   ├── sounds/         <-- Tactile low-latency sound effects
│   └── icons/          <-- App icons & art
│
├── 📂 src/             <-- [Application Source Code]
│   ├── main.py         <-- Application bootstrap & single-instance lock
│   ├── overlay.py      <-- Live2D character overlay & tactile animations
│   ├── controller.py   <-- Settings & tracklist control panel
│   ├── audio_engine.py <-- Playback & WASAPI desktop loopback
│   ├── visualizer.py   <-- Cyberpunk mouth FFT visualizer
│   └── config.py       <-- Geometry coordinates & persistent settings
│
├── 📂 tools/           <-- [Utility Scripts]
│   ├── setup_windows_app.py
│   ├── push_to_github.bat
│   ├── refresh_icon_cache.bat
│   └── run_as_admin.bat
│
├── 📄 README.md
└── 📄 requirements.txt
```

---

## 🌟 Controls & Behavior

### 1. Interactive Desktop Controls (osu! lazer Tactile Feedback & SFX)
Talia is **not click-through**, meaning you can interact directly with her on your desktop with snappy visual and tactile sound effects:
- **Snappy Pop-Up Entrance on Startup ($\le 0.20$s)**:
  - When Talia launches, she smoothly glides UP into place from below her resting position with a crisp **Pop SFX** `[🫧]` in under **0.2 seconds**, welcoming you to your desktop!
- **Hovering Cursor on Talia**: 
  - Plays a crisp **Bubble Pop SFX** `[🫧]`.
  - Brightens up with a noticeable **~20% luminous bloom highlight** + subtle 1.2% breathing pop!
  - Gives a smooth **left-right rocking tilt** ($\sim \pm 1.8^\circ$) as your cursor enters her space so she playfully reacts to your crosshair.
- **1 Click on Talia**: 
  - Plays a tactile **Mechanical Button SFX** `[🔊]`.
  - Lights up **Pure White `[⚪]`** (holds solid for **0.24s**, then smoothly dissolves) + tactile rotational bounce $\rightarrow$ Toggles **Play / Pause** `[▶ / ⏸]`.
- **2 Clicks on Talia**: 
  - Plays the button click SFX and flashes **White** then **Crimson Red `[⚪ 🔴]`** (holds solid for **0.24s**) $\rightarrow$ Skips to **Next Track** `[⏭]`.
- **3 Clicks on Talia**: 
  - Plays the button click SFX and flashes **White**, **Red**, then **Electric Gold `[⚪ 🔴 🟡]`** (holds solid for **0.24s**) $\rightarrow$ Opens the **Controller Settings Panel**.
- **Holding Talia (Drag Mode & Sinking Shutdown)**:
  - **0.0s – 1.0s**: Gentle rocking with an escalating synth riser and bubbling audio track.
  - **At 1.0s Mark ("Button Punch")**: Talia punches down 50% deeper to **`0.885` scale** (11.5% compression) with an 80ms bottom-out delay and tactile click sound, signaling that Drag Mode is ready!
  - **Release between 1.0s & 3.0s**: Toggles **Drag Mode** (cyan dashed border appears so you can drag and reposition Talia anywhere).
  - **2.0s – 3.0s (Overload)**: Talia desaturates toward cold grayscale and **rocks harder and faster** ($\pm 1.4^\circ$ to $\pm 5.4^\circ$ tilt) as power drains!
  - **3.0s – 3.6s (Sinking Power-Down)**: Instead of an abrupt cut, an authentic **heavy sci-fi reactor shutdown sound** plays while Talia smoothly accelerates and **sinks downward below the desktop screen**, powering off gracefully at 3.6s!

---

### 2. 🎵 Bass Beat Pop (osu! Bop Effect)
- Talia rhythmically pulses and pops (+3% to +4% scale bounce) to the kick drum and bass drops of whatever song is playing!
- Works in both **Built-in Player** mode and **Desktop Audio** loopback mode.
- Can be toggled ON/OFF anytime in the Controller panel (`[✔] 🎵 Bass Beat Pop`).

---

### 3. Volume & Cold Machine Eye Saturation
- **Scroll Mouse Wheel on Talia (when Move Mode is OFF)**: Adjust in-app playback volume (5% steps):
  - **At 50% Volume**: Normal original anime eye colors.
  - **Below 50%**: Eyes gradually desaturate to grayscale cold machine eyes (0% = complete mute).
  - **Above 50%**: Eyes hyper-saturate with an electric cyan neon iris glow!

---

### 4. Audio Modes (Built-in Player & Desktop Audio Reactive)
Switch between two audio modes at any time with **`[F10]`** or the **`[ 🎧 AUDIO SOURCE ]`** button:

1. **🎧 Desktop Audio Reactive Mode (osu!, Spotify, Games, YouTube)**:
   - **Zero Storage (0 MB)**: Listens directly to whatever audio is playing through your headphones or speakers in real time via low-latency Windows WASAPI loopback.
   - Play **osu!**, listen to **Spotify**, watch **YouTube**, or game while Talia's mouth visualizer dances to your game music and beat drops!
   - **System Media Controls**: 1-click on Talia sends a system Play/Pause media command (e.g. pauses Spotify), and 2-clicks skips to the next track.
2. **🎵 Built-in Cyberpunk Music Player**:
   - Plays local audio files from your `music/` playlist folder.
   - Supports: **`.opus`**, **`.mp3`**, **`.wav`**, **`.flac`**, **`.ogg`**, and **`.m4a`**.
   - Simply drop your **`.opus`** files directly into the `music/` folder; they are detected and played natively with zero setup!

---

### 5. Move Talia Mode (`[F8]` or Hold for 1s)
- **`🔒 MOVE TALIA: OFF`** *(Default)*: Talia is locked in place and fully clickable for music controls. No dashed border.
- **`🖐️ MOVE TALIA: ON`**: Repositioning mode is active! A dashed cyan border appears around her. You can click and drag her anywhere across your monitors, or scroll your mouse wheel to resize her from **150px** up to **3840px** (4K).

---

### 6. Cyberpunk Audio Visualizers (4 Modes & 4 Palettes)
- 📊 **Cyber Bars**: Logarithmic equalizer with segmented LED blocks and gravity peak caps.
- 〰️ **Neon Wave**: Dual-layer glowing oscilloscope ECG wave.
- 🎯 **Radial Core**: Spinning cyber targeting reticles with an audio-reactive reactor core.
- ⚡ **Dual Mirror**: Symmetrical dual-sided equalizer extending outward from the center.

Palettes:
- 🩵 **Cyber Cyan**: Neon cyan & electric magenta
- 💛 **Neon Gold**: High-voltage amber & golden yellow
- 💚 **Matrix Green**: Terminal green & phosphor lime
- 💜 **Synthwave Violet**: Deep purple & neon crimson

---

### 7. Global Hotkeys
| Hotkey | Action |
|---|---|
| **`[F8]`** | Toggle **Move Talia Mode** (Lock / Move & Resize) |
| **`[F9]`** | Toggle **Show / Hide** Talia Overlay |
| **`[F10]`** | Toggle **Audio Source Mode** (Desktop Audio vs Built-in Player) |

---

### 8. Native Windows App & Taskbar Pinning
Talia includes a compiled native launcher (`Talia.exe`) with a custom multi-layer Windows icon and **zero black terminal window**:
- **Pin to Taskbar**: Right-click `Talia.exe` or the Desktop shortcut $\rightarrow$ **"Pin to taskbar"**.
- **Start Menu**: Press `Win`, type `Talia`, and press Enter to launch anytime.
- **Power Off**: Click the `[🛑 Power Off & Exit Talia]` button in the Controller panel, or hold Talia for 3 seconds to trigger the sinking power-down sequence.
