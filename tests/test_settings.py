"""Settings persistence: defaults, atomic writes, and portable paths."""

import json
import os

from config import PROJECT_ROOT, SETTINGS_VERSION, load_settings, save_settings


def test_roundtrip_and_portable_path(tmp_path):
    target = tmp_path / "settings.json"
    cfg = {
        "music_folder": os.path.join(PROJECT_ROOT, "music"),
        "download_folder": "",
        "volume": 0.31,
        "shuffle": True,
    }

    assert save_settings(cfg, str(target))
    raw = json.loads(target.read_text(encoding="utf-8"))
    assert raw["music_folder"] == "music"
    assert raw["_version"] == SETTINGS_VERSION
    assert list(tmp_path.glob(".talia-settings-*.tmp")) == []

    loaded = load_settings(str(target))
    assert loaded["music_folder"] == os.path.normpath(os.path.join(PROJECT_ROOT, "music"))
    assert loaded["volume"] == 0.31
    assert loaded["shuffle"] is True


def test_missing_file_returns_defaults(tmp_path):
    loaded = load_settings(str(tmp_path / "absent.json"))
    assert loaded["_version"] == SETTINGS_VERSION
    assert loaded["visualizer_mode"] == "Neon Wave"


def test_corrupt_file_falls_back_to_defaults(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text("{ this is not json", encoding="utf-8")
    loaded = load_settings(str(target))
    assert loaded["volume"] == 0.49
    assert loaded["_version"] == SETTINGS_VERSION


def test_unknown_keys_are_preserved(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"future_setting": 42}), encoding="utf-8")
    loaded = load_settings(str(target))
    assert loaded["future_setting"] == 42


def test_save_is_atomic_under_repeat_calls(tmp_path):
    target = tmp_path / "settings.json"
    for index in range(20):
        assert save_settings({"volume": index / 20}, str(target))
        loaded = load_settings(str(target))
        assert loaded["volume"] == index / 20
    assert list(tmp_path.glob(".talia-settings-*.tmp")) == []
