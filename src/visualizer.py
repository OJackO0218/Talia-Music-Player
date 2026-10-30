"""
Cyberpunk Visualizer: Renders audio-reactive spectrum, waveforms, and reactor cores inside Talia's mouth.
"""

import os
import math
import numpy as np
from PyQt6.QtCore import Qt, QRect, QRectF, QPointF
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QRadialGradient, QPolygonF, QPixmap
)

from config import COLOR_THEMES, PNGS_DIR
from audio_engine import CyberAudioEngine


class CyberVisualizer:
    """Renders 4 distinct audio-reactive visualizer modes inside the mouth viewport."""

    def __init__(self):
        self.mode = "Cyber Bars"  # "Cyber Bars", "Neon Wave", "Radial Core", "Dual Mirror"
        self.current_theme_name = "Cyberpunk Neon"
        self.rotation_angle = 0.0
        self._cached_grid_pixmap = None
        self._cached_grid_key = None
        self.eco_mode = False
        self.music_note_icon = QPixmap()
        icon_path = os.path.join(PNGS_DIR, "music_note_white.png")
        if os.path.exists(icon_path):
            self.music_note_icon.load(icon_path)
        self._cached_scaled_note_size = -1
        self._cached_scaled_note = QPixmap()

    def set_eco_mode(self, enabled: bool):
        self.eco_mode = enabled

    def draw(self, painter: QPainter, rect: QRect, engine: CyberAudioEngine):
        """Draws the selected visualizer inside the target bounding rect."""
        painter.save()
        painter.setClipRect(rect)

        theme = COLOR_THEMES.get(self.current_theme_name, COLOR_THEMES["Cyberpunk Neon"])

        # Eco Mode: visualizer is removed; replaced with sleek black background and white music symbol
        if getattr(self, "eco_mode", False):
            self._draw_eco_mode(painter, rect, theme)
            painter.restore()
            return

        # 1 & 2. Hardware-accelerated Cached Background & Grid (single blit)
        key = (rect.width(), rect.height(), self.current_theme_name)
        if self._cached_grid_key != key or self._cached_grid_pixmap is None:
            self._cached_grid_key = key
            pm = QPixmap(rect.width(), rect.height())
            pm.fill(theme["bg"])
            p_grid = QPainter(pm)
            p_grid.setPen(QPen(theme["grid"], 1))
            step_x = 24
            step_y = 20
            for x in range(0, rect.width(), step_x):
                p_grid.drawLine(x, 0, x, rect.height())
            for y in range(0, rect.height(), step_y):
                p_grid.drawLine(0, y, rect.width(), y)
            p_grid.end()
            self._cached_grid_pixmap = pm

        painter.drawPixmap(rect.topLeft(), self._cached_grid_pixmap)

        # 3. Ambient Beat Glow Pulse (Lights up Talia's inner jaw on heavy bass)
        bars, peaks, beat = engine.update_spectrum()
        if beat > 0.15:
            cx = float(rect.center().x())
            cy = float(rect.center().y())
            radius = float(rect.width() * 0.45 * (1.0 + beat * 0.35))
            radial = QRadialGradient(cx, cy, radius)
            glow_col = QColor(theme["bar_mid"])
            glow_col.setAlpha(int(65 * beat))
            radial.setColorAt(0.0, glow_col)
            radial.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.fillRect(rect, QBrush(radial))

        # 4. Mode-specific Visualizer
        if self.mode == "Cyber Bars":
            self._draw_cyber_bars(painter, rect, bars, peaks, theme)
        elif self.mode == "Neon Wave":
            self._draw_neon_wave(painter, rect, engine, theme)
        elif self.mode == "Radial Core":
            self._draw_radial_core(painter, rect, bars, beat, theme)
        elif self.mode == "Dual Mirror":
            self._draw_dual_mirror(painter, rect, bars, peaks, theme)

        painter.restore()

    def _draw_eco_mode(self, painter: QPainter, rect: QRect, theme: dict):
        """Renders ultra-low CPU black background with crisp white music symbol and sleek cyber HUD accents."""
        # 1. Pitch black background inside mouth cavity
        painter.fillRect(rect, QColor(8, 8, 12, 255))

        cx = rect.center().x()
        cy = rect.center().y()
        icon_dim = max(16, int(min(rect.width(), rect.height()) * 0.52))

        # 2. Sleek Cyber HUD Corner Brackets
        bracket_pad = int(icon_dim * 0.16)
        bx1 = cx - icon_dim // 2 - bracket_pad
        bx2 = cx + icon_dim // 2 + bracket_pad
        by1 = cy - icon_dim // 2 - bracket_pad
        by2 = cy + icon_dim // 2 + bracket_pad
        blen = max(4, int(icon_dim * 0.20))

        bracket_color = theme.get("bar_bottom", QColor(0, 240, 255))
        bpen = QPen(QColor(bracket_color.red(), bracket_color.green(), bracket_color.blue(), 130), 1.5)
        painter.setPen(bpen)
        # Top-left
        painter.drawLine(bx1, by1, bx1 + blen, by1)
        painter.drawLine(bx1, by1, bx1, by1 + blen)
        # Top-right
        painter.drawLine(bx2, by1, bx2 - blen, by1)
        painter.drawLine(bx2, by1, bx2, by1 + blen)
        # Bottom-left
        painter.drawLine(bx1, by2, bx1 + blen, by2)
        painter.drawLine(bx1, by2, bx1, by2 - blen)
        # Bottom-right
        painter.drawLine(bx2, by2, bx2 - blen, by2)
        painter.drawLine(bx2, by2, bx2, by2 - blen)

        # 3. Soft ambient glow behind music note
        glow_rad = icon_dim * 0.85
        glow = QRadialGradient(float(cx), float(cy), float(glow_rad))
        glow.setColorAt(0.0, QColor(bracket_color.red(), bracket_color.green(), bracket_color.blue(), 45))
        glow.setColorAt(0.55, QColor(bracket_color.red(), bracket_color.green(), bracket_color.blue(), 12))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(glow)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(float(cx), float(cy)), glow_rad, glow_rad)

        # 4. White Music Note Icon
        if not self.music_note_icon.isNull():
            if self._cached_scaled_note_size != icon_dim:
                self._cached_scaled_note = self.music_note_icon.scaled(
                    icon_dim, icon_dim,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self._cached_scaled_note_size = icon_dim

            ix = cx - self._cached_scaled_note.width() // 2
            iy = cy - self._cached_scaled_note.height() // 2
            painter.drawPixmap(ix, iy, self._cached_scaled_note)

    def _draw_cyber_bars(self, painter: QPainter, rect: QRect, bars: np.ndarray, peaks: np.ndarray, theme: dict):
        """Segmented LED equalizer bars with falling peak hold caps."""
        if np.max(bars) < 0.002 and np.max(peaks) < 0.002:
            return  # Zero-cost early exit when silent
        num = len(bars)
        pad_x = max(2, int(rect.width() * 0.03))
        usable_w = rect.width() - (pad_x * 2)
        bar_w = max(1, int((usable_w / num) * 0.72))
        gap = max(1, int((usable_w - (bar_w * num)) / max(1, num - 1)))
        max_h = max(6, rect.height() - 16)
        base_y = rect.bottom() - 4

        num_segments = max(4, min(14, max_h // 4))
        seg_gap = 1 if max_h < 60 else 2

        for i in range(num):
            bx = rect.left() + pad_x + i * (bar_w + gap)
            val = float(bars[i])
            active_segs = int(val * num_segments)
            seg_h = max(2, (max_h // num_segments) - seg_gap)

            for s in range(num_segments):
                sy = base_y - (s + 1) * (seg_h + seg_gap)
                if s < active_segs:
                    # Color ramp based on segment height
                    ratio = s / float(num_segments)
                    if ratio < 0.5:
                        c1, c2 = theme["bar_bottom"], theme["bar_mid"]
                        r2 = ratio * 2.0
                        col = QColor(
                            int(c1.red() * (1 - r2) + c2.red() * r2),
                            int(c1.green() * (1 - r2) + c2.green() * r2),
                            int(c1.blue() * (1 - r2) + c2.blue() * r2),
                            235
                        )
                    else:
                        c1, c2 = theme["bar_mid"], theme["bar_top"]
                        t_ratio = (ratio - 0.5) * 2.0
                        col = QColor(
                            int(c1.red() * (1 - t_ratio) + c2.red() * t_ratio),
                            int(c1.green() * (1 - t_ratio) + c2.green() * t_ratio),
                            int(c1.blue() * (1 - t_ratio) + c2.blue() * t_ratio),
                            250
                        )
                    painter.fillRect(bx, sy, bar_w, seg_h, col)
                else:
                    # Inactive segment silhouette
                    painter.fillRect(bx, sy, bar_w, seg_h, QColor(255, 255, 255, 8))

            # Peak hold indicator
            peak_val = float(peaks[i])
            if peak_val > 0.05:
                py = base_y - int(peak_val * max_h) - 3
                painter.fillRect(bx, py, bar_w, 2, theme["peak"])

    def _draw_neon_wave(self, painter: QPainter, rect: QRect, engine: CyberAudioEngine, theme: dict):
        """Dual-layer glowing neon oscilloscope ECG waveform."""
        wave = engine.get_waveform(sample_count=80)
        pts_len = len(wave)
        if pts_len < 2:
            return

        cy = float(rect.center().y())
        if np.max(np.abs(wave)) < 0.002:
            # Silent guide line early return (zero-cost when paused)
            painter.setPen(QPen(QColor(theme["grid"].red(), theme["grid"].green(), theme["grid"].blue(), 45), 1, Qt.PenStyle.DashLine))
            painter.drawLine(rect.left(), int(cy), rect.right(), int(cy))
            return

        max_amp = float(rect.height() * 0.42)

        poly_glow = QPolygonF()
        poly_core = QPolygonF()

        dx = float(rect.width()) / float(pts_len - 1)
        for i in range(pts_len):
            x = float(rect.left()) + i * dx
            y = cy + float(wave[i]) * max_amp
            pt = QPointF(x, y)
            poly_glow.append(pt)
            poly_core.append(pt)

        # Center line guide
        painter.setPen(QPen(QColor(theme["grid"].red(), theme["grid"].green(), theme["grid"].blue(), 45), 1, Qt.PenStyle.DashLine))
        painter.drawLine(rect.left(), int(cy), rect.right(), int(cy))

        # Translucent glow envelope
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(theme["wave_glow"], 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPolyline(poly_glow)

        # Sharp bright core line
        painter.setPen(QPen(theme["wave"], 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPolyline(poly_core)

    def _draw_radial_core(self, painter: QPainter, rect: QRect, bars: np.ndarray, beat: float, theme: dict):
        """Spinning futuristic cyber targeting reticle and audio-reactive core."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cx = float(rect.center().x())
        cy = float(rect.center().y())
        base_r = float(min(rect.width(), rect.height())) * 0.28

        self.rotation_angle = (self.rotation_angle + 1.2) % 360.0

        # Pulsing center reactor core
        core_r = float(base_r * 0.5 * (1.0 + beat * 0.45))
        core_radial = QRadialGradient(cx, cy, core_r)
        core_radial.setColorAt(0.0, theme["bar_top"])
        core_radial.setColorAt(0.6, theme["bar_mid"])
        core_radial.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(core_radial))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(cx - core_r, cy - core_r, core_r * 2, core_r * 2))

        # Outer frequency radiating spikes
        num_spikes = min(32, len(bars))
        for i in range(num_spikes):
            angle = (i / float(num_spikes)) * 2 * math.pi + math.radians(self.rotation_angle)
            val = float(bars[i % len(bars)])
            r_inner = base_r * 0.75
            r_outer = r_inner + val * (base_r * 0.8)

            x1 = cx + math.cos(angle) * r_inner
            y1 = cy + math.sin(angle) * r_inner
            x2 = cx + math.cos(angle) * r_outer
            y2 = cy + math.sin(angle) * r_outer

            pen_col = theme["bar_bottom"] if (i % 2 == 0) else theme["bar_mid"]
            painter.setPen(QPen(pen_col, 2))
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # Outer tech bracket ring
        painter.setPen(QPen(theme["bar_bottom"], 1, Qt.PenStyle.DashLine))
        bracket_r = float(base_r * 1.35)
        painter.drawEllipse(QRectF(cx - bracket_r, cy - bracket_r, bracket_r * 2, bracket_r * 2))

    def _draw_dual_mirror(self, painter: QPainter, rect: QRect, bars: np.ndarray, peaks: np.ndarray, theme: dict):
        """Symmetrical dual-sided equalizer extending outward from the center."""
        cx = rect.center().x()
        # Center divider line (drawn in all states for HUD aesthetic)
        painter.setPen(QPen(theme["bar_top"], 1))
        painter.drawLine(cx, rect.top() + 8, cx, rect.bottom() - 8)

        if np.max(bars) < 0.002 and np.max(peaks) < 0.002:
            return

        base_y = rect.bottom() - 10
        max_h = rect.height() - 28
        half_bars = len(bars) // 2

        bar_w = max(2, int((rect.width() * 0.44) / half_bars))
        gap = 2

        for i in range(half_bars):
            val = float(bars[i * 2])
            h = int(val * max_h)
            col = theme["bar_mid"] if i < half_bars // 2 else theme["bar_bottom"]

            # Right side
            rx = cx + 8 + i * (bar_w + gap)
            painter.fillRect(rx, base_y - h, bar_w, h, col)

            # Left side (mirrored)
            lx = cx - 8 - (i + 1) * (bar_w + gap)
            painter.fillRect(lx, base_y - h, bar_w, h, col)
