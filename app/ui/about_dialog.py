"""About dialog for Qwen Desktop Chat."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QDialogButtonBox,
    QGroupBox,
)


class AboutDialog(QDialog):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("About Qwen Desktop Chat")
        self.setModal(True)
        self.setFixedSize(420, 280)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        box = QGroupBox()
        box.setLayout(QVBoxLayout())
        box.layout().setContentsMargins(10, 10, 10, 10)

        title = QLabel("Qwen Desktop Chat")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setStyleSheet("color: #e4e4e7;")
        box.layout().addWidget(title)

        subtitle = QLabel("A modern desktop client for Qwen models.")
        subtitle.setStyleSheet("color: #a1a1aa; font-size: 12px;")
        box.layout().addWidget(subtitle)

        line = QLabel("—")
        line.setStyleSheet("color: #3f3f46;")
        box.layout().addWidget(line)

        info = QLabel(
            "Built with Python and PySide6.\n"
            "Uses an OpenAI-compatible endpoint you configure.\n\n"
            "Your API key stays on your device.\n"
            "No telemetry is collected."
        )
        info.setStyleSheet("color: #a1a1aa; font-size: 12px;")
        info.setAlignment(Qt.AlignCenter)
        info.setWordWrap(True)
        box.layout().addWidget(info)

        layout.addWidget(box, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
