"""
Transparent Desktop Lyrics Overlay: Spotify-style synchronized kinetic lyrics
with neon purple cyberpunk typography, smooth pop-up animations, and drag repositioning.
"""

import time
import math
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QPoint, QRect, QRectF, QTimer
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QFontMetrics, QPen, QLinearGradient, QPainterPath
)

from config import (
    user32, HWND_TOPMOST, SWP_NOMOVE, SWP_NOSIZE, SWP_NOACTIVATE, SWP_SHOWWINDOW,
    save_settings
)
from audio_engine import CyberAudioEngine
from lyrics_manager import LyricsManager


class LyricsOverlayWindow(QWidget):
    """Floating transparent desktop lyrics widget displaying synchronized neon purple lyrics."""

    def __init__(self, audio_engine: CyberAudioEngine, lyrics_manager: LyricsManager):
        super().__init__(None)
        self.audio_engine = audio_engine
        self.lyrics_manager = lyrics_manager
        self.panel = None  # Reference to ControlPanel

        # Visibility and mode flags
        self.is_enabled = True
        self.move_mode = False  # True when Move Talia Mode is active (enables bounding box & dragging)

        # Kinetic pop-up animation state
        self.current_line_idx = -1
        self.displayed_text = ""
        self.pop_progress = 1.0       # 0.0 -> 1.0 cubic ease-out
        self.line_opacity = 0.0        # Smooth 0.0 to 1.0 opacity
        self.glow_flash = 0.0          # Transient luminous pulse on line entry
        self.font_scale = 1.0

        # Dragging state
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

        # Default dimensions & position: middle-bottom (not too bottom)
        self.resize(1100, 110)
        self.init_position()

        # 60 FPS animation & sync tick timer
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._sync_and_animate_tick)
        self.anim_timer.start(16)

        # Topmost enforcement timer (1000ms non-intrusive)
        self.topmost_timer = QTimer(self)
        self.topmost_timer.timeout.connect(self.enforce_topmost)
        self.topmost_timer.start(1000)

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
        """Toggles Move/Repositioning mode synchronized with Talia Move Mode."""
        self.move_mode = enabled
        self.update()

    def _sync_and_animate_tick(self):
        """Runs at 60 FPS: syncs current playback position with lyrics and drives pop-up physics."""
        if not self.is_enabled:
            return

        # 1. Fetch current playback position from audio engine
        if self.audio_engine.audio_mode == "player" and self.audio_engine.is_playing:
            current_time = self.audio_engine.get_position()
            line_idx, text, _ = self.lyrics_manager.get_current_line(current_time)

            if line_idx != self.current_line_idx:
                self.current_line_idx = line_idx
                self.displayed_text = text.strip()
                # Trigger kinetic pop-up animation on new line
                if self.displayed_text:
                    self.pop_progress = 0.0
                    self.glow_flash = 0.40
        elif self.audio_engine.audio_mode == "desktop":
            self.displayed_text = ""
            self.current_line_idx = -1

        # 2. Advance pop-up progress (0.0 -> 1.0 over ~200ms)
        if self.pop_progress < 1.0:
            self.pop_progress = min(1.0, self.pop_progress + 0.065)

        # 3. Decay transient glow flash
        if self.glow_flash > 0.005:
            self.glow_flash *= 0.88
        else:
            self.glow_flash = 0.0

        # 4. Target opacity: 1.0 if text is present and audio playing/paused, 0.0 if empty
        has_text = bool(self.displayed_text)
        target_opacity = 1.0 if has_text else (0.4 if self.move_mode else 0.0)
        self.line_opacity += (target_opacity - self.line_opacity) * 0.18

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # 1. Move Mode Guidance Frame (visible only when repositioning)
        if self.move_mode:
            painter.save()
            guide_pen = QPen(QColor(192, 132, 252, 180), 2, Qt.PenStyle.DashLine)
            painter.setPen(guide_pen)
            painter.setBrush(QColor(25, 0, 45, 80))
            painter.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 8, 8)

            guide_font = QFont("Segoe UI", 9, QFont.Weight.Bold)
            painter.setFont(guide_font)
            painter.setPen(QColor(232, 121, 249, 200))
            painter.drawText(
                QRect(0, 4, self.width(), 20),
                Qt.AlignmentFlag.AlignCenter,
                "// DRAG TO REPOSITION LYRICS OVERLAY [F8 TO LOCK]"
            )
            painter.restore()

        # 2. Render Synchronized Neon Purple Lyrics
        text_to_draw = self.displayed_text
        if not text_to_draw and self.move_mode:
            text_to_draw = "Neon Purple Synced Lyrics (Drag anywhere)"

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

        # Effective opacity combined with fade and glow flash
        eff_opacity = min(1.0, max(0.0, self.line_opacity))
        painter.setOpacity(eff_opacity)

        # Layer 1: High-contrast ambient shadow for 100% legibility on light & dark screens
        shadow_color = QColor(10, 0, 25, int(220 * eff_opacity))
        painter.setPen(shadow_color)
        for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, 1), (0, 3)]:
            painter.drawText(draw_rect.translated(dx, dy), Qt.AlignmentFlag.AlignCenter, text_to_draw)

        # Layer 2: Neon Purple Radial Bloom Glow
        bloom_alpha = int(140 * eff_opacity * (1.0 + self.glow_flash))
        bloom_color = QColor(192, 132, 252, min(255, bloom_alpha))
        painter.setPen(bloom_color)
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            painter.drawText(draw_rect.translated(dx, dy), Qt.AlignmentFlag.AlignCenter, text_to_draw)

        # Layer 3: Vibrant Luminous Neon Purple Foreground
        flash_boost = int(55 * self.glow_flash)
        neon_r = min(255, 232 + flash_boost)
        neon_g = min(255, 121 + flash_boost)
        neon_b = 255
        neon_color = QColor(neon_r, neon_g, neon_b, int(255 * eff_opacity))
        painter.setPen(neon_color)
        painter.drawText(draw_rect, Qt.AlignmentFlag.AlignCenter, text_to_draw)

        painter.restore()

    def mousePressEvent(self, event):
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            self.is_dragging = True
            self.drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.is_dragging and (event.buttons() & (Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)):
            self.move(event.globalPosition().toPoint() - self.drag_start_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if self.is_dragging:
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
