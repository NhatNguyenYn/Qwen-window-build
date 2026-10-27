"""High-level API credential policy.

The API key is never written to the settings file, the SQLite database, or any
log. It only lives in the operating system credential store, and only when a
real credential backend is available.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from app.security.secrets_backend import (
    SecretsBackend,
    discover_backends,
    secure_storage_reason,
)

SERVICE_NAME = "QwenDesktopChat"
USERNAME_KEY = "api-key"


class CredentialsManager:
    """Read, write and delete the stored API key."""

    def __init__(self, backends: Optional[List[SecretsBackend]] = None) -> None:
        self._backends: List[SecretsBackend] = (
            backends if backends is not None else discover_backends()
        )

    @property
    def usable_backends(self) -> List[SecretsBackend]:
        return [b for b in self._backends if b.is_available]

    @property
    def preferred_backend(self) -> Optional[SecretsBackend]:
        usable = self.usable_backends
        return usable[0] if usable else None

    @property
    def can_store_securely(self) -> bool:
        return self.preferred_backend is not None

    @property
    def reason(self) -> str:
        return secure_storage_reason()

    def store_key(self, api_key: str) -> Tuple[str, str]:
        """Persist the key and return ``(backend_name, user_message)``."""
        key = (api_key or "").strip()
        if not key:
            raise ValueError("The API key is empty.")
        backend = self.preferred_backend
        if backend is None:
            raise RuntimeError(self.reason)
        try:
            backend.store(SERVICE_NAME, USERNAME_KEY, key)
        except Exception as exc:
            raise RuntimeError(
                f"Could not store the API key in {backend.name}: {exc}"
            ) from exc
        return backend.name, f"API key saved to {backend.name}."

    def get_key(self) -> Optional[str]:
        for backend in self._backends:
            try:
                key = backend.retrieve(SERVICE_NAME, USERNAME_KEY)
            except Exception:
                continue
            if key:
                return key
        return None

    def has_stored_key(self) -> bool:
        return bool(self.get_key())

    def delete_key(self) -> bool:
        """Remove the stored key. Reports success of the first backend that had it."""
        removed_any = False
        for backend in self._backends:
            try:
                if backend.delete(SERVICE_NAME, USERNAME_KEY):
                    removed_any = True
            except Exception:
                continue
        return removed_any

    def storage_description(self) -> dict:
        """Describe storage options for display in the connect dialog."""
        if not self.can_store_securely:
            return {
                "available": False,
                "backend": None,
                "message": (
                    "No secure credential storage is available, so the app will "
                    "not save your API key. You can still paste the key each "
                    "session.\n\n" + self.reason
                ),
            }
        backend = self.preferred_backend
        return {
            "available": True,
            "backend": backend.name if backend else None,
            "message": (
                f"Your API key will be saved in {backend.name if backend else 'the system keyring'}. "
                "It is never written to the chat history or the settings file."
            ),
        }
