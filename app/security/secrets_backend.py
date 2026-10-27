"""Secure storage backends for the API key.

Storage policy:

* The API key is only ever written to a real platform credential store
  (Windows Credential Manager via ``keyring``, macOS Keychain, Secret Service).
* There is **no** silent plaintext fallback. If no secure backend is usable,
  the app refuses to save the key and tells the user, rather than pretending
  the key was stored safely.
* The in-memory backend exists for tests and is reported as unavailable, so it
  can never be mistaken for durable secure storage.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional


class SecretNotFoundError(Exception):
    """Raised when a secret is not present in the backend."""


class SecretsBackend(ABC):
    """Abstract secure credential storage."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def is_available(self) -> bool:
        ...

    @abstractmethod
    def store(self, service: str, username: str, value: str) -> None:
        ...

    @abstractmethod
    def retrieve(self, service: str, username: str) -> Optional[str]:
        ...

    @abstractmethod
    def delete(self, service: str, username: str) -> bool:
        ...


class InMemorySecretsBackend(SecretsBackend):
    """Non-persistent backend used only for tests.

    ``is_available`` is ``False`` by default: the app must never treat memory as
    safe credential storage, because everything vanishes when it restarts.
    """

    def __init__(self, available: bool = False) -> None:
        self._store: dict[str, dict[str, str]] = {}
        self._available = available

    @property
    def name(self) -> str:
        return "in-memory (not persistent)"

    @property
    def is_available(self) -> bool:
        return self._available

    def store(self, service: str, username: str, value: str) -> None:
        if not self._available:
            raise RuntimeError("The in-memory backend is not enabled.")
        self._store.setdefault(service, {})[username] = value

    def retrieve(self, service: str, username: str) -> Optional[str]:
        return self._store.get(service, {}).get(username)

    def delete(self, service: str, username: str) -> bool:
        if service in self._store and username in self._store[service]:
            del self._store[service][username]
            return True
        return False


class KeyringSecretsBackend(SecretsBackend):
    """Platform credential store accessed through the ``keyring`` package."""

    def __init__(self, keyring_module) -> None:
        self._keyring = keyring_module
        self._backend_name: Optional[str] = None
        self._probe()

    def _probe(self) -> None:
        """Detect whether a real, usable keyring backend is configured."""
        try:
            backend = self._keyring.get_keyring()
        except Exception:
            self._backend_name = None
            return
        module_name = type(backend).__module__ or ""
        # keyring ships a null/fail backend when nothing real is configured.
        if "fail" in module_name.lower() or "null" in module_name.lower():
            self._backend_name = None
            return
        try:
            priority = float(getattr(backend, "priority", 0) or 0)
        except Exception:
            priority = 0.0
        if priority <= 0:
            self._backend_name = None
            return
        self._backend_name = module_name

    @property
    def name(self) -> str:
        if self._backend_name and "windows" in self._backend_name.lower():
            return "Windows Credential Manager"
        if self._backend_name and "macos" in self._backend_name.lower():
            return "macOS Keychain"
        return "system keyring"

    @property
    def is_available(self) -> bool:
        return self._backend_name is not None

    def store(self, service: str, username: str, value: str) -> None:
        self._keyring.set_password(service, username, value)

    def retrieve(self, service: str, username: str) -> Optional[str]:
        try:
            return self._keyring.get_password(service, username)
        except Exception:
            return None

    def delete(self, service: str, username: str) -> bool:
        try:
            self._keyring.delete_password(service, username)
            return True
        except Exception:
            return False


def discover_backends() -> List[SecretsBackend]:
    """Return the credential backends to try, most secure first."""
    backends: List[SecretsBackend] = []

    try:
        import keyring  # type: ignore[import-untyped]
    except Exception:
        keyring = None  # type: ignore[assignment]

    if keyring is not None:
        backends.append(KeyringSecretsBackend(keyring))

    # Always present, never considered usable storage.
    backends.append(InMemorySecretsBackend(available=False))
    return backends


def secure_storage_reason() -> str:
    """Explain why secure storage is or is not available."""
    try:
        import keyring  # type: ignore[import-untyped]

        backend = keyring.get_keyring()
        module_name = type(backend).__module__ or ""
        if "fail" in module_name.lower() or "null" in module_name.lower():
            return (
                "No OS credential backend is configured on this machine. "
                "On Windows, run the app on a normal desktop session so the "
                "Windows Credential Manager is reachable."
            )
        return f"Secure storage is provided by {module_name}."
    except Exception:
        return (
            "The 'keyring' package is not installed, so the API key cannot be "
            "stored in the OS credential store. Install dependencies with "
            "setup.bat, or: pip install -r requirements.txt"
        )
