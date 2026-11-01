"""Shared Qt stylesheet used by Talia panels and dialogs."""

SHARED_PANEL_STYLE = """

    QWidget {

        background-color: #18181b;

        color: #f4f4f5;

        font-family: 'Segoe UI', Arial, sans-serif;

    }

    QScrollArea {

        border: none;

        background-color: transparent;

    }

    QScrollBar:vertical {

        border: none;

        background: #18181b;

        width: 6px;

        margin: 0px;

    }

    QScrollBar::handle:vertical {

        background: #3f3f46;

        min-height: 24px;

        border-radius: 3px;

    }

    QScrollBar::handle:vertical:hover {

        background: #52525b;

    }

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {

        height: 0px;

    }

    QPushButton {

        background-color: #27272a;

        border: 1px solid #3f3f46;

        color: #f4f4f5;

        border-radius: 4px;

        padding: 6px 12px;

        font-weight: 500;

        font-size: 11px;

    }

    QPushButton:hover {

        background-color: #3f3f46;

        border-color: #52525b;

        color: #ffffff;

    }

    QPushButton:pressed {

        background-color: #202024;

    }

    QPushButton:disabled {

        background-color: #202024;

        border-color: #27272a;

        color: #52525b;

    }

    QPushButton#btnPrimary {

        background-color: #2563eb;

        border: 1px solid #3b82f6;

        color: #ffffff;

    }

    QPushButton#btnPrimary:hover {

        background-color: #1d4ed8;

    }

    QPushButton#btnExitApp {

        background-color: #27272a;

        color: #f87171;

        border: 1px solid #451a1a;

        border-radius: 4px;

        padding: 7px;

        font-size: 11px;

        font-weight: 500;

    }

    QPushButton#btnExitApp:hover {

        background-color: #7f1d1d;

        color: #ffffff;

        border-color: #b91c1c;

    }

    QComboBox {

        background-color: #202024;

        border: 1px solid #3f3f46;

        border-radius: 4px;

        color: #f4f4f5;

        padding: 5px 10px;

        font-size: 11px;

    }

    QComboBox:hover {

        border-color: #3b82f6;

    }

    QComboBox QAbstractItemView {

        background-color: #202024;

        border: 1px solid #3f3f46;

        color: #f4f4f5;

        selection-background-color: #3b82f6;

        selection-color: #ffffff;

    }

    QListWidget {

        background-color: #202024;

        border: 1px solid #3f3f46;

        border-radius: 4px;

        color: #e4e4e7;

        font-family: 'Segoe UI', Arial, sans-serif;

        font-size: 11px;

        padding: 4px;

    }

    QListWidget::item {

        padding: 5px 8px;

        border-radius: 3px;

        border-bottom: 1px solid #27272a;

    }

    QListWidget::item:hover {

        background-color: #27272a;

        color: #ffffff;

    }

    QListWidget::item:selected {

        background-color: #2e3547;

        color: #ffffff;

        border-left: 3px solid #3b82f6;

    }

    QSlider::groove:horizontal {

        height: 4px;

        background: #3f3f46;

        border-radius: 2px;

    }

    QSlider::sub-page:horizontal {

        background: #3b82f6;

        border-radius: 2px;

    }

    QSlider::handle:horizontal {

        background: #ffffff;

        border: 1px solid #71717a;

        width: 14px;

        height: 14px;

        margin-top: -5px;

        margin-bottom: -5px;

        border-radius: 7px;

    }

    QSlider::handle:horizontal:hover {

        background: #ffffff;

        border: 1px solid #3b82f6;

    }

    QCheckBox {

        spacing: 8px;

        color: #d4d4d8;

        font-size: 11px;

    }

    QCheckBox::indicator {

        width: 14px;

        height: 14px;

        border: 1px solid #3f3f46;

        border-radius: 3px;

        background: #202024;

    }

    QCheckBox::indicator:checked {

        background: #3b82f6;

        border: 1px solid #3b82f6;

    }

    QCheckBox::indicator:hover {

        border-color: #3b82f6;

    }

    QLabel {

        font-size: 11px;

    }

"""
