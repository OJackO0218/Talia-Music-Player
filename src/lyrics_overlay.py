"""
Transparent Desktop Lyrics Overlay: Spotify-style synchronized kinetic lyrics
with customizable neon colors, smooth pop-up animations, and click-through background passthrough.
"""

import math
import os
import re
import time

from PyQt6.QtCore import QPoint, QPointF, QRect, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QWidget

from audio_engine import CyberAudioEngine
from config import (
    FONTS_DIR,
    GWL_EXSTYLE,
    HWND_TOPMOST,
    SWP_NOACTIVATE,
    SWP_NOMOVE,
    SWP_NOSIZE,
    SWP_SHOWWINDOW,
    WS_EX_TRANSPARENT,
    save_settings,
    user32,
)
from lyrics_manager import LyricsManager

# Pre-allocated QPointF offset arrays for zero-allocation shadow and bloom rendering
SHADOW_OFFSETS_STD = [
    QPointF(-2.0, 0.0),
    QPointF(2.0, 0.0),
    QPointF(0.0, -2.0),
    QPointF(0.0, 2.0),
    QPointF(-1.0, -1.0),
    QPointF(1.0, 1.0),
    QPointF(0.0, 3.0),
]
SHADOW_OFFSET_ECO = QPointF(1.5, 1.5)
BLOOM_OFFSETS = [QPointF(-1.0, 0.0), QPointF(1.0, 0.0), QPointF(0.0, -1.0), QPointF(0.0, 1.0)]

# Cyberpunk 2077 Signature Red Palette (Dialogue Subtitles)
CP2077_RED = QColor(255, 0, 60)              # Primary neon red #ff003c
CP2077_RED_BLOOM = QColor(255, 0, 60, 160)   # Ambient bloom
CP2077_RED_SHADOW = QColor(20, 0, 6, 230)    # Deep drop shadow

# Tight, clean neon glow offsets for Cyberpunk 2077 speaker artist name
CP2077_SPEAKER_GLOW_OFFSETS = [
    QPointF(-1.2, 0.0),
    QPointF(1.2, 0.0),
    QPointF(0.0, -1.2),
    QPointF(0.0, 1.2),
]


class LyricsOverlayWindow(QWidget):
    """Floating transparent desktop lyrics widget with customizable neon colors and click-through passthrough."""

    def __init__(self, audio_engine: CyberAudioEngine, lyrics_manager: LyricsManager):
        super().__init__(None)
        self.audio_engine = audio_engine
        self.lyrics_manager = lyrics_manager
        self.panel = None  # Reference to ControlPanel

        # Visibility and mode flags
        self.is_enabled = True
        self.move_mode = False
        self.dialogue_mode = True  # Cyberpunk 2077 dialogue subtitle mode

        # Color customization (defaults to Cyberpunk Neon Purple)
        self.color_hex = "#e879f9"
        self.main_color = QColor(232, 121, 249)
        self.bloom_color = QColor(200, 140, 255)
        self.shadow_color = QColor(10, 0, 25)
        self.set_color(self.color_hex)

        # Kinetic pop-up animation state
        self.current_line_idx = -1
        self.displayed_text = ""
        self.pop_progress = 1.0  # 0.0 -> 1.0 cubic ease-out
        self.line_opacity = 0.0  # Smooth 0.0 to 1.0 opacity
        self.glow_flash = 0.0  # Transient luminous pulse on line entry
        self.word_glow = True  # Spotify-style karaoke progressive word-by-word lighting
        self.line_progress = 0.0  # 0.0 -> 1.0 singing progress across the active line

        # Pause fade-out state (turns off after 10 seconds of pause)
        self.pause_start_time = None
        self._pause_timed_out = False
        self._last_paused_pos = None

        # Dragging state (only active when move_mode is True)
        self.is_dragging = False
        self.drag_start_pos = QPoint()

        # Window configuration
        self.setMouseTracking(True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Window
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        # Font size & dynamic window dimensions (14pt to 60pt)
        self.base_font_size = 25
        self._update_window_dimensions(keep_center=False)
        self.init_position()

        # By default, lyrics are 100% click-through so they never block games or apps
        self.set_click_through(True)
        self.eco_mode = False

        # Dynamic sleep dirty-check & font metric layout cache
        self._was_rendering = False
        self._cached_layout_key = None
        self._cached_layout_data = None
        self.custom_font_family = None
        self.load_custom_font()

        # 60 FPS animation & sync tick timer
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._sync_and_animate_tick)
        self.anim_timer.start(16)
        self._last_fg_hwnd = 0

        # Topmost enforcement timer (1000ms heartbeat, non-intrusive)
        self.topmost_timer = QTimer(self)
        self.topmost_timer.timeout.connect(self.enforce_topmost)
        self.topmost_timer.start(1000)

    def get_available_fonts(self) -> list:
        """Scans assets/fonts for any user-supplied .ttf or .otf files and returns list of family names."""
        families_list = ["Default (Segoe UI / Inter)"]
        if os.path.exists(FONTS_DIR):
            for f in sorted(os.listdir(FONTS_DIR)):
                if f.lower().endswith((".ttf", ".otf", ".woff", ".woff2")):
                    font_path = os.path.join(FONTS_DIR, f)
                    font_id = QFontDatabase.addApplicationFont(font_path)
                    if font_id != -1:
                        fam = QFontDatabase.applicationFontFamilies(font_id)
                        for name in fam:
                            if name not in families_list:
                                families_list.append(name)
        return families_list

    def set_custom_font(self, family_name: str):
        if not family_name or "Default" in family_name:
            self.custom_font_family = None
        else:
            self.custom_font_family = family_name
        self._cached_layout_key = None
        self.update()

    def load_custom_font(self):
        """Scans assets/fonts for any user-supplied .ttf or .otf files and registers them."""
        self.get_available_fonts()

    def set_eco_mode(self, enabled: bool):
        """Toggles power-saving Eco Mode: drops animation timer to 30 FPS (33ms)."""
        self.eco_mode = enabled
        if enabled:
            self.anim_timer.setInterval(33)  # 30 FPS
        else:
            self.anim_timer.setInterval(16)  # 60 FPS
        self.update()

    def set_color(self, hex_code: str):
        """Sets the active lyrics palette with calculated neon bloom and high-contrast shadow."""
        if not hex_code:
            hex_code = "#e879f9"
        self.color_hex = hex_code
        color = QColor(hex_code)
        if not color.isValid():
            color = QColor("#e879f9")
            self.color_hex = "#e879f9"
        self.main_color = color
        h, s, v, _ = color.getHsv()
        if h == -1:  # grayscale / white
            self.bloom_color = QColor(220, 230, 245)
            self.shadow_color = QColor(10, 12, 18)
        else:
            self.bloom_color = QColor.fromHsv(h, max(20, int(s * 0.65)), min(255, int(v * 1.1)))
            self.shadow_color = QColor.fromHsv(h, min(255, int(s * 1.3)), max(8, int(v * 0.12)))
        self.update()

    def set_click_through(self, click_through: bool):
        """Toggles Win32 WS_EX_TRANSPARENT style so cursor clicks pass straight through."""
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, click_through)
        try:
            hwnd = int(self.winId())
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if click_through:
                new_style = ex_style | WS_EX_TRANSPARENT
            else:
                new_style = ex_style & ~WS_EX_TRANSPARENT
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
        except Exception:
            pass

    @staticmethod
    def clean_dialogue_speaker(artist: str) -> str:
        """Cleans and isolates the primary artist so dialogue speaker tags stay compact and legible."""
        if not artist:
            return ""
        # Split on commas, featuring tags, or slashes (multi-artist ensemble lists)
        split_pattern = r"(?:,|\s+feat\.?|\s+ft\.?|\s+featuring|\s*/\s*|\s+x\s+)"
        parts = re.split(split_pattern, artist, flags=re.IGNORECASE)
        primary = parts[0].strip() if parts else artist.strip()
        # Cap single excessively long names to 28 characters
        if len(primary) > 28:
            primary = primary[:26].rstrip() + "..."
        return primary

    def get_current_artist(self) -> str:
        """Extracts the artist name using Discord Rich Presence parsing rules."""
        raw_title = ""
        if hasattr(self.audio_engine, "get_current_track_title"):
            raw_title = self.audio_engine.get_current_track_title()
        if not raw_title and hasattr(self.audio_engine, "playlist"):
            idx = getattr(self.audio_engine, "current_index", -1)
            if 0 <= idx < len(self.audio_engine.playlist):
                raw_title = os.path.basename(self.audio_engine.playlist[idx])
        if raw_title:
            try:
                from discord_service import parse_track_info
                _, artist = parse_track_info(raw_title)
                if artist and artist not in ("Talia Player", "Talia Music Player", "Unknown Artist"):
                    return self.clean_dialogue_speaker(artist)
            except Exception:
                pass
            clean = os.path.splitext(raw_title)[0].strip()
            if " - " in clean:
                artist = clean.split(" - ", 1)[0].strip()
                if artist:
                    return self.clean_dialogue_speaker(artist)
        return ""

    def init_position(self):
        """Centers horizontally in the middle-bottom of the screen (180px above taskbar)."""
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = max(50, screen.height() - 200)
        self.move(x, y)
        self.raise_()
        self.enforce_topmost()

    def enforce_topmost(self):
        """Ensures the floating lyrics stay visible above background apps without stealing focus."""
        if not self.isVisible():
            return
        try:
            hwnd = int(self.winId())
            user32.SetWindowPos(
                hwnd,
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
            )
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        if self.is_enabled and not self.anim_timer.isActive():
            interval = 33 if getattr(self, "eco_mode", False) else 16
            self.anim_timer.start(interval)

    def hideEvent(self, event):
        super().hideEvent(event)
        self.anim_timer.stop()

    def set_font_size(self, size: int, keep_center: bool = True):
        """Sets the base font size (clamped 14-60 pt) and updates window dimensions."""
        size = max(14, min(60, int(size)))
        if getattr(self, "base_font_size", 25) == size:
            return
        self.base_font_size = size
        self._cached_layout_key = None
        self._update_window_dimensions(keep_center=keep_center)
        self.update()

    def _update_window_dimensions(self, keep_center: bool = True):
        """Dynamically scales window width and height to comfortably fit the current font size."""
        screen = QApplication.primaryScreen()
        screen_geo = screen.geometry() if screen else QRect(0, 0, 1920, 1080)
        # Expanded width by ~56% (+20% then +30%) to fit Cyberpunk dialogue speaker tag comfortably
        target_w = min(screen_geo.width() - 40, max(655, int(self.base_font_size * 36.4)))
        target_h = max(56, int(self.base_font_size * 3.3))

        if keep_center:
            old_center = self.geometry().center()
            self.resize(target_w, target_h)
            new_x = max(0, min(screen_geo.width() - target_w, old_center.x() - target_w // 2))
            new_y = max(0, min(screen_geo.height() - target_h, old_center.y() - target_h // 2))
            self.move(new_x, new_y)
        else:
            self.resize(target_w, target_h)

    def set_move_mode(self, enabled: bool):
        """Toggles Move/Repositioning mode. When enabled, displays '(lyrics subtitle is here)' and allows dragging."""
        self.move_mode = enabled
        # When Move Mode is active, disable click-through so user can drag the subtitle box
        self.set_click_through(not enabled)
        if enabled:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            self.displayed_text = f"(lyrics subtitle is here - {self.base_font_size} pt)"
            self.pop_progress = 1.0
            self.line_opacity = 1.0
        else:
            self.unsetCursor()
            # Immediately clear '(lyrics subtitle is here)' when move mode is turned off
            if self.displayed_text.startswith("(lyrics subtitle is here"):
                self.displayed_text = ""
                self.current_line_idx = -1
                self.line_opacity = 0.0
        self.update()

    def reset_lyrics_display(self) -> None:
        """Immediately clears displayed lyrics and resets animation states."""
        self.displayed_text = ""
        self.current_line_idx = -1
        self.line_opacity = 0.0
        self.pop_progress = 1.0
        self.line_progress = 0.0
        self.glow_flash = 0.0
        self.pause_start_time = None
        self._pause_timed_out = False
        self.update()

    def _sync_and_animate_tick(self):
        """Runs at 60 FPS: syncs current playback position with lyrics and drives pop-up physics."""
        if not self.is_enabled or not self.isVisible():
            self.anim_timer.stop()
            return

        # Ensure floating lyrics stay topmost over full-screen / borderless games when foreground changes
        try:
            curr_fg = user32.GetForegroundWindow()
            if curr_fg != self._last_fg_hwnd:
                self._last_fg_hwnd = curr_fg
                self.enforce_topmost()
        except Exception:
            pass

        # In Move Mode: always show '(lyrics subtitle is here)' as requested
        if self.move_mode:
            target_text = f"(lyrics subtitle is here - {self.base_font_size} pt)"
            if self.displayed_text != target_text:
                self.displayed_text = target_text
                self.pop_progress = 1.0
                self.line_opacity = 1.0
            self.pause_start_time = None
            self._pause_timed_out = False
        else:
            # When Move Mode is OFF, remove '(lyrics subtitle is here)' immediately
            if self.displayed_text.startswith("(lyrics subtitle is here"):
                self.displayed_text = ""
                self.current_line_idx = -1
                self.line_opacity = 0.0

            # Normal playback mode: fetch current playback position
            if self.audio_engine.audio_mode == "player" and self.audio_engine.is_playing:
                current_time = self.audio_engine.get_position()
                line_idx, text, time_into_line, singing_dur = (
                    self.lyrics_manager.get_current_line_info(current_time)
                )
                if self._pause_timed_out:
                    self._pause_timed_out = False
                    self.current_line_idx = line_idx
                    self.displayed_text = text.strip()
                    self.line_opacity = 1.0
                    self.pop_progress = 1.0
                    self.glow_flash = 0.20
                elif line_idx != self.current_line_idx:
                    self.current_line_idx = line_idx
                    self.displayed_text = text.strip()
                    # Trigger kinetic pop-up animation on new line
                    if self.displayed_text:
                        self.pop_progress = 0.0
                        self.glow_flash = 0.40
                if singing_dur > 0.0:
                    self.line_progress = min(1.0, max(0.0, time_into_line / singing_dur))
                else:
                    self.line_progress = 1.0
                self.pause_start_time = None
                self._last_paused_pos = None
            elif self.audio_engine.audio_mode == "player" and not self.audio_engine.is_playing:
                # Paused state: check if timeline was scrubbed while paused
                current_time = self.audio_engine.get_position()
                if self._last_paused_pos is None:
                    self._last_paused_pos = current_time
                elif abs(current_time - self._last_paused_pos) > 0.5:
                    # Scrubbed timeline: refresh lyric for current position and reset 10s timer
                    self._last_paused_pos = current_time
                    self.pause_start_time = time.time()
                    self._pause_timed_out = False
                    line_idx, text, time_into_line, singing_dur = (
                        self.lyrics_manager.get_current_line_info(current_time)
                    )
                    self.current_line_idx = line_idx
                    self.displayed_text = text.strip()
                    if singing_dur > 0.0:
                        self.line_progress = min(1.0, max(0.0, time_into_line / singing_dur))
                    else:
                        self.line_progress = 1.0
                if self.pause_start_time is None:
                    self.pause_start_time = time.time()
                elif (time.time() - self.pause_start_time) >= 10.0:
                    self._pause_timed_out = True
            elif self.audio_engine.audio_mode == "desktop":
                self.displayed_text = ""
                self.current_line_idx = -1
                self.line_progress = 0.0
                self.pause_start_time = None
                self._pause_timed_out = False
                self._last_paused_pos = None

        # Advance pop-up progress (0.0 -> 1.0 over ~200ms)
        if self.pop_progress < 1.0:
            self.pop_progress = min(1.0, self.pop_progress + 0.065)

        # Decay transient glow flash
        if self.glow_flash > 0.005:
            self.glow_flash *= 0.88
        else:
            self.glow_flash = 0.0

        # Target opacity with snap-to-settle
        has_text = bool(self.displayed_text) and not self._pause_timed_out
        target_opacity = 1.0 if has_text else 0.0
        opacity_diff = abs(target_opacity - self.line_opacity)
        self.line_opacity += (target_opacity - self.line_opacity) * 0.18
        if opacity_diff < 0.005:
            self.line_opacity = target_opacity

        # Dynamic sleep dirty-check: do NOT call self.update() when nothing is visible or changing
        is_fading = opacity_diff > 0.005
        is_animating = (self.pop_progress < 1.0) or (self.glow_flash > 0.005) or is_fading
        is_singing = (
            getattr(self, "word_glow", True)
            and has_text
            and (self.line_opacity > 0.01)
            and (self.audio_engine.audio_mode == "player" and self.audio_engine.is_playing)
        )
        needs_update = (
            self.move_mode
            or is_animating
            or is_singing
            or (has_text and self.line_opacity > 0.01 and is_fading)
        )
        if needs_update:
            self.update()
            self._was_rendering = True
        elif getattr(self, "_was_rendering", False):
            self.update()  # One final settle update
            self._was_rendering = False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # 1. Move Mode Guidance Frame (visible only when repositioning)
        if self.move_mode:
            painter.save()
            guide_pen = QPen(self.bloom_color, 2, Qt.PenStyle.DashLine)
            painter.setPen(guide_pen)
            bg_color = QColor(
                self.shadow_color.red(), self.shadow_color.green(), self.shadow_color.blue(), 120
            )
            painter.setBrush(bg_color)
            painter.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 8, 8)
            guide_font = QFont("Segoe UI", 8, QFont.Weight.Bold)
            painter.setFont(guide_font)
            painter.setPen(self.bloom_color)
            painter.drawText(
                QRect(0, 3, self.width(), 16),
                Qt.AlignmentFlag.AlignCenter,
                "DRAG TO REPOSITION | SCROLL WHEEL TO RESIZE [F8 TO LOCK]",
            )
            painter.restore()

        # 2. Render Synchronized Lyrics
        text_to_draw = self.displayed_text
        if not text_to_draw or self.line_opacity < 0.01:
            return
        painter.save()

        # Smooth cubic ease-out
        eased = 1.0 - (1.0 - self.pop_progress) ** 3
        # Pop-up physics: slides up 14px as it appears
        y_slide = 14.0 * (1.0 - eased)
        # Pop scale punch: 0.95 -> 1.0
        pop_scale = 0.95 + 0.05 * eased
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        painter.translate(cx, cy + y_slide)
        painter.scale(pop_scale, pop_scale)
        painter.translate(-cx, -cy)

        # Spotify-style sleek bold typography
        base_pt = getattr(self, "base_font_size", 25)
        font = QFont()
        families = []
        if getattr(self, "custom_font_family", None):
            families.append(self.custom_font_family)
        families.extend(
            [
                "Inter",
                "Circular Std",
                "Segoe UI Variable Display",
                "Segoe UI",
                "Helvetica Neue",
                "Arial",
            ]
        )
        font.setFamilies(families)
        font.setPointSize(base_pt)
        font.setWeight(QFont.Weight.Bold)

        # Cyberpunk 2077 Dialogue Subtitle Speaker
        speaker_text = ""
        if getattr(self, "dialogue_mode", True):
            artist = self.get_current_artist()
            if not artist and (self.move_mode or getattr(self.audio_engine, "is_playing", False)):
                artist = "Talia"
            if artist:
                speaker_text = f"{artist}: "

        # Auto shrink-to-fit if full combined line exceeds window width
        metrics = QFontMetrics(font)
        max_w = self.width() - 36
        full_line = f"{speaker_text}{text_to_draw}" if speaker_text else text_to_draw
        text_w = metrics.horizontalAdvance(full_line)
        if text_w > max_w and text_w > 0:
            scale_ratio = max_w / float(text_w)
            scaled_pt = max(14, int(base_pt * scale_ratio))
            font.setPointSize(scaled_pt)
            metrics = QFontMetrics(font)
        painter.setFont(font)

        # Effective opacity
        eff_opacity = min(1.0, max(0.0, self.line_opacity))
        painter.setOpacity(eff_opacity)

        # Render Spotify-style progressive word-by-word lighting OR full-line mode
        if getattr(self, "word_glow", True) and not self.move_mode:
            try:
                cache_key = (speaker_text, text_to_draw, self.width(), self.height(), font.pointSize())
                if getattr(self, "_cached_layout_key", None) != cache_key:
                    speaker_w = metrics.horizontalAdvance(speaker_text) if speaker_text else 0
                    words = [w for w in text_to_draw.split() if w]
                    if not words:
                        words = [text_to_draw]
                    num_words = len(words)
                    space_w = metrics.horizontalAdvance(" ")
                    word_widths = [metrics.horizontalAdvance(w) for w in words]
                    lyrics_w = sum(word_widths) + space_w * max(0, num_words - 1)
                    total_w = speaker_w + lyrics_w
                    start_x = max(16.0, (self.width() - total_w) / 2.0)
                    baseline_y = (self.height() + metrics.ascent() - metrics.descent()) / 2.0
                    weights = [max(2, len(w.strip(",.!?\"'"))) for w in words]
                    total_weight = max(1.0, float(sum(weights)))
                    self._cached_layout_key = cache_key
                    self._cached_layout_data = (
                        speaker_text,
                        speaker_w,
                        words,
                        word_widths,
                        space_w,
                        total_w,
                        start_x,
                        baseline_y,
                        weights,
                        total_weight,
                    )
                else:
                    (
                        speaker_text,
                        speaker_w,
                        words,
                        word_widths,
                        space_w,
                        total_w,
                        start_x,
                        baseline_y,
                        weights,
                        total_weight,
                    ) = self._cached_layout_data

                # Draw Cyberpunk 2077 Speaker Artist with multi-layer soft holographic neon glow
                if speaker_text:
                    pos_speaker = QPointF(float(start_x), float(baseline_y))
                    self._draw_cyberpunk_speaker(painter, pos_speaker, speaker_text, eff_opacity)

                cum_weight = 0.0
                current_x = start_x + speaker_w
                for i, (word, w_width, weight) in enumerate(zip(words, word_widths, weights)):
                    w_start = cum_weight / total_weight
                    w_end = (cum_weight + weight) / total_weight
                    cum_weight += weight
                    if self.line_progress >= w_end:
                        p_word = 1.0
                    elif self.line_progress <= w_start:
                        p_word = 0.0
                    else:
                        p_word = (self.line_progress - w_start) / max(0.001, (w_end - w_start))
                    p_word = min(1.0, max(0.0, float(p_word)))

                    # Micro-bounce (disabled in eco mode to eliminate math overhead)
                    y_bounce = (
                        (-2.8 * math.sin(p_word * math.pi))
                        if (not self.eco_mode and 0.0 < p_word < 1.0)
                        else 0.0
                    )
                    pos_pt = QPointF(float(current_x), float(baseline_y + y_bounce))

                    # Layer 1: Ambient Drop Shadow
                    sh_alpha = min(255, max(0, int(230 * eff_opacity * (0.60 + 0.40 * p_word))))
                    painter.setPen(
                        QColor(
                            self.shadow_color.red(),
                            self.shadow_color.green(),
                            self.shadow_color.blue(),
                            sh_alpha,
                        )
                    )
                    if self.eco_mode:
                        # Single-pass drop shadow in Eco Mode
                        painter.drawText(pos_pt + SHADOW_OFFSET_ECO, word)
                    else:
                        for offset in SHADOW_OFFSETS_STD:
                            painter.drawText(pos_pt + offset, word)

                    # Layer 2: Radial Bloom Glow (dim when upcoming, peak flare when actively sung, full bloom when sung)
                    if not self.eco_mode and p_word > 0.05:
                        active_flash = 0.60 * math.sin(p_word * math.pi) if p_word < 1.0 else 0.0
                        bloom_alpha = min(
                            255,
                            max(
                                0,
                                int(
                                    115
                                    * eff_opacity
                                    * min(1.0, p_word)
                                    * (1.0 + self.glow_flash + active_flash)
                                ),
                            ),
                        )
                        bl_color = QColor(
                            self.bloom_color.red(),
                            self.bloom_color.green(),
                            self.bloom_color.blue(),
                            bloom_alpha,
                        )
                        painter.setPen(bl_color)
                        for offset in BLOOM_OFFSETS:
                            painter.drawText(pos_pt + offset, word)

                    # Layer 3: Vibrant Foreground Text
                    if p_word <= 0.0:
                        # Upcoming unreached word: soft, elegant ambient translucent slate
                        fg_color = QColor(165, 175, 195, min(255, max(0, int(115 * eff_opacity))))
                    elif p_word < 1.0:
                        # Active word transition flare
                        flare = int(70 * math.sin(p_word * math.pi))
                        r = min(
                            255, max(0, int(165 + (self.main_color.red() - 165) * p_word + flare))
                        )
                        g = min(
                            255, max(0, int(175 + (self.main_color.green() - 175) * p_word + flare))
                        )
                        b = min(
                            255, max(0, int(195 + (self.main_color.blue() - 195) * p_word + flare))
                        )
                        alpha = min(255, max(0, int((115 + (255 - 115) * p_word) * eff_opacity)))
                        fg_color = QColor(r, g, b, alpha)
                    else:
                        # Fully sung word: rich vibrant active theme color
                        flash_boost = int(45 * self.glow_flash)
                        fg_r = min(255, max(0, self.main_color.red() + flash_boost))
                        fg_g = min(255, max(0, self.main_color.green() + flash_boost))
                        fg_b = min(255, max(0, self.main_color.blue() + flash_boost))
                        fg_color = QColor(
                            fg_r, fg_g, fg_b, min(255, max(0, int(255 * eff_opacity)))
                        )
                    painter.setPen(fg_color)
                    painter.drawText(pos_pt, word)
                    current_x += w_width + space_w
            except Exception:
                # Absolute resilient fallback: if word layout ever encounters edge cases, render full line cleanly
                self._draw_full_line(painter, text_to_draw, eff_opacity)
        else:
            self._draw_full_line(painter, text_to_draw, eff_opacity)
        painter.restore()

    def _draw_cyberpunk_speaker(
        self, painter: QPainter, pos: QPointF, text: str, eff_opacity: float
    ):
        """Renders authentic Cyberpunk 2077 dialogue speaker name with razor-sharp readability and clean shadow."""
        if not text:
            return

        # Layer 1: Ambient Drop Shadow for crisp legibility
        sh_alpha = min(255, max(0, int(230 * eff_opacity)))
        painter.setPen(
            QColor(
                CP2077_RED_SHADOW.red(),
                CP2077_RED_SHADOW.green(),
                CP2077_RED_SHADOW.blue(),
                sh_alpha,
            )
        )
        if self.eco_mode:
            painter.drawText(pos + SHADOW_OFFSET_ECO, text)
        else:
            for offset in SHADOW_OFFSETS_STD:
                painter.drawText(pos + offset, text)

        # Layer 2: Tight Neon Red Bloom (noticeably higher glow than lyrics, tight 1.2px halo without letter-blur)
        if not self.eco_mode:
            speaker_glow_alpha = min(
                255,
                max(0, int(150 * eff_opacity * (1.0 + self.glow_flash * 0.35))),
            )
            painter.setPen(
                QColor(
                    CP2077_RED.red(),
                    CP2077_RED.green(),
                    CP2077_RED.blue(),
                    speaker_glow_alpha,
                )
            )
            for offset in CP2077_SPEAKER_GLOW_OFFSETS:
                painter.drawText(pos + offset, text)

        # Layer 3: 100% Crisp, Vibrant Red Text on top (razor-sharp legibility)
        fg_red = QColor(
            CP2077_RED.red(),
            CP2077_RED.green(),
            CP2077_RED.blue(),
            min(255, max(0, int(255 * eff_opacity))),
        )
        painter.setPen(fg_red)
        painter.drawText(pos, text)

    def _draw_full_line(self, painter: QPainter, text_to_draw: str, eff_opacity: float):
        """Renders the entire lyric line with dialogue speaker and layered bloom."""
        speaker_text = ""
        if getattr(self, "dialogue_mode", True):
            artist = self.get_current_artist()
            if not artist and (self.move_mode or getattr(self.audio_engine, "is_playing", False)):
                artist = "Talia"
            if artist:
                speaker_text = f"{artist}: "

        metrics = painter.fontMetrics()
        speaker_w = metrics.horizontalAdvance(speaker_text) if speaker_text else 0
        text_w = metrics.horizontalAdvance(text_to_draw)
        total_w = speaker_w + text_w
        start_x = max(16.0, (self.width() - total_w) / 2.0)
        baseline_y = (self.height() + metrics.ascent() - metrics.descent()) / 2.0

        if speaker_text:
            pos_speaker = QPointF(float(start_x), float(baseline_y))
            self._draw_cyberpunk_speaker(painter, pos_speaker, speaker_text, eff_opacity)

        # Draw lyrics in theme color at start_x + speaker_w
        pos_lyrics = QPointF(float(start_x + speaker_w), float(baseline_y))

        # Layer 1: High-contrast shadow
        sh_color = QColor(
            self.shadow_color.red(),
            self.shadow_color.green(),
            self.shadow_color.blue(),
            min(255, max(0, int(230 * eff_opacity))),
        )
        painter.setPen(sh_color)
        if self.eco_mode:
            painter.drawText(pos_lyrics + SHADOW_OFFSET_ECO, text_to_draw)
        else:
            for offset in SHADOW_OFFSETS_STD:
                painter.drawText(pos_lyrics + offset, text_to_draw)

        # Layer 2: Radial Bloom Glow (-10% intensity for crisp visual comfort)
        bloom_alpha = min(255, max(0, int(100 * eff_opacity * (1.0 + self.glow_flash))))
        bl_color = QColor(
            self.bloom_color.red(), self.bloom_color.green(), self.bloom_color.blue(), bloom_alpha
        )
        painter.setPen(bl_color)
        if not self.eco_mode:
            for offset in BLOOM_OFFSETS:
                painter.drawText(pos_lyrics + offset, text_to_draw)

        # Layer 3: Vibrant Foreground Text
        flash_boost = int(45 * self.glow_flash)
        fg_r = min(255, max(0, self.main_color.red() + flash_boost))
        fg_g = min(255, max(0, self.main_color.green() + flash_boost))
        fg_b = min(255, max(0, self.main_color.blue() + flash_boost))
        painter.setPen(QColor(fg_r, fg_g, fg_b, min(255, max(0, int(255 * eff_opacity)))))
        painter.drawText(pos_lyrics, text_to_draw)

    def wheelEvent(self, event):
        """Scroll wheel in Move Mode resizes the floating lyrics (like Talia character scaling)."""
        if self.move_mode:
            delta = event.angleDelta().y()
            if abs(delta) >= 120:
                step = 2 if delta > 0 else -2
            elif delta != 0:
                step = 1 if delta > 0 else -1
            else:
                step = 0
            if step != 0:
                new_size = max(14, min(60, self.base_font_size + step))
                if new_size != self.base_font_size:
                    self.set_font_size(new_size, keep_center=True)
                    if self.panel:
                        self.panel.sync_lyric_size(new_size)
            event.accept()
        else:
            event.ignore()

    def mousePressEvent(self, event):
        if self.move_mode and event.button() in (
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.RightButton,
            Qt.MouseButton.MiddleButton,
        ):
            self.is_dragging = True
            self.drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if (
            self.move_mode
            and self.is_dragging
            and (event.buttons() & (Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton | Qt.MouseButton.MiddleButton))
        ):
            self.move(event.globalPosition().toPoint() - self.drag_start_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if self.move_mode and self.is_dragging:
            self.is_dragging = False
            # Save new position to settings.json
            if self.panel:
                try:
                    cfg = self.panel.get_current_settings_dict()
                    cfg["lyrics_x"] = self.x()
                    cfg["lyrics_y"] = self.y()
                    cfg["lyrics_font_size"] = self.base_font_size
                    save_settings(cfg)
                except Exception:
                    pass
            event.accept()
