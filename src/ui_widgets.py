"""Reusable Qt widgets and layout helpers for Talia's interface."""

import os

from PyQt6.QtCore import QPointF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from config import PNGS_DIR


def create_section_header(title: str) -> QWidget:
    """Creates a clean, minimal section header with a subtle separator."""
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 10, 0, 4)
    layout.setSpacing(4)
    lbl = QLabel(title)
    lbl.setStyleSheet("color: #a1a1aa; font-weight: 600; font-size: 11px;")
    layout.addWidget(lbl)
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Plain)
    line.setStyleSheet("border: none; border-top: 1px solid #27272a; max-height: 1px;")
    layout.addWidget(line)
    return container


class NoScrollComboBox(QComboBox):
    """Dropdown that ignores mouse wheel events to prevent accidental value changes while scrolling."""

    def wheelEvent(self, event):
        event.ignore()


class CyberScrollingTrackLabel(QWidget):
    # Track title marquee label in Rajdhani font

    def __init__(self, parent=None):
        super().__init__(parent)
        self.full_text = "No track loaded"
        self.scroll_x = 0.0
        self.scroll_speed = 36.0
        self.is_scrolling = False
        self.symbol_mode = None
        self.symbol_timer = 0.0

        # Load skip symbols
        self.icon_forward = QPixmap(os.path.join(PNGS_DIR, "icon_forward.png"))
        self.icon_backward = QPixmap(os.path.join(PNGS_DIR, "icon_backward.png"))
        self.setFixedHeight(26)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)
        self.timer.setInterval(33)
        self.font = QFont("Rajdhani", 12, QFont.Weight.Bold)
        self.font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.5)

    def text(self) -> str:
        return self.full_text

    def setText(self, text: str):
        cleaned = text.strip() if text else "No track loaded"
        if cleaned != self.full_text:
            self.full_text = cleaned
            self.scroll_x = 0.0
            self._check_scroll_needed()
            self.update()

    def trigger_symbol(self, direction: str):
        # Display forward/backward symbol for 2.2 seconds
        self.symbol_mode = direction
        self.symbol_timer = 2.2
        if not self.timer.isActive() and self.isVisible():
            self.timer.start(33)
        self.update()

    def _check_scroll_needed(self):
        if self.full_text != "No track loaded" and self.isVisible():
            self.is_scrolling = True
            if not self.timer.isActive():
                self.timer.start(33)
        else:
            self.is_scrolling = False
            self.scroll_x = 0.0
            if self.symbol_timer <= 0.0:
                self.timer.stop()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._check_scroll_needed()

    def showEvent(self, event):
        super().showEvent(event)
        self._check_scroll_needed()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.timer.stop()

    def _on_tick(self):
        dt = 0.033
        needs_update = False
        if self.symbol_timer > 0.0:
            self.symbol_timer -= dt
            if self.symbol_timer <= 0.0:
                self.symbol_mode = None
                self.symbol_timer = 0.0
            needs_update = True
        if self.is_scrolling and self.full_text != "No track loaded":
            self.scroll_x += self.scroll_speed * dt
            needs_update = True
        elif self.symbol_timer <= 0.0:
            self.timer.stop()
        if needs_update:
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        metrics = QFontMetrics(self.font)
        baseline = (self.height() + metrics.ascent() - metrics.descent()) / 2.0
        x_start = 2
        if self.symbol_mode:
            icon = self.icon_forward if self.symbol_mode == "forward" else self.icon_backward
            if not icon.isNull():
                icon_h = min(16, self.height() - 6)
                icon_w = int(icon.width() * (icon_h / float(icon.height())))
                iy = int((self.height() - icon_h) / 2.0)
                painter.drawPixmap(x_start, iy, icon_w, icon_h, icon)
                x_start += icon_w + 8
        painter.setFont(self.font)
        painter.setPen(QColor("#f4f4f5"))
        avail_w = max(10, self.width() - x_start)
        painter.setClipRect(x_start, 0, avail_w, self.height())
        text_w = metrics.horizontalAdvance(self.full_text)
        if self.is_scrolling and self.full_text != "No track loaded":
            gap = 48
            span = text_w + gap
            curr_x = x_start - (self.scroll_x % span)
            painter.drawText(QPointF(curr_x, baseline), self.full_text)
            painter.drawText(QPointF(curr_x + span, baseline), self.full_text)
        else:
            painter.drawText(QPointF(x_start, baseline), self.full_text)


class DraggableClampedDialogMixin:
    """Provides screen-safe centering, height-clamping, and background drag support."""

    def center_and_clamp_on_screen(self):
        screen = QApplication.primaryScreen().availableGeometry()
        max_h = max(350, screen.height() - 70)
        if self.height() > max_h:
            self.resize(self.width(), max_h)
        cx = screen.left() + max(10, (screen.width() - self.width()) // 2)
        cy = screen.top() + max(35, (screen.height() - self.height()) // 2)
        self.move(cx, cy)

    def showEvent(self, event):
        super().showEvent(event)
        self.center_and_clamp_on_screen()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if getattr(self, "_drag_pos", None) is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            screen = QApplication.primaryScreen().availableGeometry()
            clamped_y = max(screen.top() + 10, min(new_pos.y(), screen.bottom() - 60))
            clamped_x = max(screen.left() - self.width() + 60, min(new_pos.x(), screen.right() - 60))
            self.move(clamped_x, clamped_y)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)
