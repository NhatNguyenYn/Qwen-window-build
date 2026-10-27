"""Background worker that streams one chat completion.

Threading contract:

* :class:`InferWorker` runs on a ``QThreadPool`` thread. It performs network
  I/O only. It never touches the database, the conversation service, or any
  widget.
* :class:`WorkerSignals` is a ``QObject`` created on the main thread. Emitting
  from the worker thread therefore delivers queued, main-thread callbacks to
  receivers that live on the main thread (the controller is such a receiver).
* Exactly one terminal signal is emitted per run: ``done``, ``failed`` or
  ``cancelled``.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from app.api.client import AbortToken, CompletionRequest, QwenApiClient
from app.api.errors import ApiError, CancelledError, NetworkError


class WorkerSignals(QObject):
    """Signals emitted by :class:`InferWorker`."""

    chunk = Signal(str)
    done = Signal(str)
    failed = Signal(object)
    cancelled = Signal()


class InferWorker(QRunnable):
    """Stream a completion in the background."""

    def __init__(
        self,
        client: QwenApiClient,
        request: CompletionRequest,
        token: AbortToken,
        request_id: str = "",
        conversation_id: str = "",
        signals: Optional[WorkerSignals] = None,
    ) -> None:
        super().__init__()
        self._client = client
        self._request = request
        self._token = token
        self.request_id = request_id
        self.conversation_id = conversation_id
        self.signals = signals or WorkerSignals()
        self.setAutoDelete(True)

    # Kept for compatibility with earlier call sites.
    @property
    def request(self) -> CompletionRequest:
        return self._request

    def request_abort(self) -> None:
        """Cancel the request. Safe to call from the main thread."""
        self._token.abort()

    @Slot()
    def run(self) -> None:
        if self._token.is_aborted():
            # Never start a request that was already cancelled.
            self.signals.cancelled.emit()
            return
        collected: list[str] = []
        try:
            for delta in self._client.stream_chat_completion(
                self._request, self._token
            ):
                collected.append(delta)
                self.signals.chunk.emit(delta)
        except CancelledError:
            self.signals.cancelled.emit()
            return
        except ApiError as exc:
            self.signals.failed.emit(exc)
            return
        except Exception as exc:  # noqa: BLE001 - convert to a typed error
            self.signals.failed.emit(
                NetworkError(str(exc) or "Unexpected network failure.")
            )
            return
        self.signals.done.emit("".join(collected))


def build_worker(
    client: QwenApiClient,
    request: CompletionRequest,
    token: AbortToken,
    *,
    request_id: str = "",
    conversation_id: str = "",
) -> InferWorker:
    """Create a worker with its own signal object on the calling thread."""
    return InferWorker(
        client,
        request,
        token,
        request_id=request_id,
        conversation_id=conversation_id,
    )
