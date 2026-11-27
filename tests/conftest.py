"""Shared pytest setup for Talia."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["TALIA_DISABLE_DISCORD_RPC"] = "1"

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "Talia Lyrics Fetch Automated"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import pytest  # noqa: E402


_SESSION_QAPP = None


@pytest.fixture(scope="session", autouse=True)
def qapp():
    global _SESSION_QAPP
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    _SESSION_QAPP = app
    yield app


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Keep every test away from the real settings.json.

    Constructing ControlPanel/OverlayWindow triggers save paths, so without
    this the suite overwrites the user's live settings with test defaults.
    """
    import config

    monkeypatch.setattr(config, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    yield


@pytest.fixture(autouse=True)
def cleanup_after_test():
    yield
    try:
        from audio_engine import _cleanup_audio_engines
        _cleanup_audio_engines()
    except Exception:
        pass
    try:
        from party_sync import _cleanup_party_services
        _cleanup_party_services()
    except Exception:
        pass
    try:
        from discord_service import _cleanup_discord_services
        _cleanup_discord_services()
    except Exception:
        pass
    try:
        from audio_feeder import _cleanup_audio_feeders
        _cleanup_audio_feeders()
    except Exception:
        pass
    try:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            for w in list(app.topLevelWidgets()):
                for attr in ("anim_timer", "topmost_timer", "timeline_timer", "hotkey_timer", "multi_click_timer", "hold_timer", "restore_timer"):
                    t = getattr(w, attr, None)
                    if t is not None:
                        try:
                            t.stop()
                        except Exception:
                            pass
    except Exception:
        pass


@pytest.fixture()
def sample_wav(tmp_path):
    import numpy as np
    import soundfile as sf

    sr = 8000
    frames = 4000
    t = np.arange(frames, dtype=np.float32) / sr
    left = np.sin(2 * np.pi * 220 * t).astype(np.float32)
    right = np.sin(2 * np.pi * 330 * t).astype(np.float32)
    data = np.column_stack([left, right])
    path = tmp_path / "sample.wav"
    sf.write(path, data, sr, subtype="FLOAT")
    return path, data, sr


def pytest_sessionfinish(session, exitstatus):
    import os
    import sys
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exitstatus)
