"""Smoke tests: every module imports, and the GUI can be constructed headless.

These catch the class of defect that previously shipped: modules that could not
be imported at all, and widgets that raised on construction because they
referenced names that did not exist.
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

APP_MODULES = [
    "app.api.client",
    "app.api.errors",
    "app.config.settings",
    "app.controller",
    "app.database.chat_repository",
    "app.database.db",
    "app.database.migration",
    "app.security.credentials",
    "app.security.secrets_backend",
    "app.services.conversation",
    "app.services.state",
    "app.styles",
    "app.ui.about_dialog",
    "app.ui.app",
    "app.ui.chat_view",
    "app.ui.connect_api_dialog",
    "app.ui.main_window",
    "app.ui.markdown_widget",
    "app.ui.settings_dialog",
    "app.ui.sidebar",
    "app.workers.infer",
]


class TestModuleImports(unittest.TestCase):
    def test_every_app_module_imports(self) -> None:
        for name in APP_MODULES:
            with self.subTest(module=name):
                importlib.import_module(name)

    def test_entry_point_module_imports(self) -> None:
        import main

        self.assertTrue(callable(main.main))


class TestGuiConstruction(unittest.TestCase):
    """Build the real widget tree on an offscreen Qt platform."""

    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _build(self):
        from app.api.client import QwenApiClient
        from app.config.settings import AppSettings
        from app.database.chat_repository import ChatRepository
        from app.security.credentials import CredentialsManager
        from app.services.conversation import ConversationService
        from app.ui.about_dialog import AboutDialog
        from app.ui.chat_view import ChatView
        from app.ui.connect_api_dialog import ConnectApiDialog
        from app.ui.main_window import MainWindow
        from app.ui.markdown_widget import MarkdownWidget
        from app.ui.settings_dialog import SettingsDialog
        from app.ui.sidebar import Sidebar
        from app.controller import ChatController

        settings = AppSettings()
        settings.base_url = "https://example.invalid/v1"
        repository = ChatRepository(Path(self._tmp.name) / "chat.db")
        credentials = CredentialsManager()
        service = ConversationService(
            repository,
            QwenApiClient(settings.base_url, "", default_timeout_seconds=5.0),
        )

        def connect_factory():
            return ConnectApiDialog(
                settings,
                credentials,
                lambda key, base: QwenApiClient(base, key, default_timeout_seconds=5.0),
            )

        def settings_factory():
            return SettingsDialog(settings, service, repository, credentials)

        sidebar = Sidebar()
        chat_view = ChatView(markdown_factory=MarkdownWidget)
        window = MainWindow(
            sidebar=sidebar,
            chat_view=chat_view,
            settings_dialog_factory=settings_factory,
            connect_dialog_factory=connect_factory,
            about_dialog_factory=AboutDialog,
        )
        controller = ChatController(
            window,
            sidebar,
            chat_view,
            service,
            settings,
            credentials,
            repository,
            settings_dialog_factory=settings_factory,
            connect_dialog_factory=connect_factory,
        )
        return window, sidebar, chat_view, controller, service

    def test_widget_tree_constructs(self) -> None:
        window, sidebar, chat_view, controller, service = self._build()
        self.assertEqual(window.windowTitle(), "Qwen Desktop Chat")
        self.assertIsNotNone(chat_view)
        self.assertIsNotNone(sidebar)

    def test_controller_start_populates_empty_state(self) -> None:
        window, sidebar, chat_view, controller, service = self._build()
        controller.start()
        # No conversations yet: the empty placeholder is shown.
        self.assertIsNone(service.active_id)

    def test_new_chat_creates_a_conversation(self) -> None:
        window, sidebar, chat_view, controller, service = self._build()
        controller.start()
        controller.new_chat()
        self.assertIsNotNone(service.active_id)
        self.assertEqual(len(service.list_recent()), 1)

    def test_refresh_sidebar_accepts_repository_rows(self) -> None:
        """Regression: the sidebar used to receive dataclasses and crash on .get()."""
        window, sidebar, chat_view, controller, service = self._build()
        service.new_conversation(title="Row test")
        controller.refresh_sidebar()
        self.assertEqual(sidebar._list.count(), 1)

    def test_settings_dialog_exposes_export_signals(self) -> None:
        from app.ui.settings_dialog import SettingsDialog

        self.assertTrue(hasattr(SettingsDialog, "export_requested"))
        self.assertTrue(hasattr(SettingsDialog, "import_requested"))


if __name__ == "__main__":
    unittest.main()
