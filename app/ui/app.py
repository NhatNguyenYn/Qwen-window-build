"""Application-level QApplication subclass used for once-only setup."""
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QApplication


class App(QApplication):
    """Top-level application for Qwen Desktop Chat."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._theme: Optional[str] = None

    def set_theme(self, theme: str) -> None:
        self._theme = theme
