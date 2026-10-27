"""Qwen (DashScope OpenAI-compatible) chat API client.

The client speaks the OpenAI ``/chat/completions`` shape because Qwen's
DashScope service exposes an OpenAI-compatible endpoint. It supports both a
single-shot completion and a streaming completion.

Streaming is cancellable at the network layer: :class:`AbortToken` can close the
in-flight HTTP response, which unblocks and terminates the reader.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional

from app.api.errors import (
    ApiError,
    CancelledError,
    NetworkError,
    TimeoutError,
    classify_error,
)


@dataclass
class ChatMessage:
    role: str
    content: str

    def to_dict(self) -> Dict[str, Any]:
        return {"role": self.role, "content": self.content}


@dataclass
class CompletionRequest:
    model: str
    messages: List[ChatMessage]
    temperature: float = 0.0
    max_tokens: int = 2000
    stream: bool = False
    request_timeout_seconds: float = 60.0

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [m.to_dict() for m in self.messages],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": self.stream,
        }
        return payload

    @staticmethod
    def parse_delta(raw: str) -> Optional[str]:
        """Extract the text delta from one SSE ``data:`` payload.

        Returns ``None`` for control frames, malformed JSON, or deltas that
        carry no text (for example the role-only opening frame).
        """
        try:
            parsed = json.loads(raw)
        except ValueError:
            return None
        choices = parsed.get("choices")
        if not isinstance(choices, list) or not choices:
            return None
        choice = choices[0]
        if not isinstance(choice, dict):
            return None
        delta = choice.get("delta")
        if not isinstance(delta, dict):
            return None
        content = delta.get("content")
        if isinstance(content, str) and content:
            return content
        return None

    def parse_stream_line(self, raw: str) -> Optional[str]:
        """Parse one raw SSE line into a text delta, if it carries one."""
        line = raw.strip()
        if not line:
            return None
        if line == "[DONE]":
            return None
        if line.startswith("data:"):
            line = line[5:].strip()
        return self.parse_delta(line)


class AbortToken:
    """Thread-safe cancellation token that can close an in-flight response.

    ``abort()`` is safe to call from the UI thread while a worker thread is
    blocked reading the response: closing the response object makes the pending
    read fail, so cancellation actually stops the transfer instead of only
    hiding a spinner.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._aborted = False
        self._response = None

    def abort(self) -> None:
        with self._lock:
            self._aborted = True
            response = self._response
            self._response = None
        if response is not None:
            try:
                response.close()
            except Exception:
                pass

    def is_aborted(self) -> bool:
        with self._lock:
            return self._aborted

    def register_response(self, response) -> None:
        """Track the live response so ``abort()`` can close it."""
        with self._lock:
            if self._aborted:
                raise CancelledError()
            self._response = response

    def detach_response(self) -> None:
        with self._lock:
            self._response = None


class QwenApiClient:
    """OpenAI-compatible client for Qwen-style endpoints."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        default_timeout_seconds: float = 60.0,
    ) -> None:
        stripped = (base_url or "").strip()
        if not stripped:
            raise ValueError("base_url must not be empty")
        self._base_url: str = stripped.rstrip("/")
        self._api_key: str = api_key or ""
        self._default_timeout: float = float(default_timeout_seconds)

    # ------------------------------------------------------------------ config

    @property
    def base_url(self) -> str:
        return self._base_url

    def has_key(self) -> bool:
        return bool(self._api_key)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _open(self, path: str, *, data: Optional[bytes] = None, timeout: float):
        url = self._base_url + path
        request = urllib.request.Request(
            url,
            data=data,
            headers=self._headers(),
            method="POST" if data is not None else "GET",
        )
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            raise classify_error(exc.code, exc.reason or "", exc) from exc
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", None)
            if isinstance(reason, TimeoutError):  # our own class
                raise
            if reason is not None and "timed out" in str(reason).lower():
                raise TimeoutError() from exc
            raise NetworkError(
                "Could not reach the endpoint. Check the base URL and your connection."
            ) from exc
        except TimeoutError:
            raise
        except OSError as exc:
            if isinstance(exc, TimeoutError):
                raise
            raise NetworkError(str(exc) or "network error") from exc

    # ------------------------------------------------------------------ models

    def list_models(self) -> List[str]:
        """Return the model IDs advertised by the endpoint."""
        response = self._open("/models", timeout=self._default_timeout)
        try:
            raw = response.read()
        finally:
            try:
                response.close()
            except Exception:
                pass
        try:
            payload = json.loads(raw)
        except ValueError as exc:
            raise NetworkError("The endpoint did not return valid JSON.") from exc

        entries = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            return []
        names: List[str] = []
        for item in entries:
            name = None
            if isinstance(item, dict):
                name = item.get("id") or item.get("name")
            elif isinstance(item, str):
                name = item
            if isinstance(name, str) and name and name not in names:
                names.append(name)
        return names

    def test_connection(self) -> Dict[str, Any]:
        """Verify the key and endpoint by listing models.

        Returns a dict describing what was found. Raises an ``ApiError``
        subclass when the connection cannot be verified, so callers can show a
        precise message instead of a generic failure.
        """
        models = self.list_models()
        return {
            "models": models,
            "count": len(models),
            "message": (
                f"Connected. {len(models)} model(s) visible."
                if models
                else "Connected, but the endpoint listed no models."
            ),
        }

    # ------------------------------------------------------------- completions

    def create_chat_completion(self, request: CompletionRequest) -> str:
        """Run a non-streaming completion and return the assistant text."""
        request.stream = False
        body = json.dumps(request.to_dict()).encode("utf-8")
        response = self._open(
            "/chat/completions",
            data=body,
            timeout=request.request_timeout_seconds,
        )
        try:
            raw = response.read()
        finally:
            try:
                response.close()
            except Exception:
                pass

        try:
            payload = json.loads(raw)
        except ValueError as exc:
            raise NetworkError("The endpoint did not return valid JSON.") from exc

        if isinstance(payload, dict) and payload.get("error"):
            message = payload["error"]
            if isinstance(message, dict):
                message = message.get("message") or str(message)
            raise ApiError(f"API error: {message}")

        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not isinstance(choices, list) or not choices:
            raise ApiError("The endpoint returned no completion choices.")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str):
            raise ApiError("The endpoint returned an empty message.")
        return content

    def stream_chat_completion(
        self,
        request: CompletionRequest,
        token: Optional[AbortToken] = None,
    ) -> Iterator[str]:
        """Yield assistant text deltas as they arrive.

        Cancellation is checked before opening the stream and between every
        line. Passing a token additionally lets the caller close the socket.
        """
        if token is not None and token.is_aborted():
            raise CancelledError()

        request.stream = True
        body = json.dumps(request.to_dict()).encode("utf-8")
        response = self._open(
            "/chat/completions",
            data=body,
            timeout=request.request_timeout_seconds,
        )
        if token is not None:
            token.register_response(response)

        try:
            while True:
                if token is not None and token.is_aborted():
                    raise CancelledError()
                try:
                    raw_line = response.readline()
                except Exception as exc:
                    if token is not None and token.is_aborted():
                        raise CancelledError() from exc
                    raise NetworkError(
                        "The response stream was interrupted."
                    ) from exc
                if not raw_line:
                    break
                text = raw_line.decode("utf-8", "replace")
                if text.strip() == "[DONE]":
                    break
                delta = request.parse_stream_line(text)
                if delta:
                    yield delta
        finally:
            if token is not None:
                token.detach_response()
            try:
                response.close()
            except Exception:
                pass


# Historical alias kept so existing imports keep working.
ApiClient = QwenApiClient
