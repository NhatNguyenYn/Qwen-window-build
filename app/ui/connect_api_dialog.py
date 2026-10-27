"""Connect Qwen API dialog.

Fields: provider, API key (masked, with show/hide), base URL, model, and the
Test / Save actions. The connection test runs on a worker thread so the dialog
never freezes while a request is in flight.

The stored key is never displayed: when a key already exists the field stays
empty and is used only if the user types a replacement.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.api.errors import ApiError, classify_error

if TYPE_CHECKING:  # pragma: no cover
    from app.api.client import QwenApiClient
    from app.config.settings import AppSettings
    from app.security.credentials import CredentialsManager

CUSTOM_MODEL_LABEL = "Custom…"


class _TestSignals(QObject):
    succeeded = Signal(dict)
    failed = Signal(object)


class _ConnectionTestTask(QRunnable):
    """Verify the key/endpoint off the UI thread."""

    def __init__(self, client: "QwenApiClient", signals: _TestSignals) -> None:
        super().__init__()
        self._client = client
        self._signals = signals
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        try:
            result = self._client.test_connection()
        except ApiError as exc:
            self._signals.failed.emit(exc)
            return
        except Exception as exc:  # noqa: BLE001 - surface a typed error instead
            self._signals.failed.emit(classify_error(None, str(exc), exc))
            return
        self._signals.succeeded.emit(result)


class ConnectApiDialog(QDialog):
    """Modal dialog for entering and verifying the API credentials."""

    def __init__(
        self,
        settings: "AppSettings",
        credentials: "CredentialsManager",
        client_factory: Callable[[str, str], "QwenApiClient"],
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._credentials = credentials
        self._client_factory = client_factory
        self._testing = False
        self._connected = False

        self.setWindowTitle("Connect Qwen API")
        self.setModal(True)
        self.setMinimumWidth(520)

        self._test_signals = _TestSignals()
        self._test_signals.succeeded.connect(self._on_test_succeeded)
        self._test_signals.failed.connect(self._on_test_failed)

        self._build_ui()
        self._load_current_state()

    # --------------------------------------------------------------- building

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        intro = QLabel(
            "Paste your Qwen API key and connect. Get a key from Alibaba Cloud "
            "Model Studio (DashScope) — it usually starts with “sk-”. The key is "
            "stored in the operating system credential store on this machine, "
            "never in the chat history, the settings file, or any log."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #a1a1aa; font-size: 12px;")
        layout.addWidget(intro)

        # 1. Provider
        provider_box = QGroupBox("1. Provider")
        provider_layout = QVBoxLayout(provider_box)
        self._provider_combo = QComboBox()
        self._provider_combo.addItem("Qwen (DashScope, OpenAI-compatible)")
        provider_layout.addWidget(self._provider_combo)
        layout.addWidget(provider_box)

        # 2. API key
        key_box = QGroupBox("2. API key")
        key_layout = QVBoxLayout(key_box)
        key_row = QHBoxLayout()
        self._key_input = QLineEdit()
        self._key_input.setPlaceholderText("sk-…")
        self._key_input.setEchoMode(QLineEdit.Password)
        key_row.addWidget(self._key_input, 1)
        self._show_key_btn = QPushButton("Show")
        self._show_key_btn.setFixedWidth(70)
        self._show_key_btn.setCheckable(True)
        self._show_key_btn.toggled.connect(self._on_toggle_key_visibility)
        key_row.addWidget(self._show_key_btn)
        key_layout.addLayout(key_row)

        self._key_hint = QLabel("")
        self._key_hint.setWordWrap(True)
        self._key_hint.setStyleSheet("color: #71717a; font-size: 11px;")
        key_layout.addWidget(self._key_hint)
        layout.addWidget(key_box)

        # 3. Endpoint + model
        endpoint_box = QGroupBox("3. Endpoint and model (advanced)")
        endpoint_layout = QVBoxLayout(endpoint_box)

        base_row = QHBoxLayout()
        base_row.addWidget(QLabel("Base URL:"))
        self._base_url = QLineEdit()
        base_row.addWidget(self._base_url, 1)
        endpoint_layout.addLayout(base_row)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Model:"))
        self._model_combo = QComboBox()
        model_row.addWidget(self._model_combo, 1)
        endpoint_layout.addLayout(model_row)

        self._model_edit = QLineEdit()
        self._model_edit.setPlaceholderText("Custom model ID (used when Model = Custom…)")
        endpoint_layout.addWidget(self._model_edit)

        note = QLabel(
            "The default is the mainland-China endpoint "
            "(dashscope.aliyuncs.com). If your Alibaba Cloud Model Studio "
            "account is international, use "
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1 instead, "
            "and pick the model IDs your account can access."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #71717a; font-size: 11px;")
        endpoint_layout.addWidget(note)
        layout.addWidget(endpoint_box)

        # Actions
        actions = QHBoxLayout()
        self._test_btn = QPushButton("Test Connection")
        self._test_btn.clicked.connect(self._on_test_clicked)
        actions.addWidget(self._test_btn)

        self._save_btn = QPushButton("Save & Connect")
        self._save_btn.setProperty("variant", "primary")
        self._save_btn.clicked.connect(self._on_save_clicked)
        actions.addWidget(self._save_btn)
        actions.addStretch(1)
        layout.addLayout(actions)

        # Status
        status_box = QGroupBox("Connection status")
        status_layout = QVBoxLayout(status_box)
        self._status_label = QLabel("Not connected")
        status_layout.addWidget(self._status_label)
        self._detail_label = QLabel("")
        self._detail_label.setWordWrap(True)
        status_layout.addWidget(self._detail_label)
        layout.addWidget(status_box)

        self._disconnect_btn = QPushButton("Disconnect & remove stored key")
        self._disconnect_btn.clicked.connect(self._on_disconnect_clicked)
        self._disconnect_btn.setVisible(False)
        layout.addWidget(self._disconnect_btn)

        self._buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self._buttons.rejected.connect(self.reject)
        self._buttons.clicked.connect(lambda _: self.reject())
        layout.addWidget(self._buttons)

    # ---------------------------------------------------------- initial state

    def _load_current_state(self) -> None:
        self._base_url.setText(self._settings.base_url)

        models = list(self._settings.available_models) or [self._settings.model]
        self._model_combo.clear()
        for model in models:
            self._model_combo.addItem(model)
        self._model_combo.addItem(CUSTOM_MODEL_LABEL)
        index = self._model_combo.findText(self._settings.model)
        if index >= 0:
            self._model_combo.setCurrentIndex(index)
        else:
            self._model_combo.setCurrentText(CUSTOM_MODEL_LABEL)
            self._model_edit.setText(self._settings.model)

        storage = self._credentials.storage_description()
        if storage["available"]:
            self._key_hint.setText(storage["message"])
        else:
            self._key_hint.setText(storage["message"])
            self._key_hint.setStyleSheet("color: #fbbf24; font-size: 11px;")

        if self._credentials.has_stored_key():
            self._connected = True
            self._key_input.setPlaceholderText(
                "A key is already stored. Type a new one to replace it."
            )
            self._set_status("Connected", "green")
            self._set_detail(
                "An API key is already stored on this device. Use the test "
                "button to verify it still works.",
                "muted",
            )
            self._disconnect_btn.setVisible(self._credentials.can_store_securely)

    # ------------------------------------------------------------- UI helpers

    def _set_status(self, text: str, tone: str = "muted") -> None:
        colors = {
            "muted": "#71717a",
            "busy": "#7dd3fc",
            "ok": "#4ade80",
            "error": "#f87171",
        }
        color = colors.get(tone, "#71717a")
        self._status_label.setText(text)
        self._status_label.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 600;")

    def _set_detail(self, text: str, tone: str = "muted") -> None:
        colors = {
            "muted": "#a1a1aa",
            "ok": "#4ade80",
            "error": "#f87171",
        }
        self._detail_label.setText(text)
        self._detail_label.setStyleSheet(
            f"color: {colors.get(tone, '#a1a1aa')}; font-size: 12px;"
        )

    def _on_toggle_key_visibility(self, shown: bool) -> None:
        self._key_input.setEchoMode(QLineEdit.Normal if shown else QLineEdit.Password)
        self._show_key_btn.setText("Hide" if shown else "Show")

    def current_model(self) -> str:
        """Resolve the chosen model, preferring a typed custom ID."""
        typed = self._model_edit.text().strip()
        selected = self._model_combo.currentText().strip()
        if selected and selected != CUSTOM_MODEL_LABEL:
            # A typed value wins over the dropdown so custom IDs are not ignored.
            return typed or selected
        return typed

    def _current_base_url(self) -> str:
        return self._base_url.text().strip() or self._settings.base_url

    def _set_busy(self, busy: bool) -> None:
        self._testing = busy
        self._test_btn.setEnabled(not busy)
        self._save_btn.setEnabled(not busy)
        self._test_btn.setText("Testing…" if busy else "Test Connection")

    # -------------------------------------------------------------- testing

    def _on_test_clicked(self) -> None:
        api_key = self._key_input.text().strip()
        if not api_key and not self._credentials.has_stored_key():
            QMessageBox.warning(
                self, "Missing API key", "Paste your Qwen API key first."
            )
            self._key_input.setFocus()
            return
        model = self.current_model()
        if not model:
            QMessageBox.warning(
                self, "Missing model", "Select or type a model ID to test."
            )
            return

        base = self._current_base_url()
        if not base.lower().startswith(("http://", "https://")):
            QMessageBox.warning(
                self,
                "Invalid base URL",
                "The base URL must start with http:// or https://.",
            )
            return
        if base.lower().startswith("http://") and "localhost" not in base and "127.0.0.1" not in base:
            QMessageBox.warning(
                self,
                "Unencrypted endpoint",
                "You are using plain HTTP. Anyone on your network could read "
                "your API key. Use HTTPS unless you accept that risk.",
            )

        self._set_busy(True)
        self._set_status("Testing connection…", "busy")
        self._set_detail("Contacting the endpoint and listing models.", "muted")

        try:
            client = self._client_factory(api_key or (self._credentials.get_key() or ""), base)
        except Exception as exc:
            self._set_busy(False)
            self._on_test_failed(classify_error(None, str(exc), exc))
            return

        QThreadPool.globalInstance().start(
            _ConnectionTestTask(client, self._test_signals)
        )

    @Slot(dict)
    def _on_test_succeeded(self, result: dict) -> None:
        self._set_busy(False)
        self._connected = True
        self._set_status("Connected", "ok")
        models = result.get("models") or []
        if models:
            shown = ", ".join(models[:12])
            self._set_detail(
                f"Endpoint reachable. {len(models)} model(s) visible: {shown}",
                "ok",
            )
        else:
            self._set_detail(
                "Endpoint reachable, but it listed no models. Check the base URL.",
                "ok",
            )

    @Slot(object)
    def _on_test_failed(self, error: object) -> None:
        self._set_busy(False)
        message = error.message if isinstance(error, ApiError) else str(error)
        retryable = error.retryable if isinstance(error, ApiError) else True
        self._set_status("Error", "error")
        hint = " You can press Test Connection again." if retryable else ""
        self._set_detail(f"{message}{hint}", "error")

    # ----------------------------------------------------------------- saving

    def _on_save_clicked(self) -> None:
        api_key = self._key_input.text().strip()
        has_stored = self._credentials.has_stored_key()
        if not api_key and not has_stored:
            QMessageBox.warning(
                self, "Missing API key", "Paste your Qwen API key first."
            )
            self._key_input.setFocus()
            return

        model = self.current_model()
        if not model:
            QMessageBox.warning(
                self, "Missing model", "Select or type a model ID to save."
            )
            return

        base = self._current_base_url()
        if not base.lower().startswith(("http://", "https://")):
            QMessageBox.warning(
                self,
                "Invalid base URL",
                "The base URL must start with http:// or https://.",
            )
            return

        if api_key:
            try:
                backend_name, message = self._credentials.store_key(api_key)
            except (RuntimeError, ValueError) as exc:
                QMessageBox.critical(
                    self,
                    "Cannot save key",
                    "The API key could not be stored securely, so it was not "
                    f"saved.\n\n{exc}",
                )
                return
            self._key_input.clear()
            self._key_hint.setText(message)
            self._key_hint.setStyleSheet("color: #4ade80; font-size: 11px;")

        self._settings.base_url = base.rstrip("/")
        self._settings.model = model
        if model not in self._settings.available_models:
            self._settings.available_models = list(self._settings.available_models) + [model]
        self._settings.provider = "Qwen"

        self._set_status("Saved", "ok")
        self._set_detail(
            "Settings saved. Close this window to start chatting.", "ok"
        )
        self._disconnect_btn.setVisible(self._credentials.can_store_securely)
        self.accept()

    def _on_disconnect_clicked(self) -> None:
        answer = QMessageBox.question(
            self,
            "Disconnect",
            "Remove the stored API key from this device?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._credentials.delete_key()
        self._connected = False
        self._key_input.clear()
        self._disconnect_btn.setVisible(False)
        self._set_status("Disconnected", "muted")
        self._set_detail("The stored key has been removed from this device.", "muted")

    # ------------------------------------------------------------------ state

    def is_connected(self) -> bool:
        return self._connected
