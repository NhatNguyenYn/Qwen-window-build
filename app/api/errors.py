"""Typed error categories for Qwen API failures.

Every error carries a message that is safe to show to the user: it never
contains the API key, and it never includes the raw request body.
"""
from __future__ import annotations

import builtins
from typing import Optional


class ApiError(Exception):
    """Base class for API-related errors raised by the client."""

    def __init__(
        self,
        message: str,
        retryable: bool = False,
        show_key: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable
        self.show_key = show_key


class AuthenticationError(ApiError):
    def __init__(self, message: str = "Invalid API key or access denied.") -> None:
        super().__init__(message, retryable=False, show_key=True)


class InsufficientQuotaError(ApiError):
    def __init__(
        self,
        message: str = "Quota exceeded, or your account is not enabled for this model.",
    ) -> None:
        super().__init__(message, retryable=False, show_key=False)


class ModelNotFoundError(ApiError):
    def __init__(
        self,
        message: str = "The requested model is not available from this endpoint.",
    ) -> None:
        super().__init__(message, retryable=False, show_key=False)


class RateLimitError(ApiError):
    def __init__(self, message: str = "Rate limit reached. Please wait and try again.") -> None:
        super().__init__(message, retryable=True, show_key=False)


class PaymentError(ApiError):
    def __init__(self, message: str = "Billing or payment issue prevented the request.") -> None:
        super().__init__(message, retryable=False, show_key=False)


class NetworkError(ApiError):
    def __init__(
        self,
        message: str = "Network error. Check your connection and try again.",
    ) -> None:
        super().__init__(message, retryable=True, show_key=False)


class TimeoutError(ApiError):
    """A request timed out.

    Note: this shadows the builtin ``TimeoutError`` inside this module. Use
    ``builtins.TimeoutError`` when you need the builtin.
    """

    def __init__(
        self,
        message: str = "The request timed out. Try again, or raise the request timeout.",
    ) -> None:
        super().__init__(message, retryable=True, show_key=False)


class ServerError(ApiError):
    def __init__(self, message: str = "The server had an error. Please try again later.") -> None:
        super().__init__(message, retryable=True, show_key=False)


class CancelledError(ApiError):
    def __init__(self, message: str = "Request was cancelled.") -> None:
        super().__init__(message, retryable=False, show_key=False)


def cancelled_error() -> CancelledError:
    """Create a CancelledError without leaking any API key."""
    return CancelledError()


# Builtin timeout types. ``socket.timeout`` is an alias of the builtin since
# Python 3.10, and ``TimeoutError`` in this module is our own class, so the
# builtin must be referenced explicitly.
_TIMEOUT_TYPES = (builtins.TimeoutError,)


def _status_from_exception(exception: Optional[BaseException]) -> Optional[int]:
    """Read an HTTP status out of whichever HTTP library raised the error.

    ``urllib.error.HTTPError`` exposes ``.code``; httpx/openai SDK errors
    expose ``.status_code``. Both shapes are supported so classification does
    not depend on one HTTP stack.
    """
    if exception is None:
        return None
    for attribute in ("status_code", "code", "status"):
        raw = getattr(exception, attribute, None)
        if isinstance(raw, int) and not isinstance(raw, bool):
            return raw
    response = getattr(exception, "response", None)
    raw = getattr(response, "status_code", None)
    if isinstance(raw, int):
        return raw
    return None


def _text_from_exception(exception: Optional[BaseException]) -> str:
    if exception is None:
        return ""
    parts = [str(exception) or "", type(exception).__name__]
    reason = getattr(exception, "reason", None)
    if reason:
        parts.append(str(reason))
    return " ".join(parts).lower()


def _is_timeout(exception: Optional[BaseException]) -> bool:
    if exception is None:
        return False
    if isinstance(exception, _TIMEOUT_TYPES):
        return True
    if isinstance(exception, TimeoutError):  # our own class
        return True
    name = type(exception).__name__.lower()
    if "timeout" in name:
        return True
    return "timed out" in _text_from_exception(exception)


def classify_error(
    status: Optional[int],
    body: str,
    exception: Optional[BaseException] = None,
) -> ApiError:
    """Map a failing request onto a user-friendly error type.

    ``status`` may be provided directly, or inferred from ``exception`` when the
    caller only has the exception object.
    """
    text = (body or "").lower()

    if isinstance(exception, CancelledError):
        return exception

    if _is_timeout(exception):
        return TimeoutError()

    if status is None:
        status = _status_from_exception(exception)

    if status is None:
        # No HTTP status available: this is a transport-level failure.
        return NetworkError()

    if status == 401:
        return AuthenticationError()
    if status == 402:
        return PaymentError()
    if status == 403:
        if any(word in text for word in ("quota", "balance", "arrears", "insufficient")):
            return InsufficientQuotaError()
        if "model" in text and "access" in text:
            return ModelNotFoundError()
        return AuthenticationError(
            "Access denied (403). The key may lack permission for this model or endpoint."
        )
    if status == 404:
        return ModelNotFoundError(
            "Endpoint or model not found (404). Check the base URL and the model ID."
        )
    if status == 408:
        return TimeoutError()
    if status == 429:
        return RateLimitError()
    if status >= 500:
        return ServerError()

    detail = (body or "").strip()
    detail = detail[:200] if detail else ""
    message = f"API error {status}."
    if detail:
        message = f"API error {status}: {detail}"
    return ApiError(message, retryable=False, show_key=False)
