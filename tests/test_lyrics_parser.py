"""Unit tests for the LRC parser and offset handling."""

import pytest

from lyrics_manager import LyricsManager


@pytest.fixture()
def manager():
    return LyricsManager()


def test_parse_standard_and_multi_timestamp(manager):
    lrc = "[00:01.50]Hello\n[00:03.00][00:05.00]Again\n[00:07]Last\n"
    lines = manager.parse_lrc(lrc)
    assert [timestamp for timestamp, _ in lines] == [1.5, 3.0, 5.0, 7.0]
    assert [text for _, text in lines] == ["Hello", "Again", "Again", "Last"]


def test_parse_three_digit_milliseconds(manager):
    lines = manager.parse_lrc("[01:02.345]Precise\n")
    assert lines == [(62.345, "Precise")]


def test_offset_tag_is_read(manager):
    manager.parse_lrc("[offset:+500]\n[00:10.00]Line\n")
    assert manager.file_offset == 0.5
    manager.parse_lrc("[offset:-250]\n[00:10.00]Line\n")
    assert manager.file_offset == -0.25


def test_invalid_lines_are_ignored_but_blank_cues_are_kept(manager):
    # A timestamp with no text is a deliberate "clear the lyric" cue used during
    # instrumental breaks, so it must survive parsing.
    lines = manager.parse_lrc("not a timestamp\n[00:02.00]\n\n[00:01.00]Real\n")
    assert lines == [(1.0, "Real"), (2.0, "")]


def test_manual_offset_moves_active_line(manager):
    manager.lines = [(10.0, "hello world")]
    manager.manual_offset = 1.0
    manager.file_offset = 0.0
    assert manager.get_current_line_info(9.2)[1] == "hello world"
    assert manager.get_current_line_info(7.0)[0] == -1


def test_get_total_offset_is_sum(manager):
    manager.manual_offset = 0.25
    manager.file_offset = 0.5
    assert manager.get_total_offset() == 0.75


def test_slow_bar_lyrics_does_not_disappear_early(manager):
    # Two lines with a 7-second gap (slow bar / held note)
    manager.lines = [(1.0, "Never fade away"), (8.0, "A thing of beauty")]
    manager.manual_offset = 0.0
    manager.file_offset = 0.0

    # At 5.5s (4.5s into line 1), it must NOT disappear
    idx, text, time_into, singing_dur = manager.get_current_line_info(5.5)
    assert idx == 0
    assert text == "Never fade away"
    assert time_into == 4.5
    assert singing_dur > 4.0

    # At 7.0s (6.0s into line 1), still singing/visible
    idx, text, time_into, singing_dur = manager.get_current_line_info(7.0)
    assert idx == 0
    assert text == "Never fade away"

    # At 8.1s, transitioned to line 2
    idx, text, time_into, _ = manager.get_current_line_info(8.1)
    assert idx == 1
    assert text == "A thing of beauty"
