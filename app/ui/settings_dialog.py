"""Settings dialog.

Groups: connection, model parameters, appearance, chat preferences, data
management, and advanced request options.

Cancel leaves the stored settings untouched: the values are only copied back
onto the live settings object when the user confirms.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:  # pragma: no cover
    from app.config.settings import AppSettings
    from app.database.chat_repository import ChatRepository
    from app.security.credentials import CredentialsManager
    from app.services.conversation import ConversationService

CUSTOM_MODEL_LABEL = "Custom…"


class SettingsDialog(QDialog):
    """Modal settings editor."""

    export_requested = Signal()
    import_requested = Signal()

    def __init__(
        self,
        settings: "AppSettings",
        conversation_service: "ConversationService",
        repository: "ChatRepository",
        credentials_manager: "CredentialsManager",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._service = conversation_service
        self._repo = repository
        self._credentials = credentials_manager

        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumSize(560, 640)

        self._build_ui()
        self._load_values()

    # --------------------------------------------------------------- building

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        layout.addWidget(self._build_connection_group())
        layout.addWidget(self._build_model_group())
        layout.addWidget(self._build_appearance_group())
        layout.addWidget(self._build_chat_group())
        layout.addWidget(self._build_system_prompt_group())
        layout.addWidget(self._build_data_group())
        layout.addStretch(1)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self._on_accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _build_connection_group(self) -> QGroupBox:
        box = QGroupBox("API connection")
        form = QFormLayout(box)
        form.setContentsMargins(12, 16, 12, 12)
        form.setSpacing(8)

        self._base_url = QLineEdit()
        self._base_url.setPlaceholderText(
            "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        form.addRow("Base URL:", self._base_url)

        self._timeout = QDoubleSpinBox()
        self._timeout.setRange(5.0, 600.0)
        self._timeout.setSingleStep(5.0)
        self._timeout.setDecimals(1)
        self._timeout.setSuffix(" s")
        form.addRow("Request timeout:", self._timeout)

        key_state = QLabel()
        if self._credentials.has_stored_key():
            key_state.setText("An API key is stored on this device.")
            key_state.setStyleSheet("color: #4ade80; font-size: 11px;")
        else:
            key_state.setText(
                "No API key stored yet — use “Connect Qwen API” in the sidebar."
            )
            key_state.setStyleSheet("color: #fbbf24; font-size: 11px;")
        key_state.setWordWrap(True)
        form.addRow("", key_state)
        return box

    def _build_model_group(self) -> QGroupBox:
        box = QGroupBox("Model parameters")
        form = QFormLayout(box)
        form.setContentsMargins(12, 16, 12, 12)
        form.setSpacing(8)

        self._model_combo = QComboBox()
        form.addRow("Model:", self._model_combo)

        self._model_edit = QLineEdit()
        self._model_edit.setPlaceholderText(
            "Custom model ID (used when Model = Custom…)"
        )
        form.addRow("Custom ID:", self._model_edit)
        self._model_combo.currentTextChanged.connect(self._on_model_changed)

        self._temperature = QDoubleSpinBox()
        self._temperature.setRange(0.0, 2.0)
        self._temperature.setSingleStep(0.1)
        self._temperature.setDecimals(2)
        form.addRow("Temperature:", self._temperature)

        self._max_tokens = QSpinBox()
        self._max_tokens.setRange(16, 200_000)
        self._max_tokens.setSingleStep(256)
        form.addRow("Max output tokens:", self._max_tokens)
        return box

    def _build_appearance_group(self) -> QGroupBox:
        box = QGroupBox("Appearance")
        form = QFormLayout(box)
        form.setContentsMargins(12, 16, 12, 12)
        form.setSpacing(8)

        theme_row = QWidget()
        theme_layout = QHBoxLayout(theme_row)
        theme_layout.setContentsMargins(0, 0, 0, 0)
        self._theme_buttons = QButtonGroup(self)
        self._dark_radio = QRadioButton("Dark")
        self._light_radio = QRadioButton("Light")
        self._theme_buttons.addButton(self._dark_radio, 0)
        self._theme_buttons.addButton(self._light_radio, 1)
        theme_layout.addWidget(self._dark_radio)
        theme_layout.addWidget(self._light_radio)
        theme_layout.addStretch(1)
        form.addRow("Theme:", theme_row)

        self._font_scale = QDoubleSpinBox()
        self._font_scale.setRange(0.8, 1.6)
        self._font_scale.setSingleStep(0.05)
        self._font_scale.setDecimals(2)
        self._font_scale.setSuffix(" ×")
        form.addRow("Font scale:", self._font_scale)
        return box

    def _build_chat_group(self) -> QGroupBox:
        box = QGroupBox("Chat preferences")
        form = QFormLayout(box)
        form.setContentsMargins(12, 16, 12, 12)
        form.setSpacing(8)

        self._context_limit = QSpinBox()
        self._context_limit.setRange(4, 200)
        self._context_limit.setSingleStep(2)
        form.addRow("Messages sent as context:", self._context_limit)

        hint = QLabel(
            "Only the most recent messages are replayed to the model. A smaller "
            "number is faster and cheaper; a larger number keeps more context."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #71717a; font-size: 11px;")
        form.addRow("", hint)
        return box

    def _build_system_prompt_group(self) -> QGroupBox:
        box = QGroupBox("System prompt")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 16, 12, 12)

        self._system_prompt = QPlainTextEdit()
        self._system_prompt.setPlaceholderText("You are a helpful assistant…")
        self._system_prompt.setFixedHeight(110)
        layout.addWidget(self._system_prompt)
        return box

    def _build_data_group(self) -> QGroupBox:
        box = QGroupBox("Data management")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(8)

        info = QLabel(f"History database:\n{self._repo.db_path}")
        info.setWordWrap(True)
        info.setStyleSheet("color: #71717a; font-size: 11px;")
        layout.addWidget(info)

        row = QHBoxLayout()
        export_btn = QPushButton("Export history…")
        export_btn.clicked.connect(self.export_requested.emit)
        row.addWidget(export_btn)

        import_btn = QPushButton("Import history…")
        import_btn.clicked.connect(self.import_requested.emit)
        row.addWidget(import_btn)
        row.addStretch(1)
        layout.addLayout(row)

        note = QLabel(
            "Exports are JSON files. Importing only adds conversations; it never "
            "overwrites or deletes existing ones."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #71717a; font-size: 11px;")
        layout.addWidget(note)
        return box

    # ------------------------------------------------------------ load/save

    def _load_values(self) -> None:
        settings = self._settings
        self._base_url.setText(settings.base_url)
        self._timeout.setValue(float(settings.request_timeout_seconds))

        models = list(settings.available_models) or [settings.model]
        self._model_combo.clear()
        for model in models:
            self._model_combo.addItem(model)
        self._model_combo.addItem(CUSTOM_MODEL_LABEL)
        index = self._model_combo.findText(settings.model)
        if index >= 0:
            self._model_combo.setCurrentIndex(index)
        else:
            self._model_combo.setCurrentText(CUSTOM_MODEL_LABEL)
            self._model_edit.setText(settings.model)

        self._temperature.setValue(float(settings.temperature))
        self._max_tokens.setValue(int(settings.max_tokens))
        (self._dark_radio if settings.theme == "dark" else self._light_radio).setChecked(True)
        self._font_scale.setValue(float(settings.chat_font_scale))
        self._context_limit.setValue(int(self._settings.max_context_messages))
        self._system_prompt.setPlainText(settings.system_prompt)

    def _on_model_changed(self, text: str) -> None:
        self._model_edit.setEnabled(text == CUSTOM_MODEL_LABEL)

    def current_model(self) -> str:
        """Resolve the model, preferring a typed custom ID."""
        typed = self._model_edit.text().strip()
        selected = self._model_combo.currentText().strip()
        if selected and selected != CUSTOM_MODEL_LABEL:
            return typed or selected
        return typed

    def _current_theme(self) -> str:
        return "dark" if self._dark_radio.isChecked() else "light"

    def _on_accept(self) -> None:
        model = self.current_model()
        if not model:
            QMessageBox.warning(
                self, "Missing model", "Select or type a model ID."
            )
            return

        base_url = self._base_url.text().strip()
        if not base_url:
            QMessageBox.warning(
                self, "Missing endpoint", "Enter the API base URL."
            )
            self._base_url.setFocus()
            return
        if not base_url.lower().startswith(("http://", "https://")):
            QMessageBox.warning(
                self,
                "Invalid URL",
                "The base URL must start with http:// or https://.",
            )
            return
        if (
            base_url.lower().startswith("http://")
            and "localhost" not in base_url
            and "127.0.0.1" not in base_url
        ):
            QMessageBox.warning(
                self,
                "Unencrypted endpoint",
                "That endpoint uses plain HTTP, so your API key would travel "
                "unencrypted. Use HTTPS unless you accept that risk.",
            )

        self._settings.provider = "Qwen"
        self._settings.base_url = base_url.rstrip("/")
        self._settings.model = model
        if model not in self._settings.available_models:
            self._settings.available_models = (
                list(self._settings.available_models) + [model]
            )
        self._settings.temperature = float(self._temperature.value())
        self._settings.max_tokens = int(self._max_tokens.value())
        self._settings.request_timeout_seconds = float(self._timeout.value())
        self._settings.theme = self._current_theme()
        self._settings.chat_font_scale = float(self._font_scale.value())
        self._settings.system_prompt = self._system_prompt.toPlainText().strip()
        self._settings.max_context_messages = int(self._context_limit.value())
        self._service.max_context_messages = int(self._context_limit.value())
        self.accept()
