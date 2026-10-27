"""Qwen Desktop Chat — application entry point.

This file is deliberately only a bootstrap: it prepares the environment, builds
the object graph, starts the controller, and reports any fatal startup error in
a message box instead of failing silently. All behaviour lives in ``app/``.

Run it with:

    venv\\Scripts\\pythonw.exe main.py        (no console window)
    venv\\Scripts\\python.exe  main.py        (with console output)
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def _report_fatal(error: BaseException) -> None:
    """Show startup failures instead of dying invisibly."""
    detail = "".join(
        traceback.format_exception(type(error), error, error.__traceback__)
    )
    sys.stderr.write(detail)
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        if QApplication.instance() is None:
            QApplication(sys.argv)
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle("Qwen Desktop Chat — startup failed")
        box.setText(
            "The application could not start.\n\n"
            f"{type(error).__name__}: {error}\n\n"
            "The full traceback was written to the console."
        )
        box.setDetailedText(detail)
        box.exec()
    except Exception:
        # If even the message box cannot be shown, the stderr trace stands.
        pass


def main() -> int:
    """Build the application and run the Qt event loop."""
    from app.ui.app import App

    app = App(sys.argv)
    app.setApplicationName("Qwen Desktop Chat")
    app.setOrganizationName("QwenDesktopChat")

    from app.config.settings import load_settings
    from app.styles import global_stylesheet, palette
    from app.ui.markdown_widget import set_render_theme

    settings = load_settings()
    set_render_theme(settings.theme)
    app.setStyleSheet(
        global_stylesheet(palette(settings.theme), settings.chat_font_scale)
    )

    from app.api.client import QwenApiClient
    from app.controller import ChatController
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

    repository = ChatRepository()
    credentials = CredentialsManager()
    service = ConversationService(
        repository,
        QwenApiClient(
            settings.base_url,
            credentials.get_key() or "",
            default_timeout_seconds=settings.request_timeout_seconds,
        ),
        max_context_messages=settings.max_context_messages,
    )

    sidebar = Sidebar()
    chat_view = ChatView(markdown_factory=MarkdownWidget)

    def client_factory(api_key: str, base_url: str) -> QwenApiClient:
        return QwenApiClient(
            base_url,
            api_key,
            default_timeout_seconds=settings.request_timeout_seconds,
        )

    def settings_dialog_factory() -> SettingsDialog:
        return SettingsDialog(settings, service, repository, credentials)

    def connect_dialog_factory() -> ConnectApiDialog:
        return ConnectApiDialog(settings, credentials, client_factory)

    def about_dialog_factory() -> AboutDialog:
        return AboutDialog()

    window = MainWindow(
        sidebar=sidebar,
        chat_view=chat_view,
        settings_dialog_factory=settings_dialog_factory,
        connect_dialog_factory=connect_dialog_factory,
        about_dialog_factory=about_dialog_factory,
    )

    controller = ChatController(
        window,
        sidebar,
        chat_view,
        service,
        settings,
        credentials,
        repository,
        settings_dialog_factory=settings_dialog_factory,
        connect_dialog_factory=connect_dialog_factory,
    )
    app.aboutToQuit.connect(controller.shutdown)

    controller.start()
    window.show()

    if not credentials.has_stored_key():
        window.set_status(
            "No API key yet — use “Connect Qwen API” in the sidebar to start.",
            0,
        )

    return app.exec()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 - last-resort visibility
        _report_fatal(exc)
        raise SystemExit(1)
