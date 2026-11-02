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


@pytest.fixture(scope="session", autouse=True)
def qapp():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


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
