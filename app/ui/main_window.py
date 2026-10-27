"""Main window: menu bar, status bar, sidebar, chat view, dialogs."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from app.styles import global_stylesheet, palette


class MainWindow(QMainWindow):
    """Top-level window. Owns layout only; behaviour lives in the controller."""

    sidebar_toggled = Signal(bool)
    request_abort = Signal()
    export_requested = Signal()
    import_requested = Signal()

    def __init__(
        self,
        sidebar,
        chat_view,
        settings_dialog_factory,
        connect_dialog_factory,
        about_dialog_factory,
    ) -> None:
        super().__init__()
        self._sidebar = sidebar
        self._chat_view = chat_view
        self._settings_dialog_factory = settings_dialog_factory
        self._connect_dialog_factory = connect_dialog_factory
        self._about_dialog_factory = about_dialog_factory

        self.setWindowTitle("Qwen Desktop Chat")
        self.setMinimumSize(880, 560)
        self.resize(1280, 820)

        self._build_central()
        self._build_menu()
        self._build_status_bar()
        self.sidebar_toggled.connect(self._on_sidebar_toggle)
        self._sidebar.toggle_requested.connect(self.sidebar_toggled.emit)

    # --------------------------------------------------------------- building

    def _build_central(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setChildrenCollapsible(False)

        self._sidebar_wrapper = QWidget()
        sidebar_layout = QVBoxLayout(self._sidebar_wrapper)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        sidebar_layout.addWidget(self._sidebar)
        self._sidebar_wrapper.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        chat_wrapper = QWidget()
        chat_layout = QVBoxLayout(chat_wrapper)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)
        chat_layout.addWidget(self._chat_view)
        chat_wrapper.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._splitter.addWidget(self._sidebar_wrapper)
        self._splitter.addWidget(chat_wrapper)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([self._sidebar.preferred_width(), 1000])

        layout.addWidget(self._splitter, 1)
        self.setCentralWidget(central)

    def _build_menu(self) -> None:
        menubar = self.menuBar()
        if menubar is None:
            return

        file_menu = menubar.addMenu("&File")

        new_action = QAction("&New chat", self)
        new_action.setShortcut(QKeySequence("Ctrl+N"))
        new_action.triggered.connect(self._sidebar.new_chat_requested.emit)
        file_menu.addAction(new_action)

        file_menu.addSeparator()

        export_action = QAction("&Export history…", self)
        export_action.triggered.connect(self.export_requested.emit)
        file_menu.addAction(export_action)

        import_action = QAction("&Import history…", self)
        import_action.triggered.connect(self.import_requested.emit)
        file_menu.addAction(import_action)

        file_menu.addSeparator()

        clear_action = QAction("&Clear chat history…", self)
        clear_action.setShortcut(QKeySequence("Ctrl+Shift+Delete"))
        clear_action.triggered.connect(self._sidebar.clear_history_requested.emit)
        file_menu.addAction(clear_action)

        file_menu.addSeparator()

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        view_menu = menubar.addMenu("&View")
        toggle_sidebar = QAction("Toggle &sidebar", self)
        toggle_sidebar.setShortcut(QKeySequence("Ctrl+B"))
        toggle_sidebar.triggered.connect(
            lambda: self.sidebar_toggled.emit(not self._sidebar.is_collapsed())
        )
        view_menu.addAction(toggle_sidebar)

        tools_menu = menubar.addMenu("&Tools")
        connect_action = QAction("Connect Qwen &API…", self)
        connect_action.triggered.connect(self._sidebar.connect_requested.emit)
        tools_menu.addAction(connect_action)

        settings_action = QAction("&Settings…", self)
        settings_action.setShortcut(QKeySequence("Ctrl+,"))
        settings_action.triggered.connect(self._sidebar.settings_requested.emit)
        tools_menu.addAction(settings_action)

        help_menu = menubar.addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def _build_status_bar(self) -> None:
        status = QStatusBar()
        status.setSizeGripEnabled(False)
        self.setStatusBar(status)
        status.showMessage("Ready", 0)

    # ------------------------------------------------------------------ status

    def set_status(self, message: str, timeout: int = 0) -> None:
        bar = self.statusBar()
        if bar is not None:
            bar.showMessage(message, timeout)

    def show_status_error(self, message: str) -> None:
        self.set_status(f"Error: {message}", 8000)

    def apply_theme(self, settings) -> None:
        """Re-apply the application stylesheet for the current theme."""
        from PySide6.QtWidgets import QApplication

        stylesheet = global_stylesheet(
            palette(settings.theme), settings.chat_font_scale
        )
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(stylesheet)

    # ------------------------------------------------------------------ wiring

    def _on_sidebar_toggle(self, collapsed: bool) -> None:
        self._sidebar.set_collapsed(collapsed)
        width = 0 if collapsed else self._sidebar.preferred_width()
        self._sidebar_wrapper.setVisible(not collapsed)
        if not collapsed:
            self._sidebar_wrapper.setFixedWidth(width)
            sizes = self._splitter.sizes()
            total = sum(sizes) or 1
            self._splitter.setSizes([width, max(1, total - width)])

    def toggle_sidebar(self) -> None:
        self.sidebar_toggled.emit(not self._sidebar.is_collapsed())

    # ----------------------------------------------------------------- dialogs

    def show_settings(self) -> None:
        self._sidebar.settings_requested.emit()

    def show_connect_api(self) -> None:
        self._sidebar.connect_requested.emit()

    def show_about(self) -> None:
        dialog = self._about_dialog_factory()
        dialog.exec()

    def active_conversation_id(self) -> Optional[str]:
        return self._chat_view.active_conversation_id()

    def settings_dialog_factory(self):
        return self._settings_dialog_factory

    def connect_dialog_factory(self):
        return self._connect_dialog_factory

    # ------------------------------------------------------------------- close

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt naming
        """Abort any in-flight request before the window disappears."""
        self.request_abort.emit()
        super().closeEvent(event)
