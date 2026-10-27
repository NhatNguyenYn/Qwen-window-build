"""Tests for the Qwen API client: request shaping, streaming, cancellation."""
from __future__ import annotations

import json
import os
import sys
import unittest
import urllib.error
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.client import (
    AbortToken,
    ChatMessage,
    CompletionRequest,
    QwenApiClient,
)
from app.api.errors import (
    ApiError,
    AuthenticationError,
    CancelledError,
    ModelNotFoundError,
    NetworkError,
    PaymentError,
    RateLimitError,
    ServerError,
    TimeoutError,
    classify_error,
)


class FakeResponse:
    """Minimal stand-in for the object ``urlopen`` returns.

    It supports the context-manager protocol and line-by-line reading because
    the streaming code reads the body incrementally.
    """

    def __init__(self, payload: bytes, lines: list[bytes] | None = None) -> None:
        self._payload = payload
        self._lines = list(lines or [])
        self.closed = False

    def read(self) -> bytes:
        return self._payload

    def readline(self) -> bytes:
        if self._lines:
            return self._lines.pop(0)
        return b""

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args) -> None:
        self.close()


def _sse(*deltas: str) -> list[bytes]:
    lines = []
    for delta in deltas:
        frame = {"choices": [{"delta": {"content": delta}}]}
        lines.append(f"data: {json.dumps(frame)}\n".encode())
    lines.append(b"data: [DONE]\n")
    return lines


class TestCompletionRequest(unittest.TestCase):
    def test_payload_shape(self) -> None:
        request = CompletionRequest(
            model="qwen-turbo",
            messages=[ChatMessage(role="user", content="hi")],
            temperature=0.0,
            max_tokens=32,
            stream=True,
        )
        payload = request.to_dict()
        self.assertEqual(payload["model"], "qwen-turbo")
        self.assertEqual(payload["messages"], [{"role": "user", "content": "hi"}])
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["max_tokens"], 32)

    def test_parse_stream_line(self) -> None:
        request = CompletionRequest(model="m", messages=[])
        frame = json.dumps({"choices": [{"delta": {"content": "Hey"}}]})
        self.assertEqual(request.parse_stream_line(f"data: {frame}"), "Hey")
        self.assertIsNone(request.parse_stream_line("data: [DONE]"))
        self.assertIsNone(request.parse_stream_line(""))
        self.assertIsNone(request.parse_stream_line("data: not-json"))
        # Role-only opening frame carries no text and must be skipped.
        role_only = json.dumps({"choices": [{"delta": {"role": "assistant"}}]})
        self.assertIsNone(request.parse_stream_line(f"data: {role_only}"))


class TestClassifyError(unittest.TestCase):
    def test_auth(self) -> None:
        error = classify_error(401, "unauthorized", None)
        self.assertIsInstance(error, AuthenticationError)
        self.assertFalse(error.retryable)

    def test_model_not_found(self) -> None:
        self.assertIsInstance(classify_error(404, "not found", None), ModelNotFoundError)

    def test_payment(self) -> None:
        self.assertIsInstance(classify_error(402, "billing", None), PaymentError)

    def test_rate_limit_is_retryable(self) -> None:
        error = classify_error(429, "rate limit", None)
        self.assertIsInstance(error, RateLimitError)
        self.assertTrue(error.retryable)

    def test_server_error_retryable(self) -> None:
        self.assertIsInstance(classify_error(500, "internal", None), ServerError)

    def test_unexpected_status_is_not_retryable(self) -> None:
        error = classify_error(400, "bad request", None)
        self.assertIsInstance(error, ApiError)
        self.assertFalse(error.retryable)

    def test_timeout_from_exception(self) -> None:
        import socket

        error = classify_error(None, "", socket.timeout("timed out"))
        self.assertIsInstance(error, TimeoutError)
        self.assertTrue(error.retryable)

    def test_connection_error_from_urlerror(self) -> None:
        error = classify_error(None, "", urllib.error.URLError("no route"))
        self.assertIsInstance(error, NetworkError)

    def test_http_error_status_is_read_from_code(self) -> None:
        """Regression: urllib exposes ``.code``, not ``.status_code``.

        Before this fix every HTTPError was reported as a network failure, so a
        wrong API key looked like a connectivity problem.
        """
        http_error = urllib.error.HTTPError(
            "https://example.invalid/v1/chat/completions", 401, "Unauthorized", {}, None
        )
        error = classify_error(None, "unauthorized", http_error)
        self.assertIsInstance(error, AuthenticationError)

    def test_http_error_429_is_rate_limit(self) -> None:
        http_error = urllib.error.HTTPError(
            "https://example.invalid/v1", 429, "Too Many Requests", {}, None
        )
        self.assertIsInstance(classify_error(None, "", http_error), RateLimitError)


class TestClientConstruction(unittest.TestCase):
    def test_base_url_is_stripped(self) -> None:
        client = QwenApiClient(base_url="  https://example.com/v1/  ", api_key="k")
        self.assertEqual(client.base_url, "https://example.com/v1")

    def test_trailing_slash_removed(self) -> None:
        client = QwenApiClient("https://example.com/v1/", "k")
        self.assertEqual(client.base_url, "https://example.com/v1")

    def test_empty_base_url_rejected(self) -> None:
        with self.assertRaises(ValueError):
            QwenApiClient("   ", "k")

    def test_default_timeout(self) -> None:
        client = QwenApiClient("https://example.invalid/v1", "k")
        self.assertEqual(client.has_key(), True)

    def test_has_key_false_when_blank(self) -> None:
        self.assertFalse(QwenApiClient("https://example.invalid/v1", "").has_key())


class TestListModels(unittest.TestCase):
    def test_extracts_names(self) -> None:
        payload = json.dumps(
            {"data": [{"id": "qwen-turbo"}, {"id": "qwen-plus"}, "qwen-max"]}
        ).encode()
        with patch("urllib.request.urlopen", return_value=FakeResponse(payload)):
            models = QwenApiClient("https://example.invalid/v1", "k").list_models()
        self.assertEqual(models, ["qwen-turbo", "qwen-plus", "qwen-max"])

    def test_closes_response(self) -> None:
        response = FakeResponse(json.dumps({"data": []}).encode())
        with patch("urllib.request.urlopen", return_value=response):
            QwenApiClient("https://example.invalid/v1", "k").list_models()
        self.assertTrue(response.closed)

    def test_test_connection_reports_count(self) -> None:
        payload = json.dumps({"data": [{"id": "qwen-turbo"}]}).encode()
        with patch("urllib.request.urlopen", return_value=FakeResponse(payload)):
            result = QwenApiClient("https://example.invalid/v1", "k").test_connection()
        # Regression: this used to return None, and the dialog crashed on it.
        self.assertIsInstance(result, dict)
        self.assertEqual(result["count"], 1)
        self.assertIn("qwen-turbo", result["models"])


class TestNonStreamingCompletion(unittest.TestCase):
    def test_returns_assistant_text(self) -> None:
        payload = json.dumps(
            {"choices": [{"message": {"role": "assistant", "content": "Hello world"}}]}
        ).encode()
        with patch("urllib.request.urlopen", return_value=FakeResponse(payload)):
            text = QwenApiClient("https://example.invalid/v1", "k").create_chat_completion(
                CompletionRequest(
                    model="qwen-turbo",
                    messages=[ChatMessage(role="user", content="hi")],
                )
            )
        self.assertEqual(text, "Hello world")


class TestStreaming(unittest.TestCase):
    def test_yields_deltas(self) -> None:
        response = FakeResponse(b"", _sse("Hel", "lo ", "world"))
        request = CompletionRequest(
            model="qwen-turbo",
            messages=[ChatMessage(role="user", content="hi")],
        )
        with patch("urllib.request.urlopen", return_value=response):
            chunks = list(
                QwenApiClient("https://example.invalid/v1", "k").stream_chat_completion(
                    request
                )
            )
        self.assertEqual("".join(chunks), "Hello world")
        self.assertTrue(request.stream)

    def test_response_is_closed_after_stream(self) -> None:
        response = FakeResponse(b"", _sse("a"))
        with patch("urllib.request.urlopen", return_value=response):
            list(
                QwenApiClient("https://example.invalid/v1", "k").stream_chat_completion(
                    CompletionRequest(model="m", messages=[])
                )
            )
        self.assertTrue(response.closed)

    def test_pre_aborted_token_raises(self) -> None:
        token = AbortToken()
        token.abort()
        with self.assertRaises(CancelledError):
            list(
                QwenApiClient("https://example.invalid/v1", "k").stream_chat_completion(
                    CompletionRequest(model="m", messages=[]), token
                )
            )

    def test_abort_during_stream_raises_and_closes(self) -> None:
        """Stop must actually cancel the transfer, not just hide a spinner."""
        token = AbortToken()
        response = FakeResponse(b"", _sse("a", "b", "c"))
        original_readline = response.readline

        def readline_then_abort() -> bytes:
            chunk = original_readline()
            token.abort()
            return chunk

        response.readline = readline_then_abort  # type: ignore[method-assign]

        with patch("urllib.request.urlopen", return_value=response):
            with self.assertRaises(CancelledError):
                list(
                    QwenApiClient("https://example.invalid/v1", "k").stream_chat_completion(
                        CompletionRequest(model="m", messages=[]), token
                    )
                )
        self.assertTrue(response.closed)

    def test_interrupted_stream_raises_network_error(self) -> None:
        response = FakeResponse(b"", [])
        response.readline = lambda: (_ for _ in ()).throw(OSError("connection reset"))
        with patch("urllib.request.urlopen", return_value=response):
            with self.assertRaises(NetworkError):
                list(
                    QwenApiClient("https://example.invalid/v1", "k").stream_chat_completion(
                        CompletionRequest(model="m", messages=[])
                    )
                )


class TestAbortToken(unittest.TestCase):
    def test_abort_closes_registered_response(self) -> None:
        token = AbortToken()
        response = FakeResponse(b"")
        token.register_response(response)
        self.assertFalse(token.is_aborted())
        token.abort()
        self.assertTrue(token.is_aborted())
        self.assertTrue(response.closed)

    def test_registering_after_abort_raises(self) -> None:
        token = AbortToken()
        token.abort()
        with self.assertRaises(CancelledError):
            token.register_response(FakeResponse(b""))


class TestApiKeyNeverLeaks(unittest.TestCase):
    def test_key_absent_from_error_message(self) -> None:
        secret = "sk-super-secret-value"
        http_error = urllib.error.HTTPError(
            "https://example.invalid/v1", 401, "Unauthorized", {}, None
        )
        error = classify_error(None, "", http_error)
        self.assertNotIn(secret, str(error))
        self.assertNotIn(secret, error.message)

    def test_key_not_in_client_repr(self) -> None:
        client = QwenApiClient("https://example.invalid/v1", "sk-hidden")
        self.assertNotIn("sk-hidden", repr(client.__dict__.get("_base_url", "")))


if __name__ == "__main__":
    unittest.main()
