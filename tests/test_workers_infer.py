"""Tests for the streaming worker.

The worker is exercised by calling ``run()`` directly on the test thread. Qt
delivers signals synchronously for same-thread connections, so no event loop is
required, while still using the real ``Signal`` machinery the GUI relies on.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QCoreApplication

from app.api.client import AbortToken, ChatMessage, CompletionRequest
from app.api.errors import AuthenticationError, CancelledError, NetworkError
from app.workers.infer import InferWorker, WorkerSignals, build_worker


class RecordingSignals(WorkerSignals):
    """Collect everything the worker emits, using the real Qt signals."""

    def __init__(self) -> None:
        super().__init__()
        self.chunks: list[str] = []
        self.done_payloads: list[str] = []
        self.errors: list[object] = []
        self.cancelled_count = 0
        self.chunk.connect(self.chunks.append)
        self.done.connect(self.done_payloads.append)
        self.failed.connect(self.errors.append)
        self.cancelled.connect(self._on_cancelled)

    def _on_cancelled(self) -> None:
        self.cancelled_count += 1


class FakeClient:
    """Yield a fixed list of deltas, honouring the abort token."""

    def __init__(self, deltas=("Hel", "lo"), error: Exception | None = None) -> None:
        self.deltas = list(deltas)
        self.error = error
        self.seen_request = None

    def stream_chat_completion(self, request, token=None):
        self.seen_request = request
        for delta in self.deltas:
            if token is not None and token.is_aborted():
                raise CancelledError()
            yield delta
        if self.error is not None:
            raise self.error


def _request() -> CompletionRequest:
    return CompletionRequest(
        model="qwen-turbo",
        messages=[ChatMessage(role="user", content="hi")],
    )


class TestWorkerSignals(unittest.TestCase):
    def test_signals_are_qt_signals_and_connectable(self) -> None:
        signals = WorkerSignals()
        received: list[str] = []
        signals.chunk.connect(received.append)
        signals.chunk.emit("a")
        self.assertEqual(received, ["a"])

    def test_worker_is_a_runnable(self) -> None:
        from PySide6.QtCore import QRunnable

        self.assertTrue(issubclass(InferWorker, QRunnable))


class TestInferWorkerRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QCoreApplication.instance() or QCoreApplication([])

    def test_success_emits_chunks_then_done(self) -> None:
        signals = RecordingSignals()
        worker = InferWorker(
            FakeClient(["Hel", "lo ", "world"]), _request(), AbortToken(), signals=signals
        )
        worker.run()

        self.assertEqual(signals.chunks, ["Hel", "lo ", "world"])
        self.assertEqual(signals.done_payloads, ["Hello world"])
        self.assertEqual(signals.errors, [])
        self.assertEqual(signals.cancelled_count, 0)

    def test_api_error_emits_failed_with_typed_error(self) -> None:
        signals = RecordingSignals()
        worker = InferWorker(
            FakeClient(["partial"], error=AuthenticationError()),
            _request(),
            AbortToken(),
            signals=signals,
        )
        worker.run()

        self.assertEqual(signals.chunks, ["partial"])
        self.assertEqual(len(signals.errors), 1)
        self.assertIsInstance(signals.errors[0], AuthenticationError)
        self.assertEqual(signals.done_payloads, [])

    def test_network_error_emits_failed(self) -> None:
        signals = RecordingSignals()
        worker = InferWorker(
            FakeClient([], error=NetworkError()), _request(), AbortToken(), signals=signals
        )
        worker.run()
        self.assertIsInstance(signals.errors[0], NetworkError)

    def test_unexpected_exception_becomes_network_error(self) -> None:
        signals = RecordingSignals()
        worker = InferWorker(
            FakeClient([], error=RuntimeError("boom")), _request(), AbortToken(), signals=signals
        )
        worker.run()
        self.assertEqual(len(signals.errors), 1)
        self.assertIsInstance(signals.errors[0], NetworkError)

    def test_pre_aborted_token_emits_cancelled(self) -> None:
        token = AbortToken()
        token.abort()
        signals = RecordingSignals()
        worker = InferWorker(FakeClient([]), _request(), token, signals=signals)
        worker.run()
        self.assertEqual(signals.cancelled_count, 1)
        self.assertEqual(signals.chunks, [])
        self.assertEqual(signals.errors, [])

    def test_request_abort_during_stream_emits_cancelled(self) -> None:
        """Aborting mid-stream must stop the transfer and report cancellation."""
        token = AbortToken()

        class AbortAfterFirst(FakeClient):
            """Mirror the real client: check the token between deltas."""

            def stream_chat_completion(self, request, token=None):
                yield "first"
                token.abort()
                if token.is_aborted():
                    raise CancelledError()
                yield "second"

        signals = RecordingSignals()
        worker = InferWorker(AbortAfterFirst([]), _request(), token, signals=signals)
        worker.run()

        self.assertEqual(signals.chunks, ["first"])
        self.assertEqual(signals.cancelled_count, 1)
        self.assertEqual(signals.done_payloads, [])

    def test_request_abort_sets_token(self) -> None:
        token = AbortToken()
        worker = InferWorker(FakeClient([]), _request(), token)
        worker.request_abort()
        self.assertTrue(token.is_aborted())

    def test_request_passed_through_unchanged(self) -> None:
        client = FakeClient(["x"])
        request = _request()
        InferWorker(client, request, AbortToken()).run()
        self.assertIs(client.seen_request, request)

    def test_exactly_one_terminal_signal(self) -> None:
        signals = RecordingSignals()
        InferWorker(FakeClient(["a"]), _request(), AbortToken(), signals=signals).run()
        terminals = len(signals.done_payloads) + len(signals.errors) + signals.cancelled_count
        self.assertEqual(terminals, 1)


class TestBuildWorker(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QCoreApplication.instance() or QCoreApplication([])

    def test_build_worker_carries_ids(self) -> None:
        worker = build_worker(
            FakeClient([]),
            _request(),
            AbortToken(),
            request_id="req-1",
            conversation_id="conv-1",
        )
        self.assertEqual(worker.request_id, "req-1")
        self.assertEqual(worker.conversation_id, "conv-1")
        self.assertIsInstance(worker.signals, WorkerSignals)

    def test_auto_delete_enabled(self) -> None:
        worker = build_worker(FakeClient([]), _request(), AbortToken())
        self.assertTrue(worker.autoDelete())


if __name__ == "__main__":
    unittest.main()
