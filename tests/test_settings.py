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


def test_lyrics_font_size_default_and_clamping(tmp_path):
    target = tmp_path / "settings.json"
    # Defaults
    loaded = load_settings(str(target))
    assert loaded["lyrics_font_size"] == 18

    # Valid custom value
    save_settings({"lyrics_font_size": 36}, str(target))
    loaded = load_settings(str(target))
    assert loaded["lyrics_font_size"] == 36

    # Clamping below minimum
    save_settings({"lyrics_font_size": 5}, str(target))
    loaded = load_settings(str(target))
    assert loaded["lyrics_font_size"] == 14

    # Clamping above maximum
    save_settings({"lyrics_font_size": 999}, str(target))
    loaded = load_settings(str(target))
    assert loaded["lyrics_font_size"] == 60


def test_queue_persistence_roundtrip(tmp_path):
    target = tmp_path / "settings.json"
    song1 = os.path.join(PROJECT_ROOT, "music", "song1.mp3")
    song2 = "D:/OutsideMusic/song2.flac"

    # Save queue
    cfg = {
        "queue": [song1, song2],
    }
    assert save_settings(cfg, str(target))

    # Verify portable conversion
    raw = json.loads(target.read_text(encoding="utf-8"))
    assert raw["queue"][0] == "music/song1.mp3"
    assert raw["queue"][1] == "D:/OutsideMusic/song2.flac"

    # Verify load resolving
    loaded = load_settings(str(target))
    assert loaded["queue"][0] == os.path.normpath(song1)
    assert loaded["queue"][1] == os.path.normpath(song2)
