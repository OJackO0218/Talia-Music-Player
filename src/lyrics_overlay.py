"""
Transparent Desktop Lyrics Overlay: Spotify-style synchronized kinetic lyrics
with customizable neon colors, smooth pop-up animations, and click-through background passthrough.
"""

import time
import math
import ctypes
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QPoint, QPointF, QRect, QRectF, QTimer
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QFontMetrics, QPen
)

from config import (
    user32, HWND_TOPMOST, SWP_NOMOVE, SWP_NOSIZE, SWP_NOACTIVATE, SWP_SHOWWINDOW,
    WS_EX_LAYERED, WS_EX_TRANSPARENT, GWL_EXSTYLE, save_settings
)
from audio_engine import CyberAudioEngine
from lyrics_manager import LyricsManager


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

        # Color customization (defaults to Cyberpunk Neon Purple)
        self.color_hex = "#e879f9"
        self.main_color = QColor(232, 121, 249)
        self.bloom_color = QColor(200, 140, 255)
        self.shadow_color = QColor(10, 0, 25)
        self.set_color(self.color_hex)

        # Kinetic pop-up animation state
        self.current_line_idx = -1
        self.displayed_text = ""
        self.pop_progress = 1.0       # 0.0 -> 1.0 cubic ease-out
        self.line_opacity = 0.0        # Smooth 0.0 to 1.0 opacity
        self.glow_flash = 0.0          # Transient luminous pulse on line entry
        self.word_glow = True          # Spotify-style karaoke progressive word-by-word lighting
        self.line_progress = 0.0       # 0.0 -> 1.0 singing progress across the active line

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

        # Default dimensions & position: middle-bottom (not too bottom, 180px above taskbar)
        self.resize(1100, 110)
        self.init_position()

        # By default, lyrics are 100% click-through so they never block games or apps
        self.set_click_through(True)

        # 60 FPS animation & sync tick timer
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._sync_and_animate_tick)
        self.anim_timer.start(16)

        # Topmost enforcement timer (1000ms non-intrusive)
        self.topmost_timer = QTimer(self)
        self.topmost_timer.timeout.connect(self.enforce_topmost)
        self.topmost_timer.start(1000)

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
        if self.isVisible():
            try:
                hwnd = int(self.winId())
                user32.SetWindowPos(
                    hwnd,
                    HWND_TOPMOST,
                    0, 0, 0, 0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW
                )
            except Exception:
                pass

    def set_move_mode(self, enabled: bool):
        """Toggles Move/Repositioning mode. When enabled, displays '(lyrics subtitle is here)' and allows dragging."""
        self.move_mode = enabled
        # When Move Mode is active, disable click-through so user can drag the subtitle box
        self.set_click_through(not enabled)
        if enabled:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            self.displayed_text = "(lyrics subtitle is here)"
            self.pop_progress = 1.0
            self.line_opacity = 1.0
        else:
            self.unsetCursor()
            # Immediately clear '(lyrics subtitle is here)' when move mode is turned off
            if self.displayed_text == "(lyrics subtitle is here)":
                self.displayed_text = ""
                self.current_line_idx = -1
                self.line_opacity = 0.0
        self.update()

    def _sync_and_animate_tick(self):
        """Runs at 60 FPS: syncs current playback position with lyrics and drives pop-up physics."""
        if not self.is_enabled:
            return

        # In Move Mode: always show '(lyrics subtitle is here)' as requested
        if self.move_mode:
            target_text = "(lyrics subtitle is here)"
            if self.displayed_text != target_text:
                self.displayed_text = target_text
                self.pop_progress = 1.0
                self.line_opacity = 1.0
        else:
            # When Move Mode is OFF, remove '(lyrics subtitle is here)' immediately
            if self.displayed_text == "(lyrics subtitle is here)":
                self.displayed_text = ""
                self.current_line_idx = -1
                self.line_opacity = 0.0

            # Normal playback mode: fetch current playback position
            if self.audio_engine.audio_mode == "player" and self.audio_engine.is_playing:
                current_time = self.audio_engine.get_position()
                line_idx, text, time_into_line, singing_dur = self.lyrics_manager.get_current_line_info(current_time)

                if line_idx != self.current_line_idx:
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
            elif self.audio_engine.audio_mode == "desktop":
                self.displayed_text = ""
                self.current_line_idx = -1
                self.line_progress = 0.0

        # Advance pop-up progress (0.0 -> 1.0 over ~200ms)
        if self.pop_progress < 1.0:
            self.pop_progress = min(1.0, self.pop_progress + 0.065)

        # Decay transient glow flash
        if self.glow_flash > 0.005:
            self.glow_flash *= 0.88
        else:
            self.glow_flash = 0.0

        # Target opacity
        has_text = bool(self.displayed_text)
        target_opacity = 1.0 if has_text else 0.0
        self.line_opacity += (target_opacity - self.line_opacity) * 0.18

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # 1. Move Mode Guidance Frame (visible only when repositioning)
        if self.move_mode:
            painter.save()
            guide_pen = QPen(self.bloom_color, 2, Qt.PenStyle.DashLine)
            painter.setPen(guide_pen)
            bg_color = QColor(self.shadow_color.red(), self.shadow_color.green(), self.shadow_color.blue(), 120)
            painter.setBrush(bg_color)
            painter.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 8, 8)

            guide_font = QFont("Segoe UI", 9, QFont.Weight.Bold)
            painter.setFont(guide_font)
            painter.setPen(self.bloom_color)
            painter.drawText(
                QRect(0, 4, self.width(), 20),
                Qt.AlignmentFlag.AlignCenter,
                "DRAG TO REPOSITION LYRICS [F8 OR HOLD TALIA TO LOCK]"
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
        base_pt = 25
        font = QFont()
        font.setFamilies(["Inter", "Circular Std", "Segoe UI Variable Display", "Segoe UI", "Helvetica Neue", "Arial"])
        font.setPointSize(base_pt)
        font.setWeight(QFont.Weight.Bold)

        # Auto shrink-to-fit if text exceeds window width
        metrics = QFontMetrics(font)
        max_w = self.width() - 80
        text_w = metrics.horizontalAdvance(text_to_draw)
        if text_w > max_w and text_w > 0:
            scale_ratio = max_w / float(text_w)
            scaled_pt = max(14, int(base_pt * scale_ratio))
            font.setPointSize(scaled_pt)
            metrics = QFontMetrics(font)

        painter.setFont(font)
        draw_rect = QRect(0, 0, self.width(), self.height())

        # Effective opacity
        eff_opacity = min(1.0, max(0.0, self.line_opacity))
        painter.setOpacity(eff_opacity)

        # Render Spotify-style progressive word-by-word lighting OR full-line mode
        if getattr(self, "word_glow", True) and not self.move_mode:
            try:
                words = [w for w in text_to_draw.split() if w]
                if not words:
                    words = [text_to_draw]
                num_words = len(words)
                space_w = metrics.horizontalAdvance(" ")
                word_widths = [metrics.horizontalAdvance(w) for w in words]
                total_w = sum(word_widths) + space_w * max(0, num_words - 1)
                start_x = (self.width() - total_w) / 2.0
                baseline_y = (self.height() + metrics.ascent() - metrics.descent()) / 2.0

                weights = [max(2, len(w.strip(',.!?\"\''))) for w in words]
                total_weight = max(1.0, float(sum(weights)))
                cum_weight = 0.0
                current_x = start_x

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

                    # Subtle micro-bounce on the currently sung word (lifts up 2.8px then settles)
                    y_bounce = -2.8 * math.sin(p_word * math.pi) if 0.0 < p_word < 1.0 else 0.0
                    pos_pt = QPointF(float(current_x), float(baseline_y + y_bounce))

                    # Layer 1: Ambient Drop Shadow
                    sh_alpha = min(255, max(0, int(230 * eff_opacity * (0.60 + 0.40 * p_word))))
                    painter.setPen(QColor(self.shadow_color.red(), self.shadow_color.green(), self.shadow_color.blue(), sh_alpha))
                    for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, 1), (0, 3)]:
                        painter.drawText(pos_pt + QPointF(float(dx), float(dy)), word)

                    # Layer 2: Radial Bloom Glow (dim when upcoming, peak flare when actively sung, full bloom when sung)
                    if p_word > 0.05:
                        active_flash = 0.60 * math.sin(p_word * math.pi) if p_word < 1.0 else 0.0
                        bloom_alpha = min(255, max(0, int(160 * eff_opacity * min(1.0, p_word) * (1.0 + self.glow_flash + active_flash))))
                        bl_color = QColor(self.bloom_color.red(), self.bloom_color.green(), self.bloom_color.blue(), bloom_alpha)
                        painter.setPen(bl_color)
                        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                            painter.drawText(pos_pt + QPointF(float(dx), float(dy)), word)

                    # Layer 3: Vibrant Foreground Text
                    if p_word <= 0.0:
                        # Upcoming unreached word: soft, elegant ambient translucent slate
                        fg_color = QColor(165, 175, 195, min(255, max(0, int(115 * eff_opacity))))
                    elif p_word < 1.0:
                        # Active word transition flare
                        flare = int(70 * math.sin(p_word * math.pi))
                        r = min(255, max(0, int(165 + (self.main_color.red() - 165) * p_word + flare)))
                        g = min(255, max(0, int(175 + (self.main_color.green() - 175) * p_word + flare)))
                        b = min(255, max(0, int(195 + (self.main_color.blue() - 195) * p_word + flare)))
                        alpha = min(255, max(0, int((115 + (255 - 115) * p_word) * eff_opacity)))
                        fg_color = QColor(r, g, b, alpha)
                    else:
                        # Fully sung word: rich vibrant active theme color
                        flash_boost = int(45 * self.glow_flash)
                        fg_r = min(255, max(0, self.main_color.red() + flash_boost))
                        fg_g = min(255, max(0, self.main_color.green() + flash_boost))
                        fg_b = min(255, max(0, self.main_color.blue() + flash_boost))
                        fg_color = QColor(fg_r, fg_g, fg_b, min(255, max(0, int(255 * eff_opacity))))

                    painter.setPen(fg_color)
                    painter.drawText(pos_pt, word)

                    current_x += w_width + space_w
            except Exception as e:
                # Absolute resilient fallback: if word layout ever encounters edge cases, render full line cleanly
                self._draw_full_line(painter, text_to_draw, eff_opacity)
        else:
            self._draw_full_line(painter, text_to_draw, eff_opacity)

        painter.restore()

    def _draw_full_line(self, painter: QPainter, text_to_draw: str, eff_opacity: float):
        """Renders the entire lyric line with glowing layered drop-shadow and bloom."""
        draw_rect = QRect(0, 0, self.width(), self.height())

        # Layer 1: High-contrast ambient shadow for 100% legibility on light & dark screens
        sh_color = QColor(self.shadow_color.red(), self.shadow_color.green(), self.shadow_color.blue(), min(255, max(0, int(230 * eff_opacity))))
        painter.setPen(sh_color)
        for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, 1), (0, 3)]:
            painter.drawText(draw_rect.translated(dx, dy), Qt.AlignmentFlag.AlignCenter, text_to_draw)

        # Layer 2: Radial Bloom Glow in selected theme color
        bloom_alpha = min(255, max(0, int(140 * eff_opacity * (1.0 + self.glow_flash))))
        bl_color = QColor(self.bloom_color.red(), self.bloom_color.green(), self.bloom_color.blue(), bloom_alpha)
        painter.setPen(bl_color)
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            painter.drawText(draw_rect.translated(dx, dy), Qt.AlignmentFlag.AlignCenter, text_to_draw)

        # Layer 3: Vibrant Luminous Foreground Text
        flash_boost = int(45 * self.glow_flash)
        fg_r = min(255, max(0, self.main_color.red() + flash_boost))
        fg_g = min(255, max(0, self.main_color.green() + flash_boost))
        fg_b = min(255, max(0, self.main_color.blue() + flash_boost))
        fg_color = QColor(fg_r, fg_g, fg_b, min(255, max(0, int(255 * eff_opacity))))
        painter.setPen(fg_color)
        painter.drawText(draw_rect, Qt.AlignmentFlag.AlignCenter, text_to_draw)

    def mousePressEvent(self, event):
        if self.move_mode and event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            self.is_dragging = True
            self.drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.move_mode and self.is_dragging and (event.buttons() & (Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)):
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
                    save_settings(cfg)
                except Exception:
                    pass
            event.accept()
