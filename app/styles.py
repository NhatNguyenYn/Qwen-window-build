"""Dark and light application palettes and global stylesheet.

Kept small on purpose. The app should look clean on common laptop screens
without heavy custom painting.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QApplication


DARK_PALETTE = {
    "background": QColor("#18181b"),
    "surface": QColor("#27272a"),
    "surface_highlight": QColor("#323235"),
    "on_background": QColor("#e4e4e7"),
    "on_surface": QColor("#d4d4d8"),
    "primary": QColor("#4ade80"),
    "primary_hover": QColor("#34d399"),
    "secondary": QColor("#64748b"),
    "border": QColor("#3f3f46"),
    "muted": QColor("#71717a"),
    "error": QColor("#f87171"),
    "thinking": QColor("#7dd3fc"),
    "code_bg": QColor("#111113"),
    "code_text": QColor("#d4d4d8"),
    "user_bubble": QColor("#2563eb"),
    "assistant_bubble": QColor("#27272a"),
    "input_bg": QColor("#1f1f23"),
    "sidebar_bg": QColor("#1a1a1c"),
    "sidebar_item_hover": QColor("#2a2a2e"),
    "sidebar_item_selected": QColor("#3a3a3f"),
}


LIGHT_PALETTE = {
    "background": QColor("#ffffff"),
    "surface": QColor("#f4f4f5"),
    "surface_highlight": QColor("#eaeaea"),
    "on_background": QColor("#18181b"),
    "on_surface": QColor("#27272a"),
    "primary": QColor("#16a34a"),
    "primary_hover": QColor("#15803d"),
    "secondary": QColor("#64748b"),
    "border": QColor("#d4d4d8"),
    "muted": QColor("#71717a"),
    "error": QColor("#dc2626"),
    "thinking": QColor("#0ea5e9"),
    "code_bg": QColor("#f7f7f8"),
    "code_text": QColor("#1f2937"),
    "user_bubble": QColor("#2563eb"),
    "assistant_bubble": QColor("#f4f4f5"),
    "input_bg": QColor("#ffffff"),
    "sidebar_bg": QColor("#fafafa"),
    "sidebar_item_hover": QColor("#eaeaea"),
    "sidebar_item_selected": QColor("#d4d4d8"),
}


def palette(theme: str) -> dict:
    if theme == "light":
        return LIGHT_PALETTE
    return DARK_PALETTE


def global_stylesheet(p: dict, font_scale: float = 1.0) -> str:
    fs_base = 13 * font_scale
    fs_sm = max(11, int(fs_base - 1.5))
    fs_md = int(fs_base)

    return f"""
    QWidget {{
        background-color: {p['background'].name()};
        color: {p['on_background'].name()};
        font-family: "Segoe UI", "Microsoft YaHei", "Noto Sans", "PingFang SC", system-ui, sans-serif;
        font-size: {fs_base}px;
    }}
    QMainWindow {{
        background-color: {p['background'].name()};
    }}
    QMenuBar {{
        background-color: {p['surface'].name()};
        color: {p['on_surface'].name()};
        border-bottom: 1px solid {p['border'].name()};
        font-size: {fs_sm}px;
        padding: 4px 8px;
        spacing: 6px;
    }}
    QMenuBar::item:selected {{
        background-color: {p['sidebar_item_hover'].name()};
    }}
    QMenu {{
        background-color: {p['surface'].name()};
        color: {p['on_surface'].name()};
        border: 1px solid {p['border'].name()};
        border-radius: 6px;
        padding: 6px 8px;
        font-size: {fs_sm}px;
    }}
    QMenu::item:selected {{
        background-color: {p['primary'].name()};
        color: #ffffff;
    }}
    QMenu::separator {{
        height: 1px;
        background: {p['border'].name()};
        margin: 4px 6px;
    }}
    QToolBar {{
        background: transparent;
        border: none;
        spacing: 6px;
        padding: 4px 6px;
    }}
    QStatusBar {{
        background-color: {p['surface'].name()};
        color: {p['on_surface'].name()};
        border-top: 1px solid {p['border'].name()};
        font-size: {fs_sm}px;
        padding: 3px 8px;
    }}
    QLineEdit, QTextEdit, QPlainTextEdit {{
        background-color: {p['input_bg'].name()};
        color: {p['on_background'].name()};
        border: 1px solid {p['border'].name()};
        border-radius: 8px;
        padding: 8px 10px;
        selection-background-color: {p['primary'].name()};
        selection-color: #ffffff;
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
        border: 1px solid {p['primary'].name()};
    }}
    QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover {{
        border: 1px solid {p['secondary'].name()};
    }}
    QPushButton {{
        background-color: {p['surface'].name()};
        color: {p['on_surface'].name()};
        border: 1px solid {p['border'].name()};
        border-radius: 8px;
        padding: 8px 14px;
        font-size: {fs_md}px;
        min-height: 34px;
    }}
    QPushButton:hover:!disabled {{
        background-color: {p['surface_highlight'].name()};
        border-color: {p['primary'].name()};
        color: {p['primary'].name()};
    }}
    QPushButton:pressed {{
        background-color: {p['secondary'].name()};
    }}
    QPushButton:disabled {{
        color: {p['muted'].name()};
        border-color: {p['border'].name()};
    }}
    QPushButton[variant="primary"] {{
        background-color: {p['primary'].name()};
        color: #ffffff;
        border-color: {p['primary'].name()};
        font-weight: 600;
    }}
    QPushButton[variant="primary"]:hover:!disabled {{
        background-color: {p['primary_hover'].name()};
        border-color: {p['primary_hover'].name()};
    }}
    QPushButton[variant="ghost"] {{
        background: transparent;
        border: none;
        color: {p['on_surface'].name()};
        min-height: 28px;
        padding: 6px 10px;
    }}
    QPushButton[variant="ghost"]:hover:!disabled {{
        background-color: {p['surface_highlight'].name()};
        color: {p['primary'].name()};
    }}
    QPushButton[variant="icon"] {{
        min-width: 32px;
        min-height: 32px;
        padding: 4px;
        background: transparent;
        border: none;
        border-radius: 6px;
        color: {p['on_surface'].name()};
    }}
    QPushButton[variant="icon"]:hover:!disabled {{
        background-color: {p['surface_highlight'].name()};
        color: {p['primary'].name()};
    }}
    QPushButton[variant="icon"]:pressed {{
        background-color: {p['secondary'].name()};
    }}
    QComboBox {{
        background-color: {p['input_bg'].name()};
        color: {p['on_background'].name()};
        border: 1px solid {p['border'].name()};
        border-radius: 8px;
        padding: 7px 10px;
        font-size: {fs_md}px;
        min-height: 34px;
    }}
    QComboBox:focus {{
        border: 1px solid {p['primary'].name()};
    }}
    QComboBox:hover {{
        border-color: {p['secondary'].name()};
    }}
    QComboBox::drop-down {{
        border: none;
        padding-right: 6px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {p['surface'].name()};
        color: {p['on_surface'].name()};
        border: 1px solid {p['border'].name()};
        border-radius: 6px;
        selection-background-color: {p['primary'].name()};
        selection-color: #ffffff;
        padding: 4px;
    }}
    QPlainTextEdit[role="input"] {{
        background-color: {p['input_bg'].name()};
        color: {p['on_background'].name()};
        border: 1px solid {p['border'].name()};
        border-radius: 10px;
        padding: 10px 12px;
        font-size: {fs_md}px;
        line-height: 1.5;
    }}
    QPlainTextEdit[role="input"]:focus {{
        border: 1px solid {p['primary'].name()};
    }}
    QScrollBar:vertical {{
        background-color: {p['background'].name()};
        width: 10px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background-color: {p['border'].name()};
        border-radius: 5px;
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {p['secondary'].name()};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar:horizontal {{
        background-color: {p['background'].name()};
        height: 10px;
        margin: 0px;
    }}
    QScrollBar::handle:horizontal {{
        background-color: {p['border'].name()};
        border-radius: 5px;
        min-width: 24px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background-color: {p['secondary'].name()};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}
    QScrollArea {{
        background: transparent;
        border: none;
    }}
    QTextBrowser {{
        background: transparent;
        border: none;
        font-size: {fs_md}px;
        line-height: 1.6;
        padding: 0px;
    }}
    QSplitter::handle {{
        background-color: {p['border'].name()};
    }}
    QSplitter::handle:horizontal {{
        width: 1px;
    }}
    QLabel {{
        color: {p['on_surface'].name()};
    }}
    QGroupBox {{
        border: 1px solid {p['border'].name()};
        border-radius: 8px;
        margin-top: 12px;
        padding-top: 14px;
        color: {p['on_surface'].name()};
        font-size: {fs_sm}px;
        font-weight: 600;
    }}
    QTabWidget::pane {{
        border: 1px solid {p['border'].name()};
        border-radius: 8px;
        background-color: {p['surface'].name()};
    }}
    QTabBar::tab {{
        background: transparent;
        color: {p['on_surface'].name()};
        padding: 8px 14px;
        border-radius: 6px 6px 0px 0px;
        margin-right: 2px;
        font-size: {fs_sm}px;
    }}
    QTabBar::tab:selected {{
        background-color: {p['background'].name()};
        color: {p['primary'].name()};
        border-bottom: 2px solid {p['primary'].name()};
    }}
    QTabBar::tab:hover:!selected {{
        background-color: {p['surface_highlight'].name()};
    }}
    QToolTip {{
        background-color: {p['surface'].name()};
        color: {p['on_surface'].name()};
        border: 1px solid {p['border'].name()};
        border-radius: 6px;
        padding: 6px 10px;
        font-size: {fs_sm}px;
    }}
    QProgressBar {{
        background-color: {p['surface'].name()};
        border: 1px solid {p['border'].name()};
        border-radius: 4px;
        text-align: center;
        height: 4px;
    }}
    QProgressBar::chunk {{
        background-color: {p['primary'].name()};
        border-radius: 3px;
    }}
    """
