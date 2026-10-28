"""
Transparent Live2D-rigged character overlay with 60 FPS eye-tracking and mouth visualizer.
"""

import os
import math
import time
import cv2
import numpy as np
from PIL import Image, ImageOps

from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QPoint, QPointF, QTimer, QRect, QRectF, QUrl
from PyQt6.QtGui import (
    QPixmap, QPainter, QColor, QPen, QImage, QCursor, QRadialGradient
)
from PyQt6.QtMultimedia import QSoundEffect

from config import (
    EYE_PARTS_DIR, SOUNDS_DIR, PNGS_DIR, CANVAS_BASE_SIZE, MOUTH_BOX_X, MOUTH_BOX_Y,
    MOUTH_BOX_W, MOUTH_BOX_H, DEFAULT_ORIGIN_LX, DEFAULT_ORIGIN_LY,
    DEFAULT_ORIGIN_RX, DEFAULT_ORIGIN_RY, MIN_CHAR_SIZE, MAX_CHAR_SIZE,
    user32, HWND_TOPMOST, SWP_NOMOVE, SWP_NOSIZE, SWP_NOACTIVATE, SWP_SHOWWINDOW
)
from audio_engine import CyberAudioEngine
from visualizer import CyberVisualizer


def cv2_to_qpixmap(cv_img: np.ndarray) -> QPixmap:
    """Converts OpenCV BGRA numpy array to QPixmap."""
    if cv_img is None:
        return QPixmap()
    h, w = cv_img.shape[:2]
    if len(cv_img.shape) == 2:
        qimg = QImage(cv_img.data, w, h, w, QImage.Format.Format_Grayscale8)
    elif cv_img.shape[2] == 4:
        rgba = cv2.cvtColor(cv_img, cv2.COLOR_BGRA2RGBA)
        qimg = QImage(rgba.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
    else:
        rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg.copy())


class OverlayWindow(QWidget):
    """Transparent desktop overlay featuring Talia with interactive eye tracking and music visualizer."""

    def __init__(self, audio_engine: CyberAudioEngine):
        super().__init__(None)
        self.audio_engine = audio_engine
        self.visualizer = CyberVisualizer()
        self.panel = None  # Reference to ControlPanel for UI synchronization

        # Display and Mode settings
        self.move_talia_mode = False  # False = Locked & Clickable, True = Movable/Resizable
        self.opacity_val = 1.0
        self.enable_scanlines = True
        self.enable_bass_pop = True
        self.bass_pop_scale = 1.0
        self.use_widescreen = False
        self.enable_eye_tracking = True
        self.eye_sensitivity = 1.0

        # Eye tracking coordinates & lerp state
        self.current_offset_lx = 0.0
        self.current_offset_ly = 0.0
        self.target_offset_lx = 0.0
        self.target_offset_ly = 0.0

        self.current_offset_rx = 0.0
        self.current_offset_ry = 0.0
        self.target_offset_rx = 0.0
        self.target_offset_ry = 0.0

        # Mouse interaction, 1/2/3 multi-click, and 4s hold-to-shutdown state
        self.drag_position = QPoint()
        self.press_pos = QPoint()
        self.is_dragging = False

        self.click_count = 0
        self.multi_click_timer = QTimer(self)
        self.multi_click_timer.setSingleShot(True)
        self.multi_click_timer.setInterval(340)  # 20% increase from 280ms for comfortable pacing
        self.multi_click_timer.timeout.connect(self._on_multi_click_timeout)

        # 4-Second Hold Power-Down State
        self.press_time = 0.0
        self.is_holding = False
        self.hold_saturation = 1.0  # 1.0 = full color, drops to 0.0 between 2s and 4s hold
        self.hold_timer = QTimer(self)
        self.hold_timer.setInterval(25)
        self.hold_timer.timeout.connect(self._on_hold_tick)

        self.restore_timer = QTimer(self)
        self.restore_timer.setInterval(20)
        self.restore_timer.timeout.connect(self._on_restore_tick)

        # Volume & Eye-Saturation Indicator State
        self.current_volume = getattr(self.audio_engine, "volume", 0.85)
        self.raw_pupil_l_cv = None
        self.raw_pupil_r_cv = None
        self._last_scaled_volume = -1.0

        # Feedback Satisfaction: Hover, Hold Rumbler, Tactile Button Punch, and Color Flashes
        self.is_hovered = False
        self.was_hovered = False
        self.hover_glow = 0.0  # Smooth 0.0 to ~0.20 luminous highlight (osu! lazer style)
        self.hover_scale = 1.0  # Subtle 1.0 to 1.012 breathing scale

        # Dynamic Rotation & Sway State (osu! lazer left-right rocking & tilt)
        self.current_rotation = 0.0  # In degrees, applied via painter.rotate()
        self.current_shake_x = 0.0
        self.current_shake_y = 0.0
        self.impulse_rock_intensity = 0.0
        self.impulse_sway_intensity = 0.0
        self.impulse_timer = 0.0

        # Tactile Button Press punch (at 1.0s drag hold mark)
        self.button_press_scale = 1.0
        self.button_press_delay = 0.0  # Bottom-out delay before delayed spring back
        self.drag_ready_triggered = False

        # Click Color Flashes (1x White, 2x Red, 3x Yellow) with 0.24s solid hold
        self.flash_color = QColor(255, 255, 255)
        self.flash_alpha = 0.0
        self.flash_hold_timer = 0.0  # Holds peak color for 0.24s before smooth fade-out

        # Sinking Shutdown State (3.0s to 3.6s)
        self.is_shutting_down = False
        self.shutdown_start_time = 0.0
        self.shutdown_start_pos = QPoint(0, 0)

        # Snappy Rise-Up Startup Entrance State (<= 0.20s max)
        self.is_starting_up = False
        self.startup_start_time = 0.0
        self.target_startup_x = 0
        self.target_startup_y = 0
        self.startup_offset_y = 110
        self.startup_duration = 0.20

        # Tactile Sound Effects (Hover Pop, Click Button, Hold Ramp-up with Bubbles, Heavy Sinking Shutdown)
        # All SFX turned down by a further 25% for balanced comfortable audio
        self.sound_pop = QSoundEffect(self)
        pop_path = os.path.join(SOUNDS_DIR, "hover_pop.wav")
        if os.path.exists(pop_path):
            self.sound_pop.setSource(QUrl.fromLocalFile(pop_path))
            self.sound_pop.setVolume(0.42)

        self.sound_btn = QSoundEffect(self)
        btn_path = os.path.join(SOUNDS_DIR, "click_button.wav")
        if os.path.exists(btn_path):
            self.sound_btn.setSource(QUrl.fromLocalFile(btn_path))
            self.sound_btn.setVolume(0.36)

        self.sound_hold = QSoundEffect(self)
        hold_path = os.path.join(SOUNDS_DIR, "hold_ramp.wav")
        if os.path.exists(hold_path):
            self.sound_hold.setSource(QUrl.fromLocalFile(hold_path))
            self.sound_hold.setVolume(0.36)

        self.sound_shutdown = QSoundEffect(self)
        shutdown_path = os.path.join(SOUNDS_DIR, "shutdown_heavy.wav")
        if os.path.exists(shutdown_path):
            self.sound_shutdown.setSource(QUrl.fromLocalFile(shutdown_path))
            self.sound_shutdown.setVolume(0.45)

        # Cyber Mute Indicator (Displays when music is paused)
        self.mute_icon = QPixmap()
        mute_path = os.path.join(PNGS_DIR, "mute_icon.png")
        if os.path.exists(mute_path):
            self.mute_icon.load(mute_path)
        self.mute_alpha = 0.0
        self._cached_scaled_mute_size = -1
        self._cached_scaled_mute = QPixmap()

        # Caching optimization: store pre-scaled pixmaps to avoid re-scaling on every 16ms frame
        self._last_scaled_size = -1
        self._cached_scaled_talia = QPixmap()
        self._cached_scaled_talia_gray = QPixmap()
        self._cached_scaled_whites = QPixmap()
        self._cached_scaled_pupil_l = QPixmap()
        self._cached_scaled_pupil_r = QPixmap()

        self.setMouseTracking(True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Window
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self.load_assets()
        self.init_position()

        # Continuous topmost enforcement (100ms)
        self.topmost_timer = QTimer(self)
        self.topmost_timer.timeout.connect(self.enforce_topmost)
        self.topmost_timer.start(100)

        # 60 FPS Animation & Eye-tracking loop (16ms)
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.on_anim_tick)
        self.anim_timer.start(16)

    def load_assets(self):
        """Loads and auto-slices the 3-layer eye rig from PNG files."""
        print(f"[ASSET LOADER] Reading art from: {EYE_PARTS_DIR}")
        p1_path = os.path.join(EYE_PARTS_DIR, "part1_pupils_full.png")
        p2_path = os.path.join(EYE_PARTS_DIR, "part2_eye_whites_full.png")
        p3_path = os.path.join(EYE_PARTS_DIR, "part3_talia_main_sprite.png")

        # Layer 1: Talia Main Sprite (Front)
        self.talia_sprite = QPixmap(p3_path)

        # Grayscale version of Talia Sprite for 4s power-down shutdown effect
        talia_pil = Image.open(p3_path).convert("RGBA")
        r, g, b, a = talia_pil.split()
        gray_rgb = ImageOps.grayscale(talia_pil.convert("RGB"))
        gray_rgba = Image.merge("RGBA", (gray_rgb, gray_rgb, gray_rgb, a))
        gray_np = np.array(gray_rgba)
        qimg_gray = QImage(gray_np.data, 591, 591, 591 * 4, QImage.Format.Format_RGBA8888)
        self.talia_sprite_gray = QPixmap.fromImage(qimg_gray.copy())

        # Layer 3: Eye Whites (Back)
        self.whites = QPixmap(p2_path)

        # Layer 2: Moving Pupils - Auto-slice left and right pupils from part1_pupils_full.png
        p1_cv = cv2.imread(p1_path, cv2.IMREAD_UNCHANGED)
        if p1_cv is not None and p1_cv.shape[2] == 4:
            # Left pupil (x < 300)
            p1_l = p1_cv.copy()
            p1_l[:, 300:, 3] = 0
            coords_l = np.column_stack(np.where(p1_l[:, :, 3] > 0))
            if len(coords_l):
                yl_min, xl_min = coords_l[:, 0].min(), coords_l[:, 1].min()
                yl_max, xl_max = coords_l[:, 0].max(), coords_l[:, 1].max()
                self.origin_lx = int(xl_min)
                self.origin_ly = int(yl_min)
                self.raw_pupil_l_cv = p1_cv[yl_min:yl_max+1, xl_min:xl_max+1].copy()
            else:
                self.origin_lx, self.origin_ly = DEFAULT_ORIGIN_LX, DEFAULT_ORIGIN_LY
                self.raw_pupil_l_cv = None

            # Right pupil (x >= 300)
            p1_r = p1_cv.copy()
            p1_r[:, :300, 3] = 0
            coords_r = np.column_stack(np.where(p1_r[:, :, 3] > 0))
            if len(coords_r):
                yr_min, xr_min = coords_r[:, 0].min(), coords_r[:, 1].min()
                yr_max, xr_max = coords_r[:, 0].max(), coords_r[:, 1].max()
                self.origin_rx = int(xr_min)
                self.origin_ry = int(yr_min)
                self.raw_pupil_r_cv = p1_cv[yr_min:yr_max+1, xr_min:xr_max+1].copy()
            else:
                self.origin_rx, self.origin_ry = DEFAULT_ORIGIN_RX, DEFAULT_ORIGIN_RY
                self.raw_pupil_r_cv = None
        else:
            self.origin_lx, self.origin_ly = DEFAULT_ORIGIN_LX, DEFAULT_ORIGIN_LY
            self.origin_rx, self.origin_ry = DEFAULT_ORIGIN_RX, DEFAULT_ORIGIN_RY
            self.raw_pupil_l_cv = None
            self.raw_pupil_r_cv = None

        self._apply_pupil_saturation()

        # Build 16:9 widescreen cockpit bezel edition
        wide_pil = Image.new("RGBA", (1920, 1080), (10, 10, 15, 255))
        talia_1080 = talia_pil.resize((1080, 1080), Image.Resampling.LANCZOS)
        wide_pil.paste(talia_1080, (420, 0), talia_1080)

        wide_np = np.array(wide_pil)
        qimg_wide = QImage(wide_np.data, 1920, 1080, 1920 * 4, QImage.Format.Format_RGBA8888)
        self.talia_wide = QPixmap.fromImage(qimg_wide.copy())

        # Invalidate scaled pixmap cache
        self._last_scaled_size = -1
        self.update()

    def _apply_pupil_saturation(self):
        """
        Adjusts pupil saturation & brightness based on application volume and power-down hold state:
        - At 50% volume (0.50): 100% normal (original eye colors).
        - Below 50%: Saturation and brightness scale down towards cold grayscale at 0% (mute).
        - Above 50%: Saturation scales up to 2.5x with neon brightness boost for high volume.
        - During 4s shutdown hold (after 2s): All saturation drops to 0.0 as Talia powers off.
        """
        if self.raw_pupil_l_cv is None or self.raw_pupil_r_cv is None:
            self.pupil_l = QPixmap()
            self.pupil_r = QPixmap()
            return

        vol = self.current_volume
        if vol <= 0.5:
            ratio = vol / 0.5
            sat_factor = ratio * self.hold_saturation
            val_factor = (0.55 + 0.45 * ratio) * (0.35 + 0.65 * self.hold_saturation)
        else:
            boost = (vol - 0.5) / 0.5
            sat_factor = (1.0 + boost * 1.5) * self.hold_saturation
            val_factor = (1.0 + boost * 0.35) * (0.35 + 0.65 * self.hold_saturation)

        def _process(cv_img):
            bgr = cv_img[:, :, :3].astype(np.float32)
            alpha = cv_img[:, :, 3]
            hsv = cv2.cvtColor(bgr.astype(np.uint8), cv2.COLOR_BGR2HSV).astype(np.float32)
            hsv[:, :, 1] = np.clip(hsv[:, :, 1] * sat_factor, 0, 255)
            hsv[:, :, 2] = np.clip(hsv[:, :, 2] * val_factor, 0, 255)
            new_bgr = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
            return cv2_to_qpixmap(np.dstack([new_bgr, alpha]))

        self.pupil_l = _process(self.raw_pupil_l_cv)
        self.pupil_r = _process(self.raw_pupil_r_cv)
        self._last_scaled_volume = self.current_volume
        self._last_scaled_size = -1

    def _on_hold_tick(self):
        """Ticks while holding mouse button. After 1s enables drag mode; after 3.0s initiates 0.6s sinking shutdown."""
        if self.is_shutting_down:
            return

        if not self.is_holding or self.has_dragged:
            self.hold_timer.stop()
            return

        elapsed = time.time() - self.press_time
        if elapsed >= 3.0:
            # Full 3 seconds held: Initiate 0.6s dramatic sinking power-down sequence!
            self.is_shutting_down = True
            self.shutdown_start_time = time.time()
            self.shutdown_start_pos = self.pos()
            self.hold_saturation = 0.0
            self._apply_pupil_saturation()
            if hasattr(self, "sound_hold") and self.sound_hold.isPlaying():
                self.sound_hold.stop()
            if hasattr(self, "sound_shutdown") and self.sound_shutdown.isLoaded():
                self.sound_shutdown.play()
            return
        elif elapsed >= 1.0:
            # At 1.0s mark: Trigger tactile button-press compression (50% more pressed in: 0.885 scale + delay)!
            if not self.drag_ready_triggered:
                self.drag_ready_triggered = True
                self.button_press_scale = 0.885
                self.button_press_delay = 0.08  # ~80ms bottom-out delay before spring release
                if hasattr(self, "sound_btn") and self.sound_btn.isLoaded():
                    self.sound_btn.play()

            # Between 1s and 3s: Desaturate the entire character towards grayscale
            # If user releases anytime between 1s and 3s, Move Talia (Drag Mode) is toggled!
            progress = (elapsed - 1.0) / 2.0  # 0.0 to 1.0 across the 2-second transition (from 1.0s to 3.0s)
            self.hold_saturation = max(0.0, 1.0 - progress)
            self._apply_pupil_saturation()
            self.update()
        else:
            self.hold_saturation = 1.0

    def _trigger_hover_feedback(self, char_size: int):
        """osu! lazer style subtle left-right rocking tilt and sway when cursor enters Talia."""
        self.impulse_rock_intensity = 1.8  # ~1.8 degrees smooth tilt
        self.impulse_sway_intensity = max(3.0, char_size * 0.007)  # ~6px sway
        self.impulse_timer = 0.22
        if hasattr(self, "sound_pop") and self.sound_pop.isLoaded():
            self.sound_pop.play()
        self.update()

    def _trigger_click_feedback(self, color: QColor, rot_degrees: float, alpha: float):
        """osu! lazer style tactile color flash and rotational bounce for clicks."""
        self.flash_color = color
        self.flash_alpha = alpha
        self.flash_hold_timer = 0.24  # Holds peak color solid for 0.24s (0.2s + 20%)
        self.impulse_rock_intensity = rot_degrees
        self.impulse_sway_intensity = 6.5
        self.impulse_timer = 0.24
        if hasattr(self, "sound_btn") and self.sound_btn.isLoaded():
            self.sound_btn.play()
        self.update()

    def enterEvent(self, event):
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.is_hovered = False
        self.was_hovered = False
        super().leaveEvent(event)

    def _start_restore_color_animation(self):
        """Smoothly restores color saturation if user released hold before 4 seconds."""
        self.restore_timer.start()

    def _on_restore_tick(self):
        """Ticks color saturation smoothly back to 1.0."""
        self.hold_saturation = min(1.0, self.hold_saturation + 0.08)
        self._apply_pupil_saturation()
        self.update()
        if self.hold_saturation >= 1.0:
            self.restore_timer.stop()

    def close_application(self):
        """Powers down Talia, auto-saves persistent settings, and terminates application instantly."""
        print("[SHUTDOWN] Talia powered down after 4s hold. Saving settings and exiting instantly...")
        if hasattr(self, "sound_hold") and self.sound_hold.isPlaying():
            self.sound_hold.stop()
        try:
            if self.panel:
                cfg = self.panel.get_current_settings_dict()
                save_settings(cfg)
        except Exception:
            pass

        self.audio_engine.shutdown()
        self.anim_timer.stop()
        self.topmost_timer.stop()
        self.hold_timer.stop()
        self.hide()
        QApplication.quit()
        import os
        os._exit(0)

    def set_volume(self, vol: float):
        """Sets in-app volume, updates pupil saturation, and syncs UI."""
        self.current_volume = max(0.0, min(1.0, float(vol)))
        self.audio_engine.set_volume(self.current_volume)
        self._apply_pupil_saturation()

        if self.panel:
            self.panel.sync_volume(self.current_volume)

        self.update()

    def init_position(self):
        screen = QApplication.primaryScreen().geometry()
        init_size = min(screen.height() - 60, 960)
        self.resize(init_size, init_size)
        self.move((screen.width() - init_size) // 2, (screen.height() - init_size) // 2)
        self.enforce_topmost()

    def enforce_topmost(self):
        if self.isVisible():
            hwnd = int(self.winId())
            user32.SetWindowPos(
                hwnd, HWND_TOPMOST,
                0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW
            )

    def set_move_talia_mode(self, enabled: bool):
        self.move_talia_mode = enabled
        if self.panel and hasattr(self.panel, "update_move_talia_ui"):
            self.panel.update_move_talia_ui()
        self.update()

    def trigger_startup_entrance(self):
        """Snappy 0.20s rise-up entrance from below with pop SFX when application launches."""
        self.target_startup_x = self.x()
        self.target_startup_y = self.y()
        self.startup_offset_y = min(140, max(75, int(self.height() * 0.16)))
        self.is_starting_up = True
        self.startup_start_time = 0.0  # Will be stamped on the very first live animation frame!
        self.move(self.target_startup_x, self.target_startup_y + self.startup_offset_y)
        self.update()

    def on_anim_tick(self):
        if not self.isVisible():
            return

        # Snappy Rise-Up Entrance Animation (<= 0.20s max)
        if self.is_starting_up:
            if self.startup_start_time == 0.0:
                self.startup_start_time = time.time()
                if hasattr(self, "sound_pop"):
                    self.sound_pop.stop()
                    self.sound_pop.play()

            elapsed = time.time() - self.startup_start_time
            p = min(1.0, elapsed / self.startup_duration)
            p_ease = 1.0 - ((1.0 - p) ** 3)  # Snappy cubic ease-out
            curr_y = int(self.target_startup_y + self.startup_offset_y * (1.0 - p_ease))
            self.move(self.target_startup_x, curr_y)
            if p >= 1.0:
                self.move(self.target_startup_x, self.target_startup_y)
                self.is_starting_up = False

        # Sinking Power-Down Shutdown Sequence (3.0s to 3.6s)
        if self.is_shutting_down:
            p = min(1.0, (time.time() - self.shutdown_start_time) / 0.60)
            p_ease = p * p  # Accelerating gravity sink
            sink_offset = int((self.height() + 120) * p_ease)
            self.move(self.shutdown_start_pos.x(), self.shutdown_start_pos.y() + sink_offset)
            self.opacity_val = max(0.0, 1.0 - (p ** 1.3))
            self.hold_saturation = 0.0
            self.current_rotation *= 0.70
            self.current_shake_x = 0.0
            self.current_shake_y = 0.0
            self.update()
            if p >= 1.0:
                self.close_application()
            return

        # 1. Update eye tracking relative to Talia's true screen coordinates
        cursor_pt = QCursor.pos()
        win_pos = self.mapToGlobal(QPoint(0, 0))

        if self.use_widescreen:
            char_size = self.height()
            char_offset_x = (self.width() - char_size) // 2
            char_offset_y = 0
        else:
            char_size = min(self.width(), self.height())
            char_offset_x = (self.width() - char_size) // 2
            char_offset_y = (self.height() - char_size) // 2

        scale = char_size / float(CANVAS_BASE_SIZE)

        # Exact center of left and right eyes in Global Screen Coordinates
        eye_lx = win_pos.x() + char_offset_x + (self.origin_lx + self.pupil_l.width() / 2.0) * scale
        eye_ly = win_pos.y() + char_offset_y + (self.origin_ly + self.pupil_l.height() / 2.0) * scale

        eye_rx = win_pos.x() + char_offset_x + (self.origin_rx + self.pupil_r.width() / 2.0) * scale
        eye_ry = win_pos.y() + char_offset_y + (self.origin_ry + self.pupil_r.height() / 2.0) * scale

        # Travel limits scaled by eye sensitivity
        max_travel_x = 18.0 * self.eye_sensitivity
        max_travel_y = 14.0 * self.eye_sensitivity

        # Left eye delta to cursor
        dx_l = float(cursor_pt.x() - eye_lx)
        dy_l = float(cursor_pt.y() - eye_ly)
        dist_l = math.hypot(dx_l, dy_l)
        if dist_l > 4:
            power_l = min(1.0, (dist_l / 280.0) ** 0.75)
            self.target_offset_lx = (dx_l / dist_l) * max_travel_x * power_l
            self.target_offset_ly = (dy_l / dist_l) * max_travel_y * power_l
        else:
            self.target_offset_lx = 0.0
            self.target_offset_ly = 0.0

        # Right eye delta to cursor
        dx_r = float(cursor_pt.x() - eye_rx)
        dy_r = float(cursor_pt.y() - eye_ry)
        dist_r = math.hypot(dx_r, dy_r)
        if dist_r > 4:
            power_r = min(1.0, (dist_r / 280.0) ** 0.75)
            self.target_offset_rx = (dx_r / dist_r) * max_travel_x * power_r
            self.target_offset_ry = (dy_r / dist_r) * max_travel_y * power_r
        else:
            self.target_offset_rx = 0.0
            self.target_offset_ry = 0.0

        # Smooth interpolation (lerp)
        self.current_offset_lx += (self.target_offset_lx - self.current_offset_lx) * 0.25
        self.current_offset_ly += (self.target_offset_ly - self.current_offset_ly) * 0.25
        self.current_offset_rx += (self.target_offset_rx - self.current_offset_rx) * 0.25
        self.current_offset_ry += (self.target_offset_ry - self.current_offset_ry) * 0.25

        # 2. Hover hit-testing & smooth osu! lazer luminous lighting (~20% highlight)
        global_char_x = win_pos.x() + char_offset_x
        global_char_y = win_pos.y() + char_offset_y
        center_x = global_char_x + char_size / 2.0
        center_y = global_char_y + char_size / 2.0
        dist_to_center = math.hypot(cursor_pt.x() - center_x, cursor_pt.y() - center_y)
        is_hovering = dist_to_center <= (char_size * 0.48)

        if is_hovering and not self.was_hovered:
            self._trigger_hover_feedback(char_size)
            self.was_hovered = True
        elif not is_hovering and self.was_hovered:
            self.was_hovered = False

        # Smooth hover glow interpolation (noticeable ~20% luminous bloom)
        target_glow = 0.20 if self.was_hovered else 0.0
        self.hover_glow += (target_glow - self.hover_glow) * 0.22

        # Subtle 1.2% breathing scale on hover
        target_hover_scale = 1.012 if self.was_hovered else 1.0
        self.hover_scale += (target_hover_scale - self.hover_scale) * 0.20

        # 3. Button press tactile spring bounce back to 1.0 (with bottom-out delay & 25% delayed recovery rate)
        if self.button_press_delay > 0.0:
            self.button_press_delay -= 0.016
        elif abs(self.button_press_scale - 1.0) > 0.001:
            self.button_press_scale += (1.0 - self.button_press_scale) * 0.20
        else:
            self.button_press_scale = 1.0

        # 3.5. Beat Pop effect (Talia pulses with the music bass kick)
        if self.enable_bass_pop:
            target_pop = 1.0 + float(getattr(self.audio_engine, "beat_energy", 0.0)) * 0.038
            self.bass_pop_scale += (target_pop - self.bass_pop_scale) * 0.35
        else:
            self.bass_pop_scale += (1.0 - self.bass_pop_scale) * 0.35

        # 4. Click tactile flash: 0.24s solid hold, followed by smooth exponential fade-out
        if self.flash_hold_timer > 0.0:
            self.flash_hold_timer -= 0.016
        elif self.flash_alpha > 0.005:
            self.flash_alpha *= 0.82
        else:
            self.flash_alpha = 0.0

        # 4.5. Cyber Mute Indicator Interpolation (Smooth fade in when paused, fade out when playing)
        is_paused = not getattr(self.audio_engine, "is_active", self.audio_engine.is_playing)
        target_mute = 1.0 if is_paused else 0.0
        self.mute_alpha += (target_mute - self.mute_alpha) * 0.22

        # 5. Dynamic Rotation & Sway computation (osu! lazer left-right rocking & tilt)
        t = time.time()
        if self.is_holding and not self.has_dragged:
            elapsed = t - self.press_time
            if elapsed < 2.0:
                # 0.0s to 2.0s: Reduced by 50% at start! Gentle, subtle rocking (tilt +/- 0.7 to 1.4 deg, sway 2-4px)
                progress = elapsed / 2.0
                rot_amp = (0.7 + progress * 0.7)
                sway_amp = (2.0 + progress * 2.0) * (char_size / 850.0)
                self.current_rotation = math.sin(t * 16.0) * rot_amp
                self.current_shake_x = math.sin(t * 16.0 + 0.3) * sway_amp
                self.current_shake_y = math.cos(t * 32.0) * (0.8 + progress * 0.8)
            else:
                # 2.0s to 3.0s: "start going a bit harder after 2 seconds" towards 3.0s shutdown
                progress_hard = min(1.0, elapsed - 2.0)
                rot_amp = (1.4 + progress_hard * 4.0)
                sway_amp = (4.0 + progress_hard * 12.0) * (char_size / 850.0)
                self.current_rotation = math.sin(t * 26.0) * rot_amp
                self.current_shake_x = math.sin(t * 26.0 + 0.3) * sway_amp
                self.current_shake_y = math.cos(t * 52.0) * (1.6 + progress_hard * 3.4)
        elif self.impulse_timer > 0.0:
            self.impulse_timer -= 0.016
            decay = max(0.0, self.impulse_timer / 0.24)
            # Smooth left-right bounce rocking easing to 0
            self.current_rotation = math.sin(t * 22.0) * (self.impulse_rock_intensity * decay)
            self.current_shake_x = math.sin(t * 22.0 + 0.3) * (self.impulse_sway_intensity * decay)
            self.current_shake_y = math.cos(t * 44.0) * (2.0 * decay)
        else:
            self.current_rotation *= 0.75
            self.current_shake_x *= 0.75
            self.current_shake_y *= 0.75
            if abs(self.current_rotation) < 0.02:
                self.current_rotation = 0.0
            if abs(self.current_shake_x) < 0.05:
                self.current_shake_x = 0.0
            if abs(self.current_shake_y) < 0.05:
                self.current_shake_y = 0.0

        # Trigger redraw
        self.update()

    def _ensure_scaled_pixmaps(self, char_size: int, scale: float):
        """Optimized caching: rescales pixmaps only when character size or eye volume saturation changes."""
        if self._last_scaled_size == char_size and getattr(self, "_last_scaled_volume", None) == self.current_volume:
            return

        self._last_scaled_size = char_size
        self._last_scaled_volume = self.current_volume
        self._cached_scaled_whites = self.whites.scaled(
            char_size, char_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self._cached_scaled_talia = self.talia_sprite.scaled(
            char_size, char_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self._cached_scaled_talia_gray = self.talia_sprite_gray.scaled(
            char_size, char_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        w_l = max(1, int(self.pupil_l.width() * scale))
        h_l = max(1, int(self.pupil_l.height() * scale))
        self._cached_scaled_pupil_l = self.pupil_l.scaled(
            w_l, h_l,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        w_r = max(1, int(self.pupil_r.width() * scale))
        h_r = max(1, int(self.pupil_r.height() * scale))
        self._cached_scaled_pupil_r = self.pupil_r.scaled(
            w_r, h_r,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setOpacity(self.opacity_val)

        if self.use_widescreen:
            char_size = self.height()
            char_x = (self.width() - char_size) // 2
            char_y = 0
            scaled_wide = self.talia_wide.scaled(
                self.width(), self.height(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            painter.drawPixmap(0, 0, scaled_wide)
        else:
            char_size = min(self.width(), self.height())
            char_x = (self.width() - char_size) // 2
            char_y = (self.height() - char_size) // 2

        scale = char_size / float(CANVAS_BASE_SIZE)
        self._ensure_scaled_pixmaps(char_size, scale)

        # Save painter state and apply 2D matrix transformations for tactile button press, rotation, and sway
        painter.save()

        center_x = char_x + char_size / 2.0
        center_y = char_y + char_size / 2.0

        # 1. Total Scale (Tactile Button-Press punch * Hover breathing scale * Bass beat pop)
        total_scale = self.button_press_scale * self.hover_scale * self.bass_pop_scale
        if abs(total_scale - 1.0) > 0.001:
            painter.translate(center_x, center_y)
            painter.scale(total_scale, total_scale)
            painter.translate(-center_x, -center_y)

        # 2. Dynamic Rotation (osu! lazer left-right rocking & tilt)
        if abs(self.current_rotation) > 0.02:
            painter.translate(center_x, center_y)
            painter.rotate(self.current_rotation)
            painter.translate(-center_x, -center_y)

        # 3. Dynamic Sway Displacement
        if abs(self.current_shake_x) > 0.05 or abs(self.current_shake_y) > 0.05:
            painter.translate(self.current_shake_x, self.current_shake_y)

        # ==========================================================
        # LAYER 0: CYBERPUNK AUDIO VISUALIZER (Inside Mouth Cavity)
        # ==========================================================
        mouth_x = char_x + int(MOUTH_BOX_X * scale)
        mouth_y = char_y + int(MOUTH_BOX_Y * scale)
        mouth_w = int(MOUTH_BOX_W * scale)
        mouth_h = int(MOUTH_BOX_H * scale)
        mouth_rect = QRect(mouth_x, mouth_y, mouth_w, mouth_h)

        if self.hold_saturation > 0.05:
            vis_opacity = self.opacity_val * self.hold_saturation
            painter.setOpacity(vis_opacity)
            self.visualizer.draw(painter, mouth_rect, self.audio_engine)
            painter.setOpacity(self.opacity_val)

        # ==========================================================
        # LAYER 0.5: CYBER MUTE INDICATOR (Inside Mouth Cavity on Pause)
        # ==========================================================
        if self.mute_alpha > 0.005 and not self.mute_icon.isNull() and self.hold_saturation > 0.05:
            t = time.time()
            pulse = 0.88 + 0.12 * math.sin(t * 3.5)
            eff_alpha = min(1.0, max(0.0, self.mute_alpha * pulse))
            cx = mouth_x + mouth_w // 2
            cy = mouth_y + mouth_h // 2
            icon_dim = max(18, int(mouth_h * 0.56))

            # 1. Soft Cyber Neon Radial Glow
            glow_rad = icon_dim * 0.90
            glow = QRadialGradient(cx, cy, glow_rad)
            glow.setColorAt(0.0, QColor(255, 30, 60, int(85 * eff_alpha)))
            glow.setColorAt(0.55, QColor(255, 10, 40, int(30 * eff_alpha)))
            glow.setColorAt(1.0, QColor(255, 0, 30, 0))
            painter.setBrush(glow)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPoint(cx, cy), int(glow_rad), int(glow_rad))

            # 2. Sleek Cyber HUD Corner Brackets
            bracket_pad = int(icon_dim * 0.12)
            bx1 = cx - icon_dim // 2 - bracket_pad
            bx2 = cx + icon_dim // 2 + bracket_pad
            by1 = cy - icon_dim // 2 - bracket_pad
            by2 = cy + icon_dim // 2 + bracket_pad
            blen = max(4, int(icon_dim * 0.18))

            bpen = QPen(QColor(255, 45, 75, int(180 * eff_alpha)), max(1, int(1.5 * scale)))
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

            # 3. Mute Icon Pixmap
            if self._cached_scaled_mute_size != icon_dim:
                self._cached_scaled_mute = self.mute_icon.scaled(
                    icon_dim, icon_dim,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self._cached_scaled_mute_size = icon_dim

            ix = cx - self._cached_scaled_mute.width() // 2
            iy = cy - self._cached_scaled_mute.height() // 2
            painter.setOpacity(self.opacity_val * eff_alpha * self.hold_saturation)
            painter.drawPixmap(ix, iy, self._cached_scaled_mute)
            painter.setOpacity(self.opacity_val)

        # ==========================================================
        # LAYER 3: EYE WHITES (Sclera Back Layer)
        # ==========================================================
        if self.hold_saturation < 1.0:
            painter.setOpacity(self.opacity_val * (0.35 + 0.65 * self.hold_saturation))
            painter.drawPixmap(char_x, char_y, self._cached_scaled_whites)
            painter.setOpacity(self.opacity_val)
        else:
            painter.drawPixmap(char_x, char_y, self._cached_scaled_whites)

        # ==========================================================
        # LAYER 2: MOVING PUPILS + HIGH-VOLUME CYBER NEON GLOW
        # ==========================================================
        pos_lx = int(char_x + (self.origin_lx + self.current_offset_lx) * scale)
        pos_ly = int(char_y + (self.origin_ly + self.current_offset_ly) * scale)
        pos_rx = int(char_x + (self.origin_rx + self.current_offset_rx) * scale)
        pos_ry = int(char_y + (self.origin_ry + self.current_offset_ry) * scale)

        # High volume iris bloom (> 50% volume)
        if self.current_volume > 0.50 and self.hold_saturation > 0.2:
            glow_intensity = (self.current_volume - 0.50) / 0.50
            glow_alpha = int(110 * glow_intensity * self.hold_saturation)
            glow_color = QColor(0, 240, 255, glow_alpha)

            pw_l = self._cached_scaled_pupil_l.width()
            ph_l = self._cached_scaled_pupil_l.height()
            center_lx = pos_lx + pw_l / 2.0
            center_ly = pos_ly + ph_l / 2.0

            pw_r = self._cached_scaled_pupil_r.width()
            ph_r = self._cached_scaled_pupil_r.height()
            center_rx = pos_rx + pw_r / 2.0
            center_ry = pos_ry + ph_r / 2.0

            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            rad_l = max(pw_l, ph_l) * 0.85
            grad_l = QRadialGradient(center_lx, center_ly, rad_l)
            grad_l.setColorAt(0.0, glow_color)
            grad_l.setColorAt(1.0, QColor(0, 240, 255, 0))
            painter.setBrush(grad_l)
            painter.drawEllipse(QPointF(center_lx, center_ly), rad_l, rad_l)

            rad_r = max(pw_r, ph_r) * 0.85
            grad_r = QRadialGradient(center_rx, center_ry, rad_r)
            grad_r.setColorAt(0.0, glow_color)
            grad_r.setColorAt(1.0, QColor(0, 240, 255, 0))
            painter.setBrush(grad_r)
            painter.drawEllipse(QPointF(center_rx, center_ry), rad_r, rad_r)
            painter.restore()

        painter.drawPixmap(pos_lx, pos_ly, self._cached_scaled_pupil_l)
        painter.drawPixmap(pos_rx, pos_ry, self._cached_scaled_pupil_r)

        # ==========================================================
        # LAYER 1: TALIA MAIN SPRITE (Front Layer - Frames Mouth & Eyes)
        # ==========================================================
        if self.hold_saturation < 1.0:
            # Powering down: Draw grayscale sprite base underneath, color sprite on top with fading opacity
            painter.drawPixmap(char_x, char_y, self._cached_scaled_talia_gray)
            painter.setOpacity(self.opacity_val * self.hold_saturation)
            painter.drawPixmap(char_x, char_y, self._cached_scaled_talia)
            painter.setOpacity(self.opacity_val)
        else:
            painter.drawPixmap(char_x, char_y, self._cached_scaled_talia)

        # ==========================================================
        # LAYER 4: CRT MONITOR SCANLINES (Across Mouth Opening)
        # ==========================================================
        if self.enable_scanlines:
            painter.setOpacity(0.20 * self.hold_saturation)
            pen = QPen(QColor(0, 0, 0, 220), 1)
            painter.setPen(pen)
            y_start = char_y + int(MOUTH_BOX_Y * scale)
            y_end = char_y + int((MOUTH_BOX_Y + MOUTH_BOX_H) * scale)
            x_start = char_x + int(MOUTH_BOX_X * scale)
            x_end = char_x + int((MOUTH_BOX_X + MOUTH_BOX_W) * scale)
            for line_y in range(y_start, y_end, 3):
                painter.drawLine(x_start, line_y, x_end, line_y)

        # ==========================================================
        # FEEDBACK SATISFACTION: HOVER LIGHTING & CLICK TACTILE FLASH
        # ==========================================================
        char_rect = QRect(char_x, char_y, char_size, char_size)

        # 1. Noticeable osu! lazer luminous hover highlight (~20% luminous bloom)
        if self.hover_glow > 0.005:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
            hover_alpha = int(255 * min(0.35, self.hover_glow))
            painter.fillRect(char_rect, QColor(255, 255, 255, hover_alpha))
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # 2. Click Tactile Color Flash (0.24s solid hold + smooth exponential fade)
        if self.flash_alpha > 0.005:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
            fc = QColor(self.flash_color)
            fc.setAlpha(int(255 * min(0.75, self.flash_alpha)))
            painter.fillRect(char_rect, fc)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # Restore painter matrix transform
        painter.restore()

        # ==========================================================
        # LAYER 5: SETUP MODE GUIDING BORDER (Visible only in Move Mode)
        # ==========================================================
        if self.move_talia_mode:
            painter.setOpacity(0.85)
            border_pen = QPen(QColor(0, 240, 255, 200), 2, Qt.PenStyle.DashLine)
            painter.setPen(border_pen)
            painter.drawRect(1, 1, self.width() - 2, self.height() - 2)

    def mousePressEvent(self, event):
        if self.is_shutting_down:
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.press_pos = event.globalPosition().toPoint()
            self.press_time = time.time()
            self.is_holding = True
            self.has_dragged = False
            self.drag_ready_triggered = False
            self.button_press_delay = 0.0
            self.restore_timer.stop()
            self.hold_timer.start(25)

            if hasattr(self, "sound_hold") and self.sound_hold.isLoaded():
                self.sound_hold.stop()
                self.sound_hold.play()

            if self.move_talia_mode:
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                self.is_dragging = True
            else:
                self.is_dragging = False

            event.accept()

    def mouseMoveEvent(self, event):
        if self.is_shutting_down:
            event.accept()
            return
        if event.buttons() & Qt.MouseButton.LeftButton:
            dist = (event.globalPosition().toPoint() - self.press_pos).manhattanLength()
            if dist > 6:
                self.has_dragged = True
                if hasattr(self, "sound_hold") and self.sound_hold.isPlaying():
                    self.sound_hold.stop()

            if self.move_talia_mode:
                self.move(event.globalPosition().toPoint() - self.drag_position)

            event.accept()

    def mouseReleaseEvent(self, event):
        if self.is_shutting_down:
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            elapsed = time.time() - self.press_time
            self.is_holding = False
            self.hold_timer.stop()

            if hasattr(self, "sound_hold") and self.sound_hold.isPlaying():
                self.sound_hold.stop()

            if self.has_dragged:
                # User dragged Talia in Move Mode
                self.is_dragging = False
                event.accept()
                return

            if 1.0 <= elapsed < 3.0:
                # User held for 1+ seconds and let go: TOGGLE DRAG MODE!
                self.hold_saturation = 1.0
                self._apply_pupil_saturation()
                self.update()
                new_mode = not self.move_talia_mode
                self.set_move_talia_mode(new_mode)
                status = "ON (Drag to Move / Scroll to Resize)" if new_mode else "OFF (Locked & Clickable)"
                print(f"[ACTION] Held for 1s: Move Talia Mode is now {status}!")
            elif elapsed < 0.45:
                # Short tap/click: count for 1x, 2x, 3x multi-click
                if self.hold_saturation < 1.0:
                    self._start_restore_color_animation()
                self._handle_click()
            else:
                # Held between 0.45s and 1.0s: restore color if needed
                if self.hold_saturation < 1.0:
                    self._start_restore_color_animation()

            self.is_dragging = False
            event.accept()

    def _handle_click(self):
        """Dispatches single, double, or triple clicks cleanly with tactile satisfaction flashes & shakes."""
        self.click_count += 1
        if self.click_count == 1:
            # 1 Click: Instant WHITE flash (holds 0.24s) + osu! lazer tilt bounce!
            self._trigger_click_feedback(color=QColor(255, 255, 255), rot_degrees=-2.2, alpha=0.65)
            self.multi_click_timer.start(340)
        elif self.click_count == 2:
            # 2 Clicks: Instant CRIMSON RED flash (holds 0.24s) + osu! lazer tilt bounce!
            self._trigger_click_feedback(color=QColor(255, 30, 80), rot_degrees=2.5, alpha=0.68)
            self.multi_click_timer.start(340)
        elif self.click_count >= 3:
            # 3 Clicks: Instant GOLDEN YELLOW flash (holds 0.24s) + osu! lazer tilt bounce & open Controller!
            self._trigger_click_feedback(color=QColor(255, 215, 0), rot_degrees=-3.0, alpha=0.70)
            self.multi_click_timer.stop()
            self.click_count = 0
            self._trigger_triple_click()

    def _on_multi_click_timeout(self):
        """Called when no further clicks arrived within 280ms."""
        count = self.click_count
        self.click_count = 0
        if count == 1:
            self._trigger_single_click()
        elif count == 2:
            self._trigger_double_click()

    def _trigger_single_click(self):
        """1 Click on Talia: Toggle Play / Pause."""
        if self.audio_engine.audio_mode == "desktop":
            self.audio_engine.toggle_play_pause()
            return
        if not self.audio_engine.playlist:
            return
        if self.audio_engine.current_index < 0:
            self.audio_engine.play_index(0)
        else:
            self.audio_engine.toggle_play_pause()
        if self.panel:
            self.panel.sync_play_state()
        print("[ACTION] 1 Click on Talia: Play/Pause toggled.")

    def _trigger_double_click(self):
        """2 Clicks on Talia: Skip to Next Track."""
        if self.audio_engine.audio_mode == "desktop":
            self.audio_engine.next_track()
            return
        if not self.audio_engine.playlist:
            return
        self.audio_engine.next_track()
        if self.panel:
            self.panel.sync_play_state()
        print("[ACTION] 2 Clicks on Talia: Skipped to Next Song.")

    def _trigger_triple_click(self):
        """3 Clicks on Talia: Open / Show Controller Panel."""
        if self.panel:
            self.panel.show()
            self.panel.raise_()
            self.panel.activateWindow()
            print("[ACTION] 3 Clicks on Talia: Controller Panel Opened.")

    def wheelEvent(self, event):
        if self.is_shutting_down:
            event.accept()
            return
        delta = event.angleDelta().y()
        if self.move_talia_mode:
            step = 50 if delta > 0 else -50
            new_w = max(MIN_CHAR_SIZE, min(self.width() + step, MAX_CHAR_SIZE))
            new_h = max(MIN_CHAR_SIZE, min(self.height() + step, MAX_CHAR_SIZE))
            self.resize(new_w, new_h)
            if self.panel:
                self.panel.slider_size.blockSignals(True)
                self.panel.slider_size.setValue(new_w)
                self.panel.slider_size.blockSignals(False)
            event.accept()
        else:
            step = 0.05 if delta > 0 else -0.05
            new_vol = max(0.0, min(1.0, round(self.current_volume + step, 2)))
            self.set_volume(new_vol)
            print(f"[ACTION] Volume adjusted: {int(new_vol * 100)}% (Eye saturation updated)")
            event.accept()
