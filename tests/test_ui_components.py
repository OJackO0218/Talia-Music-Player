"""
Unit tests for Talia's Cyberpunk UI Component Library (ui_widgets & ui_theme).
"""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from ui_theme import BUTTON_VARIANTS, CARD_STYLE, COLOR_BG_CARD
from ui_widgets import (
    CyberButton,
    CyberCard,
    CyberLineEdit,
    CyberSlider,
    CyberToggle,
    create_section_header,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_cyber_button_variants(qapp):
    btn = CyberButton("Test Button", variant="primary")
    assert btn.text() == "Test Button"
    assert "background-color" in btn.styleSheet()

    # Change to purple variant
    btn.set_variant("purple")
    assert btn.styleSheet() == BUTTON_VARIANTS["purple"]

    # Verify click callback
    clicked_flag = []
    btn_click = CyberButton("Click Me", on_click=lambda: clicked_flag.append(True))
    btn_click.click()
    assert len(clicked_flag) == 1


def test_cyber_card_container(qapp):
    card = CyberCard(title="Audio Settings")
    assert card.objectName() == "cyberCard"

    lbl = QLabel("Sample Content")
    card.addWidget(lbl)
    assert card.layout_content.count() >= 2  # Header + label


def test_cyber_slider(qapp):
    callback_values = []
    slider = CyberSlider(
        label="Master Volume",
        min_val=0,
        max_val=100,
        initial_val=50,
        unit="%",
        on_change=lambda v: callback_values.append(v),
    )
    assert slider.value() == 50
    assert "50 %" in slider.lbl_val.text()

    slider.setValue(75)
    assert slider.value() == 75
    assert "75 %" in slider.lbl_val.text()
    assert 75 in callback_values


def test_cyber_toggle(qapp):
    toggled_states = []
    toggle = CyberToggle(
        "Enable Head Bop",
        checked=False,
        on_toggled=lambda st: toggled_states.append(st),
    )
    assert not toggle.isChecked()
    toggle.setChecked(True)
    assert len(toggled_states) == 1
    assert toggled_states[0] is True


def test_cyber_line_edit(qapp):
    edit = CyberLineEdit(placeholder="Enter Room Code", monospace=True)
    assert edit.placeholderText() == "Enter Room Code"
    assert "monospace" in edit.styleSheet().lower() or "consolas" in edit.styleSheet().lower()
