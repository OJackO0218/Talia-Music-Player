"""
Reusable Qt widgets and layout helpers for Talia's interface.
Provides a unified Cyberpunk component library to eliminate inline styling boilerplate.
"""

import os
from typing import Callable, Optional

from PyQt6.QtCore import QPointF, QRect, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QCursor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from config import PNGS_DIR, PROJECT_ROOT

try:
    from PyQt6.QtSvg import QSvgRenderer
except ImportError:
    QSvgRenderer = None
from ui_theme import (
    BUTTON_VARIANTS,
    CARD_STYLE,
    COLOR_ACCENT_BLUE_BORDER,
    COLOR_BORDER_DEFAULT,
    COLOR_TEXT_PRIMARY,
)


def create_section_header(title: str) -> QWidget:
    """Creates a clean modern section header with a subtle divider line."""
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 2, 0, 6)
    layout.setSpacing(5)
    lbl = QLabel(title)
    lbl.setStyleSheet(
        "color: #f4f4f5; font-family: 'Segoe UI', Arial, sans-serif; font-weight: 600; "
        "font-size: 13px; background: transparent;"
    )
    layout.addWidget(lbl)
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Plain)
    line.setStyleSheet("border: none; border-top: 1px solid #2b2b35; max-height: 1px;")
    layout.addWidget(line)
    return container


class NoScrollComboBox(QComboBox):
    """Dropdown that ignores mouse wheel events to prevent accidental value changes while scrolling."""

    def wheelEvent(self, event):
        event.ignore()


class CyberButton(QPushButton):
    """
    Standard Cyberpunk styled button with variant support.
    Variants: 'default', 'primary', 'purple', 'cyan', 'success', 'danger'.
    """

    def __init__(
        self,
        text: str = "",
        variant: str = "default",
        on_click: Optional[Callable] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(text, parent)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.set_variant(variant)
        if on_click:
            self.clicked.connect(on_click)

    def set_variant(self, variant: str):
        style = BUTTON_VARIANTS.get(variant, BUTTON_VARIANTS["default"])
        self.setStyleSheet(style)


class CyberCard(QFrame):
    """
    Pre-styled container card with dark zinc background, subtle border, and optional header.
    Offers convenient .addWidget() and .addLayout() helpers.
    """

    def __init__(self, title: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("cyberCard")
        self.setStyleSheet(CARD_STYLE)
        self._root_layout = QVBoxLayout(self)
        self._root_layout.setContentsMargins(12, 10, 12, 12)
        self._root_layout.setSpacing(8)

        if title:
            self._header = create_section_header(title)
            self._root_layout.addWidget(self._header)

    @property
    def layout_content(self) -> QVBoxLayout:
        return self._root_layout

    def addWidget(self, widget: QWidget):
        self._root_layout.addWidget(widget)

    def addLayout(self, layout):
        self._root_layout.addLayout(layout)


class CyberSlider(QWidget):
    """
    Composite widget bundling a label, a live numeric readout, and a horizontal slider.
    Fires value_changed(int) and optional on_change callback.
    """

    valueChanged = pyqtSignal(int)

    def __init__(
        self,
        label: str,
        min_val: int,
        max_val: int,
        initial_val: int = 0,
        unit: str = "",
        on_change: Optional[Callable[[int], None]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.unit = unit
        self._callback = on_change

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 2, 0, 2)
        root.setSpacing(3)

        hbox = QHBoxLayout()
        self.lbl_title = QLabel(label)
        self.lbl_title.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-weight: 500;")
        hbox.addWidget(self.lbl_title)
        hbox.addStretch(1)

        self.lbl_val = QLabel(self._format_val(initial_val))
        self.lbl_val.setStyleSheet(f"color: {COLOR_ACCENT_BLUE_BORDER}; font-family: monospace; font-size: 11px;")
        hbox.addWidget(self.lbl_val)
        root.addLayout(hbox)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(min_val, max_val)
        self.slider.setValue(initial_val)
        self.slider.valueChanged.connect(self._on_slider_changed)
        root.addWidget(self.slider)

    def _format_val(self, val: int) -> str:
        return f"{val} {self.unit}".strip() if self.unit else str(val)

    def _on_slider_changed(self, val: int):
        self.lbl_val.setText(self._format_val(val))
        self.valueChanged.emit(val)
        if self._callback:
            try:
                self._callback(val)
            except Exception:
                pass

    def value(self) -> int:
        return self.slider.value()

    def setValue(self, val: int):
        self.slider.setValue(val)
        self.lbl_val.setText(self._format_val(val))

    def setRange(self, min_val: int, max_val: int):
        self.slider.setRange(min_val, max_val)


class CyberToggle(QCheckBox):
    """Pre-styled Cyberpunk checkbox/toggle with cursor and callback support."""

    def __init__(
        self,
        text: str,
        checked: bool = False,
        on_toggled: Optional[Callable[[bool], None]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(text, parent)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setChecked(checked)
        if on_toggled:
            self.toggled.connect(on_toggled)


class CyberLineEdit(QLineEdit):
    """Pre-styled text input with optional uppercase/monospace styling for codes & search."""

    def __init__(
        self,
        placeholder: str = "",
        text: str = "",
        monospace: bool = False,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(text, parent)
        if placeholder:
            self.setPlaceholderText(placeholder)
        if monospace:
            self.setStyleSheet(
                f"background-color: #202024; border: 1px solid {COLOR_BORDER_DEFAULT}; "
                "font-family: 'Consolas', monospace; font-size: 13px; font-weight: bold; padding: 6px 10px; border-radius: 4px;"
            )


class CyberScrollingTrackLabel(QWidget):
    """Track title marquee label in Rajdhani font."""

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

    def _get_active_screen_geom(self):
        screen = None
        if hasattr(self, "screen") and self.screen():
            screen = self.screen()
        elif hasattr(self, "parent") and self.parent() and hasattr(self.parent(), "screen") and self.parent().screen():
            screen = self.parent().screen()
        else:
            app = QApplication.instance()
            if app:
                screen = app.primaryScreen()
        return screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)

    def center_and_clamp_on_screen(self):
        screen = self._get_active_screen_geom()
        max_h = max(350, screen.height() - 70)
        if self.height() > max_h:
            self.resize(self.width(), max_h)
        cx = screen.left() + max(10, (screen.width() - self.width()) // 2)
        cy = screen.top() + max(35, (screen.height() - self.height()) // 2)
        self.move(cx, cy)

    def clamp_on_screen(self):
        screen = self._get_active_screen_geom()
        max_h = max(350, screen.height() - 70)
        if self.height() > max_h:
            self.resize(self.width(), max_h)
        pos = self.pos()
        clamped_y = max(screen.top() + 10, min(pos.y(), screen.bottom() - self.height() - 10))
        clamped_x = max(screen.left() + 10, min(pos.x(), screen.right() - self.width() - 10))
        self.move(clamped_x, clamped_y)

    def showEvent(self, event):
        super().showEvent(event)
        if getattr(self, "_custom_positioned", False):
            self.clamp_on_screen()
        else:
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
            screen = self._get_active_screen_geom()
            clamped_y = max(screen.top() + 10, min(new_pos.y(), screen.bottom() - self.height() - 10))
            clamped_x = max(screen.left() + 10, min(new_pos.x(), screen.right() - self.width() - 10))
            self.move(clamped_x, clamped_y)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


class DraggableHeaderWidget(QWidget):
    """Header bar that forwards drag events to its parent dialog."""

    def __init__(self, dialog: QWidget, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.dialog = dialog

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dialog._drag_pos = event.globalPosition().toPoint() - self.dialog.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if getattr(self.dialog, "_drag_pos", None) is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            new_pos = event.globalPosition().toPoint() - self.dialog._drag_pos
            screen = QApplication.primaryScreen().availableGeometry()
            clamped_y = max(screen.top() + 10, min(new_pos.y(), screen.bottom() - 60))
            clamped_x = max(screen.left() - self.dialog.width() + 60, min(new_pos.x(), screen.right() - 60))
            self.dialog.move(clamped_x, clamped_y)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.dialog._drag_pos = None
        super().mouseReleaseEvent(event)


class CyberChamferButton(QPushButton):
    """Polygonal button with chamfered bottom-right corner matching main menu action buttons.

    Icon variants:
      'exit', 'settings', 'new_playlist', 'delete_playlist', 'spotify', 'party'
    Text variants:
      'action_cyan', 'action_green', 'action_red', 'action_purple', 'action_neutral',
      'danger_accept', 'tab_cyan', 'tab_green', 'tab_purple', 'tab_idle'
    """

    # (normal_bg, normal_border, normal_text, hover_bg, hover_border, hover_text)
    _TEXT_VARIANTS: dict[str, tuple[tuple[int, ...], ...]] = {
        "action_cyan": (
            (12, 22, 36, 230), (94, 246, 255), (94, 246, 255),
            (0, 245, 255, 65), (255, 255, 255), (255, 255, 255),
        ),
        "action_green": (
            (7, 42, 26, 235), (32, 224, 112), (74, 222, 128),
            (16, 185, 129, 225), (110, 255, 180), (10, 14, 18),
        ),
        "action_red": (
            (40, 12, 18, 235), (247, 80, 73), (255, 138, 132),
            (247, 80, 73, 225), (255, 150, 145), (14, 14, 23),
        ),
        "action_purple": (
            (28, 18, 56, 235), (168, 85, 247), (216, 180, 254),
            (124, 58, 237, 235), (216, 180, 254), (255, 255, 255),
        ),
        "action_neutral": (
            (16, 17, 26, 235), (95, 95, 118), (228, 228, 236),
            (22, 32, 48, 240), (94, 246, 255), (255, 255, 255),
        ),
        "danger_accept": (
            (247, 80, 73), (247, 80, 73), (14, 14, 23),
            (255, 100, 95), (255, 120, 115), (10, 10, 20),
        ),
        "tab_cyan": (
            (16, 30, 48, 240), (94, 246, 255), (94, 246, 255),
            (20, 42, 66, 245), (94, 246, 255), (255, 255, 255),
        ),
        "tab_green": (
            (10, 38, 26, 240), (74, 222, 128), (74, 222, 128),
            (14, 52, 34, 245), (110, 255, 180), (255, 255, 255),
        ),
        "tab_purple": (
            (28, 18, 52, 240), (167, 139, 250), (196, 181, 253),
            (38, 24, 70, 245), (196, 181, 253), (255, 255, 255),
        ),
        "tab_idle": (
            (12, 12, 20, 210), (46, 46, 62), (130, 130, 150),
            (22, 22, 34, 230), (94, 246, 255), (244, 244, 245),
        ),
    }

    def __init__(self, text: str = "", variant: str = "exit", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.variant = variant
        self.chamfer_size = 6.0
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._is_hovered = False
        self._custom_tint: Optional[QColor] = None

    def set_variant(self, variant: str):
        """Updates button visual variant cleanly without recreating the widget."""
        self.variant = variant
        self._custom_tint = None
        self.update()

    def set_custom_tint(self, hex_color: str):
        """Applies a custom border & label highlight tint (e.g. chosen lyric swatch color)."""
        col = QColor(hex_color)
        self._custom_tint = col if col.isValid() else None
        self.update()

    def enterEvent(self, event):
        if self.isEnabled():
            self._is_hovered = True
            self.update()
            try:
                from cyber_sfx import get_cyber_sfx
                get_cyber_sfx().play_hover()
            except Exception:
                pass
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if self.isEnabled():
            try:
                from cyber_sfx import get_cyber_sfx
                get_cyber_sfx().play_click()
            except Exception:
                pass
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = float(self.width())
        h = float(self.height())
        c = min(self.chamfer_size, min(w, h) / 2.0)

        # Polygon path with bottom-right corner chamfered
        path = QPainterPath()
        path.moveTo(0, 0)
        path.lineTo(w, 0)
        path.lineTo(w, h - c)
        path.lineTo(w - c, h)
        path.lineTo(0, h)
        path.closeSubpath()

        # Determine colors based on variant & state
        bg_col = QColor(22, 22, 34)
        border_col = QColor(42, 42, 60)
        text_col = QColor(255, 255, 255)

        enabled = self.isEnabled()
        is_pressed = enabled and self.isDown()
        is_hover = enabled and self._is_hovered

        if not enabled and self.variant not in ("exit", "settings", "delete_playlist", "new_playlist", "spotify", "party"):
            bg_col = QColor(18, 18, 26, 200)
            border_col = QColor(52, 52, 68)
            text_col = QColor(95, 95, 115)
        elif self.variant in self._TEXT_VARIANTS:
            spec = self._TEXT_VARIANTS[self.variant]
            nb, nbr, nt, hb, hbr, ht = spec
            if is_hover or is_pressed:
                bg_col, border_col, text_col = QColor(*hb), QColor(*hbr), QColor(*ht)
            else:
                bg_col, border_col, text_col = QColor(*nb), QColor(*nbr), QColor(*nt)
            if self._custom_tint is not None and not is_hover and not is_pressed:
                border_col = QColor(self._custom_tint)
                text_col = QColor(self._custom_tint)
        elif self.variant == "exit":
            if is_hover or is_pressed:
                bg_col = QColor(0, 245, 255)
                border_col = QColor(0, 245, 255)
                text_col = QColor(10, 10, 20)
            else:
                bg_col = QColor(247, 80, 73, 0)
                border_col = QColor(255, 255, 255, 220)
                text_col = QColor(255, 255, 255)

        elif self.variant == "settings":
            if is_hover or is_pressed:
                bg_col = QColor(0, 245, 255)
                border_col = QColor(0, 245, 255)
                text_col = QColor(10, 10, 20)
            else:
                bg_col = QColor(247, 80, 73, 0)
                border_col = QColor(255, 255, 255, 220)
                text_col = QColor(255, 255, 255)

        elif self.variant == "new_playlist":
            if is_pressed:
                bg_col = QColor(32, 224, 112)
                border_col = QColor(32, 224, 112)
                text_col = QColor(255, 255, 255)
            elif is_hover:
                bg_col = QColor(0, 245, 255)
                border_col = QColor(0, 245, 255)
                text_col = QColor(255, 255, 255)
            else:
                bg_col = QColor(247, 80, 73)
                border_col = QColor(247, 80, 73)
                text_col = QColor(32, 224, 112)

        elif self.variant == "delete_playlist":
            if is_pressed:
                bg_col = QColor(255, 255, 0)
                border_col = QColor(255, 255, 0)
                text_col = QColor(20, 20, 20)
            elif is_hover:
                bg_col = QColor(0, 245, 255)
                border_col = QColor(0, 245, 255)
                text_col = QColor(20, 20, 20)
            else:
                bg_col = QColor(247, 80, 73)
                border_col = QColor(247, 80, 73)
                text_col = QColor(20, 20, 20)

        elif self.variant == "spotify":
            if is_hover or is_pressed:
                bg_col = QColor(0, 245, 255)
                border_col = QColor(0, 245, 255)
                text_col = QColor(10, 10, 20)
            else:
                bg_col = QColor(247, 80, 73, 0)
                border_col = QColor(255, 255, 255, 220)
                text_col = QColor(255, 255, 255)

        elif self.variant == "party":
            if is_hover or is_pressed:
                bg_col = QColor(0, 245, 255)
                border_col = QColor(0, 245, 255)
                text_col = QColor(10, 10, 20)
            else:
                bg_col = QColor(247, 80, 73, 0)
                border_col = QColor(255, 255, 255, 220)
                text_col = QColor(255, 255, 255)

        painter.setPen(QPen(border_col, 1.2))
        painter.setBrush(QBrush(bg_col))
        painter.drawPath(path)

        # Draw icon or text
        if self.variant in ("exit", "settings", "delete_playlist", "new_playlist", "spotify", "party"):
            self._paint_icon(painter, w, h, text_col)
            return

        # Rajdhani is bundled with Talia, so text metrics are consistent on
        # every machine. Shrink and elide rather than spilling outside the
        # chamfer at small fixed button sizes.
        font = QFont("Rajdhani")
        font.setWeight(QFont.Weight.DemiBold)
        size = max(8, int(round(h * 0.42)))
        font.setPixelSize(size)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.3)
        available = max(1.0, w - c - 6)
        metrics = QFontMetrics(font)
        while size > 7 and metrics.horizontalAdvance(self.text()) > available:
            size -= 1
            font.setPixelSize(size)
            metrics = QFontMetrics(font)
        label = metrics.elidedText(
            self.text(), Qt.TextElideMode.ElideRight, int(available)
        )
        painter.setPen(text_col)
        painter.setFont(font)
        painter.drawText(
            QRectF(0, 0, w - (c * 0.3), h), Qt.AlignmentFlag.AlignCenter, label
        )

    _icon_pixmap_cache: dict[str, QPixmap] = {}

    @classmethod
    def _get_cached_icon_pixmap(cls, filename: str) -> Optional[QPixmap]:
        if filename in cls._icon_pixmap_cache:
            return cls._icon_pixmap_cache[filename]
        cand_paths = (
            os.path.join(PROJECT_ROOT, "assets", "ui_cyber", filename),
            os.path.join(os.path.dirname(__file__), "..", "assets", "ui_cyber", filename),
        )
        pm: Optional[QPixmap] = None
        for path in cand_paths:
            if os.path.exists(path):
                loaded = QPixmap(path)
                if not loaded.isNull():
                    pm = loaded
                    break
        cls._icon_pixmap_cache[filename] = pm
        return pm

    def _paint_icon(self, painter: QPainter, w: float, h: float, color: QColor):
        """Draws crisp vector icons so we never depend on symbol fonts."""
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(
            QPen(
                color,
                max(1.4, min(w, h) * 0.075),
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )

        if self.variant == "settings":
            gear_pm = self._get_cached_icon_pixmap("settings_gear.png")
            if gear_pm is not None:
                gw, gh = min(w, h) * 0.76, min(w, h) * 0.76
                gx, gy = (w - gw) / 2.0, (h - gh) / 2.0
                painter.drawPixmap(QRectF(gx, gy, gw, gh), gear_pm, QRectF(gear_pm.rect()))
                return
            # Fallback gear teeth if image missing
            pad = min(w, h) * 0.24
            knob_r = max(1.4, min(w, h) * 0.055)
            for row, knob_pos in enumerate((0.38, 0.64, 0.46)):
                y = h * (0.30 + row * 0.20)
                painter.drawLine(QPointF(pad, y), QPointF(w - pad, y))
                painter.setBrush(QBrush(color))
                painter.drawEllipse(QPointF(w * knob_pos, y), knob_r, knob_r)
                painter.setBrush(Qt.BrushStyle.NoBrush)
            return

        if self.variant == "new_playlist":
            pad = min(w, h) * 0.22
            pen = QPen(color, max(2.6, min(w, h) * 0.12), Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap)
            painter.setPen(pen)
            mid_x, mid_y = w / 2.0, h / 2.0
            painter.drawLine(QPointF(pad, mid_y), QPointF(w - pad, mid_y))
            painter.drawLine(QPointF(mid_x, pad), QPointF(mid_x, h - pad))
            return

        if self.variant == "spotify":
            spot_pm = self._get_cached_icon_pixmap("spotify_logo.png")
            if spot_pm is not None:
                pw, ph = min(w, h) * 0.72, min(w, h) * 0.72
                px, py = (w - pw) / 2.0, (h - ph) / 2.0
                painter.drawPixmap(QRectF(px, py, pw, ph), spot_pm, QRectF(spot_pm.rect()))
                return
            painter.setBrush(QBrush(QColor(30, 215, 96)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(w / 2.0, h / 2.0), min(w, h) * 0.35, min(w, h) * 0.35)
            return

        if self.variant == "party":
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            # Left user
            l_head_r = min(w, h) * 0.12
            l_hx = w * 0.38
            l_hy = h * 0.35
            painter.drawEllipse(QPointF(l_hx, l_hy), l_head_r, l_head_r)
            l_torso = QPainterPath()
            l_torso.moveTo(l_hx - min(w, h) * 0.20, h * 0.76)
            l_torso.quadTo(l_hx, h * 0.48, l_hx + min(w, h) * 0.20, h * 0.76)
            l_torso.closeSubpath()
            painter.drawPath(l_torso)
            # Right user
            r_head_r = min(w, h) * 0.11
            r_hx = w * 0.65
            r_hy = h * 0.38
            painter.drawEllipse(QPointF(r_hx, r_hy), r_head_r, r_head_r)
            r_torso = QPainterPath()
            r_torso.moveTo(r_hx - min(w, h) * 0.18, h * 0.76)
            r_torso.quadTo(r_hx, h * 0.52, r_hx + min(w, h) * 0.18, h * 0.76)
            r_torso.closeSubpath()
            painter.drawPath(r_torso)
            return

        # 'exit' and 'delete_playlist': an X.
        m = min(w, h) * 0.30
        painter.drawLine(QPointF(m, m), QPointF(w - m, h - m))
        painter.drawLine(QPointF(w - m, m), QPointF(m, h - m))


class CyberVerticalVolumeSlider(QWidget):
    """Vertical volume slider flank matching Figma Demo frame.

    - Rotated vertical text 'MASTER VOLUME'.
    - Vertical red rail spanning 100% of the flank from top edge to bottom edge.
    - Horizontal sliding red pip handle with soft glow.
    - Syncs smoothly with mouse drag, click, and mouse wheel with Cyberpunk SFX.
    """

    valueChanged = pyqtSignal(int)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedWidth(28)
        self.setMinimumHeight(140)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._value = 50  # 0 to 100
        self._is_dragging = False

    def orientation(self) -> Qt.Orientation:
        return Qt.Orientation.Vertical

    def setRange(self, min_val: int, max_val: int):
        pass

    def value(self) -> int:
        return self._value

    def setValue(self, val: int):
        val = max(0, min(100, int(val)))
        if val != self._value:
            old_val = self._value
            self._value = val
            self.update()
            self.valueChanged.emit(val)
            try:
                from cyber_sfx import get_cyber_sfx
                get_cyber_sfx().play_value(val > old_val)
            except Exception:
                pass

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._update_from_y(event.position().y())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_dragging and (event.buttons() & Qt.MouseButton.LeftButton):
            self._update_from_y(event.position().y())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        step = 4 if delta > 0 else -4
        self.setValue(self._value + step)
        event.accept()

    def _update_from_y(self, y_pos: float):
        h = max(1.0, float(self.height()))
        norm = (h - y_pos) / h
        val = int(round(max(0.0, min(1.0, norm)) * 100))
        self.setValue(val)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = float(self.width())
        h = float(self.height())

        # 1. Rotated vertical text 'MASTER VOLUME' matching Figma
        painter.save()
        painter.translate(9.0, h - 22.0)
        painter.rotate(-90.0)
        font = QFont("Rajdhani", 8, QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
        painter.setFont(font)
        painter.setPen(QColor(176, 200, 201, 230))
        painter.drawText(0, 0, "MASTER VOLUME")
        painter.restore()

        # 2. Rail geometry reaching 100% of flank (y=0 to y=h)
        rail_x = 21.0
        track_h = h

        # Subtle tick marks at 0%, 25%, 50%, 75%, 100%
        painter.setPen(QPen(QColor(255, 138, 132, 160), 1.0))
        for tick_pct in (0.0, 0.25, 0.50, 0.75, 1.0):
            ty = h - (tick_pct * track_h)
            painter.drawLine(QPointF(rail_x - 4.0, ty), QPointF(rail_x - 1.0, ty))

        # Full red track line from very top (0.0) to very bottom (h)
        painter.setPen(QPen(QColor(247, 80, 73, 110), 1.5))
        painter.drawLine(QPointF(rail_x, 0.0), QPointF(rail_x, h))

        # Pip / Handle: horizontal coral bar with soft halo matching Figma
        pip_w = 16.0
        pip_h = 5.0
        raw_handle_y = h - (float(self._value) / 100.0 * track_h)
        handle_y = max(pip_h / 2.0, min(h - pip_h / 2.0, raw_handle_y))

        # Active rail (bottom to handle) in bright red reaching all the way to bottom
        painter.setPen(QPen(QColor(247, 80, 73, 255), 2.0))
        painter.drawLine(QPointF(rail_x, handle_y), QPointF(rail_x, h))

        # Soft outer glow
        painter.setBrush(QBrush(QColor(247, 80, 73, 70)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(QRectF(rail_x - (pip_w / 2.0) - 3.0, handle_y - (pip_h / 2.0) - 3.0, pip_w + 6.0, pip_h + 6.0))

        # Solid handle bar
        pip_rect = QRectF(rail_x - (pip_w / 2.0), handle_y - (pip_h / 2.0), pip_w, pip_h)
        painter.setBrush(QBrush(QColor(255, 138, 132)))
        painter.setPen(QPen(QColor(255, 255, 255, 220), 0.8))
        painter.drawRect(pip_rect)


class CyberDeletePlaylistDialog(QDialog, DraggableClampedDialogMixin):
    """Custom cyberpunk modal dialog for deleting custom playlists matching Figma component."""

    def __init__(self, playlist_name: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(310, 160)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 14)
        layout.setSpacing(10)

        # Title: Warning icon + DELETE PLAYLIST?
        lbl_title = QLabel("▲ DELETE PLAYLIST?")
        lbl_title.setStyleSheet("color: #F75049; font-weight: 800; font-size: 13px; letter-spacing: 1.5px;")
        layout.addWidget(lbl_title)

        # Body message
        lbl_body = QLabel(
            f"Are you sure you want to delete the playlist '{playlist_name}'?\n(Original songs will remain safe in your library)"
        )
        lbl_body.setWordWrap(True)
        lbl_body.setStyleSheet("color: #a1a1aa; font-size: 10px; line-height: 1.3;")
        layout.addWidget(lbl_body, 1)

        # Buttons row: DECLINE & ACCEPT >
        hbox_btns = QHBoxLayout()
        hbox_btns.setSpacing(12)
        hbox_btns.addStretch()

        self.btn_decline = QPushButton("DECLINE")
        self.btn_decline.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_decline.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #F75049;
                font-weight: bold;
                font-size: 10px;
                letter-spacing: 1px;
                border: none;
                padding: 6px 12px;
            }
            QPushButton:hover {
                color: #ff8888;
            }
        """)
        self.btn_decline.clicked.connect(self.reject)
        hbox_btns.addWidget(self.btn_decline)

        self.btn_accept = CyberChamferButton("ACCEPT >", variant="danger_accept")
        self.btn_accept.setFixedSize(92, 28)
        self.btn_accept.clicked.connect(self.accept)
        hbox_btns.addWidget(self.btn_accept)

        layout.addLayout(hbox_btns)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = float(self.width())
        h = float(self.height())
        c = 8.0

        path = QPainterPath()
        path.moveTo(c, 0)
        path.lineTo(w - c, 0)
        path.lineTo(w, c)
        path.lineTo(w, h - c)
        path.lineTo(w - c, h)
        path.lineTo(c, h)
        path.lineTo(0, h - c)
        path.lineTo(0, c)
        path.closeSubpath()

        painter.fillPath(path, QBrush(QColor(14, 14, 23, 248)))
        painter.setPen(QPen(QColor(247, 80, 73, 220), 1.5))
        painter.drawPath(path)


class CyberCardContainer(QFrame):
    """
    Cyberpunk UI Container Frame matching Figma Node 2215:411 and simple menu panel.
    - Neutral/Dark background #0E0E17 with authentic subtle HUD grid texture.
    - Outer cyber border with chamfered corners in Primary Red #F75049.
    - Top geometric chamfered banner that hugs the chassis body (header_banner_hug.png).
    - Left telemetry rail ruler markings from Forms/Web.Razor.svg (#FCEE0A yellow).
    - Bottom left red hex geometry badge from Forms/geometry5.svg.
    - Bottom right Protocol 6520-A44 badge from protocol_badge.png.
    """

    _shared_assets_loaded: bool = False
    _shared_protocol_scaled: Optional[QPixmap] = None
    _shared_bg_pixmap: Optional[QPixmap] = None
    _shared_banner_pixmap: Optional[QPixmap] = None

    @classmethod
    def _ensure_shared_assets(cls):
        if cls._shared_assets_loaded:
            return
        cls._shared_assets_loaded = True
        assets_dir = os.path.join(PROJECT_ROOT, "assets", "ui_cyber")

        proto_p = os.path.join(assets_dir, "protocol_badge.png")
        if os.path.exists(proto_p):
            raw_proto = QPixmap(proto_p)
            if not raw_proto.isNull():
                cls._shared_protocol_scaled = raw_proto.scaled(
                    32, 26, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )

        bg_p = os.path.join(assets_dir, "panel_background_texture.png")
        if not os.path.exists(bg_p):
            bg_p = os.path.join(assets_dir, "bg_texture.png")
        if os.path.exists(bg_p):
            bg_pm = QPixmap(bg_p)
            if not bg_pm.isNull():
                cls._shared_bg_pixmap = bg_pm

        hug_p = os.path.join(assets_dir, "header_banner_hug.png")
        if os.path.exists(hug_p):
            hug_pm = QPixmap(hug_p)
            if not hug_pm.isNull():
                cls._shared_banner_pixmap = hug_pm

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("slidePanelCard")
        self._ensure_shared_assets()
        self.protocol_pixmap = self._shared_protocol_scaled
        self.bg_pixmap = self._shared_bg_pixmap
        self.banner_pixmap = self._shared_banner_pixmap

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w = float(self.width())
        h = float(self.height())

        header_h = 42.0
        inset_x = 10.0
        body_top_y = 36.0
        body_w = w - (2.0 * inset_x)
        body_h = h - body_top_y - 2.0

        # 1. Chassis Body Dark base #0E0E17
        painter.fillRect(QRectF(inset_x, body_top_y, body_w, body_h), QColor(14, 14, 23))

        # 2. Authentic Figma Panel Background Texture inside chassis body
        if self.bg_pixmap and not self.bg_pixmap.isNull():
            painter.drawPixmap(
                QRectF(inset_x, body_top_y, body_w, body_h),
                self.bg_pixmap,
                QRectF(self.bg_pixmap.rect()),
            )

        # 3. Outer Chamfered Cyber Border (#F75049) on Chassis Body
        pen = QPen(QColor(247, 80, 73, 220), 1.5)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        c = 8.0
        body_path = QPainterPath()
        body_path.moveTo(inset_x, body_top_y)
        body_path.lineTo(inset_x + body_w, body_top_y)
        body_path.lineTo(inset_x + body_w, body_top_y + body_h - c)
        body_path.lineTo(inset_x + body_w - c, body_top_y + body_h)
        body_path.lineTo(inset_x + c, body_top_y + body_h)
        body_path.lineTo(inset_x, body_top_y + body_h - c)
        body_path.closeSubpath()
        painter.drawPath(body_path)

        # 4. Right edge mechanical red ribbed slats on Chassis Body matching Figma
        painter.setPen(QPen(QColor(247, 80, 73, 190), 1.2))
        for ty in range(int(body_top_y) + 12, int(h) - 28, 6):
            painter.drawLine(
                QPointF(inset_x + body_w - 6.0, float(ty)),
                QPointF(inset_x + body_w - 2.0, float(ty)),
            )

        # 5. Bottom Right: protocol_badge.png (PROTOCOL 6520-A44) matching Figma
        if self.protocol_pixmap and not self.protocol_pixmap.isNull():
            pw, ph = 32, 26
            px, py = inset_x + body_w - pw - 12, h - ph - 6
            painter.drawPixmap(int(px), int(py), self.protocol_pixmap)

        # 6. Top Header Banner that HUGS the Chassis Body:
        if self.banner_pixmap and not self.banner_pixmap.isNull():
            painter.drawPixmap(
                QRectF(0, 0, w, header_h),
                self.banner_pixmap,
                QRectF(self.banner_pixmap.rect()),
            )
        else:
            header_chamfer = 14.0
            h_path = QPainterPath()
            h_path.moveTo(header_chamfer, 0)
            h_path.lineTo(w, 0)
            h_path.lineTo(w, header_h)
            h_path.lineTo(w - inset_x, header_h)
            h_path.lineTo(w - inset_x, body_top_y)
            h_path.lineTo(inset_x, body_top_y)
            h_path.lineTo(inset_x, header_h)
            h_path.lineTo(0, header_h)
            h_path.lineTo(0, header_chamfer)
            h_path.closeSubpath()
            painter.fillPath(h_path, QColor(247, 80, 73))

        super().paintEvent(event)

