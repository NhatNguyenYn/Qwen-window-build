"""Tests for the request state machine."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.state import (
    FinishResult,
    InFlightRequest,
    RequestState,
    StateTransitionError,
    TransitionGuard,
    finish_in_flight,
)


class TestRequestState(unittest.TestCase):
    def test_active_states(self) -> None:
        self.assertTrue(RequestState.is_active(RequestState.CONNECTING))
        self.assertTrue(RequestState.is_active(RequestState.STREAMING))
        self.assertFalse(RequestState.is_active(RequestState.IDLE))

    def test_terminal_states(self) -> None:
        for state in (RequestState.COMPLETED, RequestState.CANCELLED, RequestState.FAILED):
            self.assertTrue(RequestState.is_terminal(state))
        self.assertFalse(RequestState.is_terminal(RequestState.STREAMING))


class TestTransitionGuard(unittest.TestCase):
    def test_allowed_flow(self) -> None:
        guard = TransitionGuard("req-1")
        guard.transition(RequestState.CONNECTING)
        guard.transition(RequestState.STREAMING)
        guard.transition(RequestState.COMPLETED)
        self.assertEqual(guard.state, RequestState.COMPLETED)

    def test_direct_completion_from_idle_is_allowed(self) -> None:
        """A request that resolves without ever streaming is still valid."""
        guard = TransitionGuard("req-1")
        guard.transition(RequestState.COMPLETED)
        self.assertEqual(guard.state, RequestState.COMPLETED)

    def test_cancel_from_streaming(self) -> None:
        guard = TransitionGuard("req-1")
        guard.transition(RequestState.CONNECTING)
        guard.transition(RequestState.STREAMING)
        guard.transition(RequestState.CANCELLED)
        self.assertEqual(guard.state, RequestState.CANCELLED)

    def test_fail_from_connecting(self) -> None:
        guard = TransitionGuard("req-1")
        guard.transition(RequestState.CONNECTING)
        guard.transition(RequestState.FAILED)
        self.assertEqual(guard.state, RequestState.FAILED)

    def test_skipping_states_raises(self) -> None:
        guard = TransitionGuard("req-1")
        with self.assertRaises(StateTransitionError):
            guard.transition(RequestState.STREAMING)

    def test_completed_is_terminal(self) -> None:
        guard = TransitionGuard("req-1")
        guard.transition(RequestState.COMPLETED)
        with self.assertRaises(StateTransitionError):
            guard.transition(RequestState.STREAMING)

    def test_failed_cannot_restart(self) -> None:
        guard = TransitionGuard("req-1")
        guard.transition(RequestState.CONNECTING)
        guard.transition(RequestState.FAILED)
        with self.assertRaises(StateTransitionError):
            guard.transition(RequestState.STREAMING)

    def test_error_reports_request_id(self) -> None:
        guard = TransitionGuard("req-42")
        with self.assertRaises(StateTransitionError) as ctx:
            guard.transition(RequestState.STREAMING)
        self.assertEqual(ctx.exception.request_id, "req-42")


class TestInFlightRequest(unittest.TestCase):
    def _make(self, state: str = RequestState.IDLE) -> InFlightRequest:
        return InFlightRequest(
            request_id="req-1",
            conversation_id="conv-1",
            assistant_message_id=7,
            state=state,
            abort_handle=object(),
        )

    def test_transition_updates_state(self) -> None:
        inflight = self._make()
        inflight.transition(RequestState.CONNECTING)
        self.assertEqual(inflight.state, RequestState.CONNECTING)

    def test_rehydrating_a_terminal_state_is_validated(self) -> None:
        inflight = self._make(RequestState.COMPLETED)
        self.assertTrue(inflight.finished)

    def test_rehydrating_an_impossible_state_raises(self) -> None:
        with self.assertRaises(StateTransitionError):
            self._make(RequestState.STREAMING)

    def test_flags(self) -> None:
        inflight = self._make()
        inflight.transition(RequestState.CONNECTING)
        inflight.transition(RequestState.FAILED)
        self.assertTrue(inflight.failed)
        self.assertTrue(inflight.finished)
        self.assertFalse(inflight.cancelled)


class TestFinishInFlight(unittest.TestCase):
    def _make(self, state: str) -> InFlightRequest:
        handle = object()
        inflight = InFlightRequest(
            request_id="req-1",
            conversation_id="conv-1",
            assistant_message_id=3,
            state=RequestState.IDLE,
            abort_handle=handle,
        )
        if state != RequestState.IDLE:
            inflight.guard.transition(state)
            inflight.state = state
        return inflight

    def test_completed_result(self) -> None:
        result = finish_in_flight(self._make(RequestState.COMPLETED))
        self.assertIsInstance(result, FinishResult)
        self.assertTrue(result.finished)
        self.assertFalse(result.failed)
        self.assertFalse(result.cancelled)
        self.assertEqual(result.assistant_message_id, 3)

    def test_cancelled_result(self) -> None:
        result = finish_in_flight(self._make(RequestState.CANCELLED))
        self.assertTrue(result.cancelled)
        self.assertTrue(result.finished)

    def test_failed_result(self) -> None:
        result = finish_in_flight(self._make(RequestState.FAILED))
        self.assertTrue(result.failed)

    def test_handle_released_for_every_terminal_state(self) -> None:
        """Resources are released on failure too.

        Once a request is terminal, aborting it is meaningless and holding the
        handle would keep network objects alive. Retry builds a new request.
        """
        for state in (
            RequestState.COMPLETED,
            RequestState.CANCELLED,
            RequestState.FAILED,
        ):
            with self.subTest(state=state):
                inflight = self._make(state)
                finish_in_flight(inflight)
                self.assertIsNone(inflight.abort_handle)


if __name__ == "__main__":
    unittest.main()
