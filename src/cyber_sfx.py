import os
import time
from typing import Dict, Optional
from PyQt6.QtCore import QObject, QUrl
from PyQt6.QtMultimedia import QSoundEffect

BASE_CYBER_SFX_VOLUME = 0.32
_current_talia_volume = 0.49


def compute_sfx_volume_multiplier(talia_volume: float) -> float:
    """Scale SFX amplitude smoothly with Talia's master volume [0.0, 1.0].

    - volume = 0.0 -> 0.18x base (quiet subtle tactile feedback)
    - volume = 0.5 -> 0.75x base (normal, still a little quiet)
    - volume = 1.0 -> 1.32x base (normal, a little louder)
    """
    vol = max(0.0, min(1.0, float(talia_volume)))
    return 0.18 + 1.14 * vol


def set_cyber_sfx_talia_volume(talia_volume: float) -> None:
    """Propagate Talia's volume setting to CyberSfxManager without forcing eager creation."""
    global _current_talia_volume
    _current_talia_volume = max(0.0, min(1.0, float(talia_volume)))
    inst = CyberSfxManager._instance
    if inst is not None:
        inst.set_talia_volume(_current_talia_volume)


class CyberSfxManager(QObject):
    """
    Zero-latency, high-performance sound effects manager powered by Cyberpunk 2077 UI SFX.
    """
    _instance: Optional["CyberSfxManager"] = None

    @classmethod
    def instance(cls) -> "CyberSfxManager":
        if cls._instance is None:
            cls._instance = CyberSfxManager()
        return cls._instance

    def __init__(self, parent=None):
        super().__init__(parent)
        self._effects: Dict[str, QSoundEffect] = {}
        self._last_played: Dict[str, float] = {}
        self.enabled = True
        self._base_volume = BASE_CYBER_SFX_VOLUME
        self.volume = min(1.0, self._base_volume * compute_sfx_volume_multiplier(_current_talia_volume))

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        sfx_dir = os.path.join(project_root, "assets", "sounds", "cyberpunk_ui")
        if not os.path.exists(sfx_dir):
            sfx_dir = os.path.join(project_root, "sounds", "cyberpunk_ui")

        sound_files = {
            "click": "ui_menu_mouse_click.wav",
            "hover": "ui_menu_hover.wav",
            "press": "ui_menu_onpress.wav",
            "value_up": "ui_menu_value_up.wav",
            "value_down": "ui_menu_value_down.wav",
            "open": "ui_menu_open.wav",
            "close": "ui_menu_close.wav",
            "tab": "ui_main_menu_open_tab.wav",
            "delete": "ui_main_menu_saves_delete_confirmation.wav",
            "add": "ui_menu_perk_buy.wav",
            "level_up": "ui_menu_perk_level_up.wav",
            "enter": "ui_menu_enter.wav",
            "exit": "ui_menu_exit.wav",
        }

        for key, fname in sound_files.items():
            fpath = os.path.join(sfx_dir, fname)
            if os.path.exists(fpath):
                effect = QSoundEffect(self)
                effect.setSource(QUrl.fromLocalFile(fpath))
                effect.setVolume(self.volume)
                self._effects[key] = effect

    def set_talia_volume(self, talia_volume: float):
        """Scale all loaded Cyberpunk UI SFX from Talia's master volume."""
        mult = compute_sfx_volume_multiplier(talia_volume)
        self.set_volume(self._base_volume * mult)

    def set_volume(self, volume: float):
        self.volume = max(0.0, min(1.0, volume))
        for effect in self._effects.values():
            try:
                effect.setVolume(self.volume)
            except Exception:
                pass

    def play(self, name: str, throttle_ms: float = 0.0):
        if not self.enabled:
            return
        effect = self._effects.get(name)
        if not effect:
            return
        now = time.time()
        if throttle_ms > 0:
            last = self._last_played.get(name, 0.0)
            if (now - last) * 1000.0 < throttle_ms:
                return
        self._last_played[name] = now
        try:
            effect.play()
        except Exception:
            pass

    def play_click(self):
        self.play("click", throttle_ms=30.0)

    def play_hover(self):
        self.play("hover", throttle_ms=45.0)

    def play_value(self, is_up: bool):
        self.play("value_up" if is_up else "value_down", throttle_ms=50.0)

    def play_open(self):
        self.play("open")

    def play_close(self):
        self.play("close")

    def play_tab(self):
        self.play("tab")

    def play_delete(self):
        self.play("delete")

    def play_add(self):
        self.play("add")

    def play_level_up(self):
        self.play("level_up")


def get_cyber_sfx() -> CyberSfxManager:
    return CyberSfxManager.instance()
