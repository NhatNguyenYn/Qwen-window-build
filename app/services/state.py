"""Request lifecycle state machine and in-flight request bookkeeping.

This is the single source of truth for the states a chat request can be in.
Invalid transitions raise immediately instead of silently corrupting state, so
a stale request can never overwrite the state of a newer one.

The module is Qt-free and therefore testable without a GUI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


class RequestState:
    """String constants for request lifecycle states."""

    IDLE = "IDLE"
    CONNECTING = "CONNECTING"
    STREAMING = "STREAMING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"

    TERMINAL = (COMPLETED, CANCELLED, FAILED)

    _ALLOWED: Dict[str, Tuple[str, ...]] = {
        IDLE: (CONNECTING, COMPLETED, CANCELLED, FAILED),
        CONNECTING: (STREAMING, COMPLETED, CANCELLED, FAILED),
        STREAMING: (COMPLETED, CANCELLED, FAILED),
        COMPLETED: (COMPLETED,),
        CANCELLED: (CANCELLED,),
        FAILED: (FAILED,),
    }

    @classmethod
    def is_terminal(cls, state: str) -> bool:
        return state in cls.TERMINAL

    @classmethod
    def is_active(cls, state: str) -> bool:
        return state in (cls.CONNECTING, cls.STREAMING)

    @classmethod
    def allowed_targets(cls, source: str) -> Tuple[str, ...]:
        return cls._ALLOWED.get(source, ())


class StateTransitionError(Exception):
    """Raised when a request attempts an invalid state transition."""

    def __init__(self, request_id: str, source: str, target: str) -> None:
        self.request_id = request_id
        self.source = source
        self.target = target
        super().__init__(
            f"Cannot transition request {request_id!r} from {source!r} to {target!r}"
        )


class TransitionGuard:
    """Validates the state transitions of one request."""

    def __init__(self, request_id: str = "anonymous") -> None:
        self._state: str = RequestState.IDLE
        self._request_id: str = request_id

    @property
    def state(self) -> str:
        return self._state

    @property
    def request_id(self) -> str:
        return self._request_id

    def transition(self, target: str) -> None:
        source = self._state
        if target not in RequestState.allowed_targets(source):
            raise StateTransitionError(self._request_id, source, target)
        self._state = target


@dataclass
class InFlightRequest:
    """One request owned by the conversation service."""

    request_id: str
    conversation_id: str
    assistant_message_id: Optional[int] = None
    state: str = RequestState.IDLE
    guard: TransitionGuard = field(init=False)
    abort_handle: Any = None

    def __post_init__(self) -> None:
        self.guard = TransitionGuard(self.request_id)
        if self.state != RequestState.IDLE:
            # Rehydrating a stored state must not bypass validation.
            self.guard.transition(self.state)

    def transition(self, target: str) -> None:
        self.guard.transition(target)
        self.state = self.guard.state

    @property
    def finished(self) -> bool:
        return RequestState.is_terminal(self.state)

    @property
    def failed(self) -> bool:
        return self.state == RequestState.FAILED

    @property
    def cancelled(self) -> bool:
        return self.state == RequestState.CANCELLED

    @property
    def is_active(self) -> bool:
        return RequestState.is_active(self.state)


@dataclass
class FinishResult:
    """Outcome of finishing a request, with resources already released."""

    request_id: str
    conversation_id: str
    assistant_message_id: Optional[int]
    finished: bool
    failed: bool
    cancelled: bool


def finish_in_flight(inflight: InFlightRequest) -> FinishResult:
    """Finalize a request and release its abort handle.

    The handle is released for every terminal state, including FAILED: once a
    request has reached a terminal state, aborting it is meaningless, and a
    retained handle would keep the response object alive. Retrying builds a new
    request with a new handle.
    """
    result = FinishResult(
        request_id=inflight.request_id,
        conversation_id=inflight.conversation_id,
        assistant_message_id=inflight.assistant_message_id,
        finished=RequestState.is_terminal(inflight.state),
        failed=inflight.state == RequestState.FAILED,
        cancelled=inflight.state == RequestState.CANCELLED,
    )
    inflight.abort_handle = None
    return result
