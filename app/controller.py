"""Application controller: wires the window, the service and the worker pool.

This is a ``QObject`` that lives on the main thread. Background workers emit
signals, and because the controller is a main-thread ``QObject``, those
connections are delivered as queued calls on the main thread. All widget and
database access therefore happens on the main thread, and workers only do
network I/O.

Keeping this logic out of ``main.py`` also means the entry point stays a thin
bootstrap and this behaviour is testable without a full GUI session.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QObject, QThreadPool, QTimer, Slot
from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox

from app.api.client import QwenApiClient
from app.api.errors import ApiError, CancelledError
from app.config.settings import AppSettings, save_settings
from app.database.chat_repository import ChatRepository
from app.database.migration import (
    UnexpectedPayloadError,
    export_conversations,
    import_conversations,
)
from app.security.credentials import CredentialsManager
from app.services.conversation import ConversationService, SendHandle
from app.services.state import RequestState  # noqa: F401 - used for state names
from app.ui.chat_view import ChatView
from app.ui.main_window import MainWindow
from app.ui.sidebar import Sidebar
from app.workers.infer import InferWorker, build_worker

# Streaming arrives token by token; repainting on every token wastes CPU and
# makes long answers flicker. Text is buffered and flushed on this interval.
STREAM_FLUSH_MS = 70


class ChatController(QObject):
    """Owns all interaction between the UI, the service layer and workers."""

    def __init__(
        self,
        window: MainWindow,
        sidebar: Sidebar,
        chat_view: ChatView,
        service: ConversationService,
        settings: AppSettings,
        credentials: CredentialsManager,
        repository: ChatRepository,
        *,
        settings_dialog_factory,
        connect_dialog_factory,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._window = window
        self._sidebar = sidebar
        self._chat = chat_view
        self._service = service
        self._settings = settings
        self._credentials = credentials
        self._repository = repository
        self._settings_dialog_factory = settings_dialog_factory
        self._connect_dialog_factory = connect_dialog_factory

        self._service.max_context_messages = int(settings.max_context_messages)
        self._client: QwenApiClient = self._make_client()
        self._worker: Optional[InferWorker] = None
        self._handle: Optional[SendHandle] = None
        self._stream_buffer: List[str] = []
        self._stream_written = ""

        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(STREAM_FLUSH_MS)
        self._flush_timer.timeout.connect(self._flush_stream)

        self._wire()

    # ------------------------------------------------------------- client/key

    def _make_client(self) -> QwenApiClient:
        return QwenApiClient(
            self._settings.base_url,
            self._credentials.get_key() or "",
            default_timeout_seconds=self._settings.request_timeout_seconds,
        )

    def reload_credentials_and_settings(self) -> None:
        """Rebuild the API client after the key or endpoint changed."""
        self._client = self._make_client()
        self.refresh_connection_status()

    def refresh_connection_status(self) -> None:
        if self._client.has_key():
            self._sidebar.set_status("connected", "Connected")
        else:
            self._sidebar.set_status("disconnected", "No API key")

    # ------------------------------------------------------------------ wiring

    def _wire(self) -> None:
        self._sidebar.conversation_selected.connect(self.open_conversation)
        self._sidebar.new_chat_requested.connect(self.new_chat)
        self._sidebar.search_requested.connect(self.search_conversations)
        self._sidebar.rename_requested.connect(self.rename_conversation)
        self._sidebar.delete_requested.connect(self.delete_conversation)
        self._sidebar.clear_history_requested.connect(self.clear_history)
        self._sidebar.connect_requested.connect(self.open_connect_dialog)
        self._sidebar.settings_requested.connect(self.open_settings_dialog)

        self._chat.send_requested.connect(self.send_message)
        self._chat.stop_requested.connect(self.stop_request)
        self._chat.retry_requested.connect(self.retry_last_request)

        self._window.export_requested.connect(self.export_history)
        self._window.import_requested.connect(self.import_history)
        self._window.request_abort.connect(self.stop_request)

    def _apply_theme(self) -> None:
        """Re-apply stylesheet and markdown palette for the current theme."""
        from PySide6.QtWidgets import QApplication

        from app.styles import global_stylesheet, palette
        from app.ui.markdown_widget import set_render_theme

        set_render_theme(self._settings.theme)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(
                global_stylesheet(
                    palette(self._settings.theme), self._settings.chat_font_scale
                )
            )

    def start(self) -> None:
        """Populate the sidebar and open the most recent conversation."""
        self._apply_theme()
        self.refresh_connection_status()
        self.refresh_sidebar()
        conversations = self._service.list_recent(limit=50)
        if conversations:
            self.open_conversation(conversations[0]["id"])
        else:
            self._chat.show_welcome()

    # ------------------------------------------------------------- sidebar/UI

    def refresh_sidebar(self) -> None:
        self._sidebar.set_conversations(self._service.list_recent(limit=200))

    def open_conversation(self, conversation_id: str) -> None:
        if conversation_id == "__new__":
            self.new_chat()
            return
        if self._is_busy():
            return
        conversation = self._service.get_conversation(conversation_id)
        if conversation is None:
            self._window.set_status("Conversation not found.", 3000)
            return
        self._service.set_active(conversation_id)
        self._chat.set_conversation(
            conversation_id, conversation["title"], self._settings.model
        )
        self._chat.clear()
        messages = self._service.messages(conversation_id)
        rendered_any = False
        for message in messages:
            content = (message.get("content") or "").strip()
            role = message.get("role")
            if not content:
                continue
            if role == "user":
                self._chat.add_user_message(content)
                rendered_any = True
            elif role == "assistant":
                self._chat.add_assistant_message(content)
                rendered_any = True
        if not rendered_any:
            self._chat.show_welcome()
        self._sidebar.select_conversation(conversation_id)

    def new_chat(self) -> None:
        if self._is_busy():
            return
        conversation_id = self._service.new_conversation(
            system_prompt=self._settings.system_prompt
        )
        self.refresh_sidebar()
        self._chat.set_conversation(conversation_id, "New conversation", self._settings.model)
        self._chat.show_welcome()
        self._sidebar.select_conversation(conversation_id)
        self._chat.focus_input()

    def search_conversations(self, query: str) -> None:
        results = self._service.search(query, limit=200)
        self._sidebar.set_conversations(results)
        if query.strip():
            self._window.set_status(
                f"{len(results)} conversation(s) match “{query.strip()}”.", 4000
            )

    def rename_conversation(self, conversation_id: str) -> None:
        conversation = self._service.get_conversation(conversation_id)
        if conversation is None:
            return
        from PySide6.QtWidgets import QInputDialog

        new_title, accepted = QInputDialog.getText(
            self._window, "Rename conversation", "New title:", text=conversation["title"]
        )
        if not accepted:
            return
        if not self._service.rename(conversation_id, new_title):
            QMessageBox.warning(
                self._window, "Rename failed", "The title could not be saved."
            )
            return
        self.refresh_sidebar()
        if self._service.active_id == conversation_id:
            self._chat.set_conversation(
                conversation_id, new_title.strip() or conversation["title"], self._settings.model
            )

    def delete_conversation(self, conversation_id: str) -> None:
        conversation = self._service.get_conversation(conversation_id)
        if conversation is None:
            return
        if self._is_busy():
            return
        answer = QMessageBox.question(
            self._window,
            "Delete conversation",
            f"Delete “{conversation['title']}” and all of its messages?\n"
            "This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._service.delete(conversation_id)
        self.refresh_sidebar()
        if self._service.active_id is None:
            self._chat.clear()
            self._chat.show_welcome()
        self._window.set_status("Conversation deleted.", 2000)

    def clear_history(self) -> None:
        if self._is_busy():
            return
        answer = QMessageBox.question(
            self._window,
            "Clear all history",
            "Delete all conversations and messages?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        removed = self._service.delete_all()
        self.refresh_sidebar()
        self._chat.clear()
        self._chat.show_welcome()
        self._window.set_status(f"Deleted {removed} conversation(s).", 3000)

    # ------------------------------------------------------------ send/stream

    def _is_busy(self) -> bool:
        return self._worker is not None

    def _require_key(self) -> bool:
        if self._client.has_key():
            return True
        self._chat.add_error_block(
            "No API key configured",
            "Open “Connect Qwen API” in the sidebar, paste your key, then press "
            "“Save & Connect”. Your key is stored in the operating system "
            "credential store, never in the chat database.",
            show_retry=False,
        )
        self._window.set_status("No API key configured.", 4000)
        return False

    @Slot(str)
    def send_message(self, text: str) -> None:
        if self._is_busy():
            return
        if not self._require_key():
            return

        if self._service.active_id is None:
            self.new_chat()
        active = self._service.active_id
        if active is None:
            return

        try:
            handle = self._service.send_message(
                active,
                text,
                model=self._settings.model,
                temperature=self._settings.temperature,
                max_tokens=self._settings.max_tokens,
                request_timeout_seconds=self._settings.request_timeout_seconds,
                system_prompt_override=self._settings.system_prompt,
            )
        except ValueError as exc:
            self._chat.add_error_block("Cannot send", str(exc), show_retry=False)
            return

        self._chat.add_user_message(text)
        self.refresh_sidebar()
        self._start_request(handle)

    @Slot()
    def retry_last_request(self) -> None:
        if self._is_busy():
            return
        if not self._require_key():
            return
        active = self._service.active_id
        if active is None:
            return
        handle = self._service.retry_last_message(
            active,
            model=self._settings.model,
            temperature=self._settings.temperature,
            max_tokens=self._settings.max_tokens,
            request_timeout_seconds=self._settings.request_timeout_seconds,
            system_prompt_override=self._settings.system_prompt,
        )
        if handle is None:
            self._chat.add_error_block(
                "Nothing to retry",
                "There is no user message in this conversation yet.",
                show_retry=False,
            )
            return
        self._start_request(handle)

    def _start_request(self, handle: SendHandle) -> None:
        self._handle = handle
        self._stream_buffer = []
        self._stream_written = ""
        self._chat.set_busy(True)
        self._service.mark_streaming(handle)
        self._chat.begin_assistant_message()

        worker = build_worker(
            self._client,
            handle.request,
            handle.abort_token,
            request_id=handle.request_id,
            conversation_id=handle.conversation_id,
        )
        worker.signals.chunk.connect(self._on_chunk)
        worker.signals.done.connect(self._on_done)
        worker.signals.failed.connect(self._on_failed)
        worker.signals.cancelled.connect(self._on_cancelled)
        self._worker = worker
        self._flush_timer.start()
        QThreadPool.globalInstance().start(worker)

    @Slot(str)
    def _on_chunk(self, delta: str) -> None:
        if self._handle is None or self._worker is None:
            return
        if self._worker.request_id != self._handle.request_id:
            # A stale request must never write into the current conversation.
            return
        self._stream_buffer.append(delta)

    @Slot()
    def _flush_stream(self) -> None:
        if not self._stream_buffer:
            return
        self._stream_written += "".join(self._stream_buffer)
        self._stream_buffer = []
        self._chat.append_streaming(self._stream_written)

    def _collect_stream(self) -> str:
        if self._stream_buffer:
            self._stream_written += "".join(self._stream_buffer)
            self._stream_buffer = []
        return self._stream_written

    def _finalize(self, state: str, *, note: str = "") -> None:
        text = self._collect_stream()
        self._flush_timer.stop()
        handle = self._handle
        self._worker = None
        self._handle = None
        if handle is None:
            self._chat.set_busy(False)
            return

        if text.strip():
            self._service.store_assistant_text(handle.assistant_message_id, text)
        self._service.finish_request(handle, state)

        self._chat.end_streaming(final_text=text, incomplete=bool(note), note=note)
        self._chat.set_busy(False)
        self.refresh_sidebar()

        if state == RequestState.FAILED:
            self._window.set_status("Request failed.", 4000)
        elif state == RequestState.CANCELLED:
            self._window.set_status("Response stopped.", 3000)
        else:
            self._window.set_status("Answer complete.", 2000)

    @Slot(str)
    def _on_done(self, _final_text: str) -> None:
        self._finalize(RequestState.COMPLETED)

    @Slot(object)
    def _on_failed(self, error: object) -> None:
        text = self._collect_stream()
        partial = text.strip()
        message = (
            error.message
            if isinstance(error, ApiError)
            else str(error) or "Unexpected error."
        )
        self._finalize(RequestState.FAILED)
        detail = message
        if partial:
            detail = (
                f"{message}\n\nPartial answer was kept in this conversation."
            )
        self._chat.add_error_block("Request failed", detail)
        self._window.show_status_error(message)

    @Slot()
    def _on_cancelled(self) -> None:
        text = self._collect_stream()
        self._finalize(
            RequestState.CANCELLED,
            note="Stopped before the answer finished." if text.strip() else "",
        )

    @Slot()
    def stop_request(self) -> None:
        """Cancel the in-flight request at the network layer."""
        if self._worker is not None:
            self._worker.request_abort()
        self._service.cancel_pending()
        self._window.set_status("Stopping…", 1500)

    # -------------------------------------------------------- dialogs/settings

    def open_connect_dialog(self) -> None:
        if self._is_busy():
            self._window.set_status("Stop the current answer first.", 3000)
            return
        dialog = self._connect_dialog_factory()
        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            save_settings(self._settings)
            self.reload_credentials_and_settings()
            self.refresh_sidebar()
            self._window.set_status("Connected to Qwen.", 3000)
        else:
            self.refresh_connection_status()

    def open_settings_dialog(self) -> None:
        if self._is_busy():
            self._window.set_status("Stop the current answer first.", 3000)
            return
        dialog = self._settings_dialog_factory()
        if hasattr(dialog, "export_requested"):
            dialog.export_requested.connect(self.export_history)
            dialog.import_requested.connect(self.import_history)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            save_settings(self._settings)
            self._apply_theme()
            self.reload_credentials_and_settings()
            self._chat.set_conversation(
                self._service.active_id or "",
                self._chat.conversation_title(),
                self._settings.model,
            )
            self._window.set_status("Settings saved.", 2500)

    # ------------------------------------------------------- export / import

    def export_history(self) -> None:
        if self._is_busy():
            return
        target, _ = QFileDialog.getSaveFileName(
            self._window,
            "Export chat history",
            "qwen-chat-history.json",
            "JSON files (*.json)",
        )
        if not target:
            return
        try:
            payload = export_conversations(self._repository.db_path)
            Path(target).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            QMessageBox.critical(self._window, "Export failed", str(exc))
            return
        count = len(payload.get("conversations", []))
        self._window.set_status(f"Exported {count} conversation(s).", 4000)

    def import_history(self) -> None:
        if self._is_busy():
            return
        source, _ = QFileDialog.getOpenFileName(
            self._window,
            "Import chat history",
            "",
            "JSON files (*.json)",
        )
        if not source:
            return
        path = Path(source)
        if path.stat().st_size > 64 * 1024 * 1024:
            QMessageBox.warning(
                self._window,
                "Import refused",
                "That file is larger than 64 MB and will not be imported.",
            )
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self._window, "Import failed", f"Not valid JSON.\n\n{exc}")
            return
        try:
            imported = import_conversations(self._repository.db_path, payload)
        except UnexpectedPayloadError as exc:
            QMessageBox.warning(
                self._window,
                "Import refused",
                f"That file is not a Qwen Desktop Chat export.\n\n{exc}",
            )
            return
        self.refresh_sidebar()
        self._window.set_status(f"Imported {imported} conversation(s).", 4000)

    # ------------------------------------------------------------------ close

    def shutdown(self) -> None:
        """Abort in-flight work so the window can close promptly."""
        self._flush_timer.stop()
        self._service.on_close()
        worker = self._worker
        if worker is not None:
            worker.request_abort()
        pool = QThreadPool.globalInstance()
        pool.waitForDone(3000)
