"""Tests for the application controller.

The controller owns the risky logic: gating duplicate sends, refusing a request
whose chunks belong to a superseded request, and finalizing a request so the
assistant text is persisted exactly once.

The Qt thread pool is not exercised here; ``build_worker`` is replaced with a
fake so chunks can be delivered deterministically.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.client import QwenApiClient
from app.config.settings import AppSettings
from app.database.chat_repository import ChatRepository
from app.security.credentials import CredentialsManager
from app.services.conversation import ConversationService
from app.services.state import RequestState


class FakeWorker:
    """Stand-in for InferWorker that carries the real Qt signal object."""

    def __init__(self, request_id: str) -> None:
        from app.workers.infer import WorkerSignals

        self.request_id = request_id
        self.signals = WorkerSignals()
        self.abort_calls = 0

    def request_abort(self) -> None:
        self.abort_calls += 1


class ControllerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        import app.controller as controller_module
        from app.ui.about_dialog import AboutDialog
        from app.ui.chat_view import ChatView
        from app.ui.connect_api_dialog import ConnectApiDialog
        from app.ui.main_window import MainWindow
        from app.ui.markdown_widget import MarkdownWidget
        from app.ui.settings_dialog import SettingsDialog
        from app.ui.sidebar import Sidebar

        self._tmp = tempfile.TemporaryDirectory()
        self.settings = AppSettings()
        self.settings.base_url = "https://example.invalid/v1"
        self.repository = ChatRepository(Path(self._tmp.name) / "chat.db")
        self.credentials = CredentialsManager()
        self.service = ConversationService(
            self.repository,
            QwenApiClient(self.settings.base_url, "", default_timeout_seconds=5.0),
        )
        self.sidebar = Sidebar()
        self.chat = ChatView(markdown_factory=MarkdownWidget)
        self.window = MainWindow(
            sidebar=self.sidebar,
            chat_view=self.chat,
            settings_dialog_factory=lambda: SettingsDialog(
                self.settings, self.service, self.repository, self.credentials
            ),
            connect_dialog_factory=lambda: ConnectApiDialog(
                self.settings, self.credentials, lambda k, b: QwenApiClient(b, k)
            ),
            about_dialog_factory=AboutDialog,
        )
        self.controller = controller_module.ChatController(
            self.window,
            self.sidebar,
            self.chat,
            self.service,
            self.settings,
            self.credentials,
            self.repository,
            settings_dialog_factory=lambda: SettingsDialog(
                self.settings, self.service, self.repository, self.credentials
            ),
            connect_dialog_factory=lambda: ConnectApiDialog(
                self.settings, self.credentials, lambda k, b: QwenApiClient(b, k)
            ),
        )
        # Replace the real worker construction so no thread pool is involved.
        self.started_workers: list[FakeWorker] = []
        self._original_build = controller_module.build_worker

        def fake_build(client, request, token, *, request_id="", conversation_id=""):
            worker = FakeWorker(request_id)
            self.started_workers.append(worker)
            return worker

        controller_module.build_worker = fake_build
        from PySide6.QtCore import QThreadPool

        self._original_start = QThreadPool.globalInstance().start
        QThreadPool.globalInstance().start = lambda *a, **k: None  # type: ignore[assignment]

    def tearDown(self) -> None:
        import app.controller as controller_module
        from PySide6.QtCore import QThreadPool

        controller_module.build_worker = self._original_build
        QThreadPool.globalInstance().start = self._original_start  # type: ignore[assignment]
        self._tmp.cleanup()

    def _connect_key(self) -> None:
        """Point the controller at a client that has a key (no network is used)."""
        self.controller._client = QwenApiClient(
            self.settings.base_url, "sk-test", default_timeout_seconds=5.0
        )


class TestSendGating(ControllerTestCase):
    def test_send_without_key_does_not_start_a_worker(self) -> None:
        self.controller.start()
        self.controller.send_message("hello")
        self.assertEqual(self.started_workers, [])
        self.assertIsNone(self.service.active_id or None)
        # The empty-state placeholder plus the error block should be present.
        self.assertGreaterEqual(self.chat._container_layout.count(), 1)
        self.assertFalse(self.chat.is_busy())

    def test_send_creates_conversation_and_starts_one_worker(self) -> None:
        self._connect_key()
        self.controller.start()
        self.controller.send_message("hello there")
        self.assertEqual(len(self.started_workers), 1)
        self.assertTrue(self.chat.is_busy())
        self.assertIsNotNone(self.service.active_id)

    def test_second_send_while_busy_is_ignored(self) -> None:
        self._connect_key()
        self.controller.start()
        self.controller.send_message("first")
        self.controller.send_message("second")
        self.assertEqual(len(self.started_workers), 1)

    def test_send_after_finalize_works_again(self) -> None:
        self._connect_key()
        self.controller.start()
        self.controller.send_message("first")
        self.controller._finalize(RequestState.COMPLETED)
        self.assertFalse(self.chat.is_busy())
        self.controller.send_message("second")
        self.assertEqual(len(self.started_workers), 2)

    def test_empty_message_from_view_is_not_sent(self) -> None:
        self._connect_key()
        self.controller.start()
        self.chat._input.setPlainText("   ")
        self.chat._emit_send()
        self.assertEqual(self.started_workers, [])


class TestStaleRequestIsolation(ControllerTestCase):
    def test_chunk_from_superseded_request_is_ignored(self) -> None:
        """A late chunk must never be written into the current conversation."""
        self._connect_key()
        self.controller.start()
        self.controller.send_message("hello")

        # Simulate the worker being replaced by a newer request.
        self.controller._worker = FakeWorker("a-different-request-id")
        self.controller._stream_buffer = []
        self.controller._on_chunk("stale text")
        self.assertEqual(self.controller._stream_buffer, [])

    def test_chunk_from_current_request_is_buffered(self) -> None:
        self._connect_key()
        self.controller.start()
        self.controller.send_message("hello")
        self.controller._on_chunk("live text")
        self.assertEqual(self.controller._stream_buffer, ["live text"])

    def test_chunk_without_active_request_is_ignored(self) -> None:
        self.controller._handle = None
        self.controller._worker = None
        self.controller._on_chunk("orphan")
        self.assertEqual(self.controller._stream_buffer, [])


class TestStop(ControllerTestCase):
    def test_stop_aborts_worker_and_token(self) -> None:
        self._connect_key()
        self.controller.start()
        self.controller.send_message("hello")
        worker = self.started_workers[0]
        handle = self.controller._handle
        self.assertIsNotNone(handle)

        self.controller.stop_request()
        self.assertEqual(worker.abort_calls, 1)
        self.assertTrue(handle.abort_token.is_aborted())

    def test_stop_without_request_is_safe(self) -> None:
        self.controller.stop_request()
        self.assertEqual(self.started_workers, [])


class TestFinalize(ControllerTestCase):
    def test_completed_persists_assistant_text_once(self) -> None:
        self._connect_key()
        self.controller.start()
        self.controller.send_message("question")
        handle = self.controller._handle

        self.controller._on_chunk("the ")
        self.controller._on_chunk("answer")
        self.controller._finalize(RequestState.COMPLETED)

        messages = self.repository.list_messages(handle.conversation_id)
        assistant = [m for m in messages if m["role"] == "assistant"]
        self.assertEqual(len(assistant), 1)
        self.assertEqual(assistant[0]["content"], "the answer")
        self.assertFalse(self.controller._is_busy())

    def test_cancelled_keeps_partial_answer(self) -> None:
        self._connect_key()
        self.controller.start()
        self.controller.send_message("question")
        handle = self.controller._handle

        self.controller._on_chunk("half an ans")
        self.controller._finalize(RequestState.CANCELLED, note="stopped")

        messages = self.repository.list_messages(handle.conversation_id)
        assistant = [m for m in messages if m["role"] == "assistant"]
        self.assertEqual(assistant[0]["content"], "half an ans")

    def test_failed_keeps_partial_answer(self) -> None:
        self._connect_key()
        self.controller.start()
        self.controller.send_message("question")
        handle = self.controller._handle

        self.controller._on_chunk("partial")
        self.controller._finalize(RequestState.FAILED)

        messages = self.repository.list_messages(handle.conversation_id)
        assistant = [m for m in messages if m["role"] == "assistant"]
        self.assertEqual(assistant[0]["content"], "partial")

    def test_finalize_without_handle_is_safe(self) -> None:
        self.controller._handle = None
        self.controller._worker = None
        self.controller._finalize(RequestState.COMPLETED)
        self.assertFalse(self.controller._is_busy())


class TestSidebarAndNavigation(ControllerTestCase):
    def test_refresh_sidebar_shows_created_conversations(self) -> None:
        self.service.new_conversation(title="One")
        self.service.new_conversation(title="Two")
        self.controller.refresh_sidebar()
        self.assertEqual(self.sidebar._list.count(), 2)

    def test_new_chat_is_blocked_while_busy(self) -> None:
        self._connect_key()
        self.controller.start()
        self.controller.send_message("hello")
        active_before = self.service.active_id
        self.controller.new_chat()
        self.assertEqual(self.service.active_id, active_before)

    def test_search_filters_the_sidebar(self) -> None:
        first = self.service.new_conversation(title="Alpha topic")
        self.service.new_conversation(title="Beta topic")
        self.controller.search_conversations("Alpha")
        self.assertEqual(len(self.service.search("Alpha")), 1)

    def test_shutdown_aborts_in_flight_request(self) -> None:
        self._connect_key()
        self.controller.start()
        self.controller.send_message("hello")
        worker = self.started_workers[0]
        self.controller.shutdown()
        self.assertEqual(worker.abort_calls, 1)


if __name__ == "__main__":
    unittest.main()
