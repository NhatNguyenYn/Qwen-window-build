"""Chat area: message list, markdown rendering, input box, send/stop controls.

The message list is a ``QScrollArea`` holding a ``QVBoxLayout`` container. Each
message is a widget (a :class:`MarkdownWidget`), so widgets do not need to be
crammed into a rich-text document.

Auto-scrolling follows the user: new output scrolls into view only when the user
is already at the bottom, so reading earlier text is never interrupted.
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.markdown_widget import MarkdownWidget


class ChatView(QWidget):
    """The conversation pane."""

    send_requested = Signal(str)
    stop_requested = Signal()
    retry_requested = Signal()

    def __init__(
        self,
        markdown_factory: Callable[[str], QWidget] = MarkdownWidget,
    ) -> None:
        super().__init__()
        self._markdown_factory = markdown_factory
        self._active_conversation_id: Optional[str] = None
        self._conversation_title: str = "New conversation"
        self._busy = False
        self._stream_block: Optional[MarkdownWidget] = None
        self._stream_wrapper: Optional[QWidget] = None
        self._build_ui()

    # --------------------------------------------------------------- building

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addWidget(self._build_message_area(), 1)
        root.addWidget(self._build_composer(), 0)

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("chatHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(10)

        self._title_label = QLabel(self._conversation_title)
        self._title_label.setStyleSheet(
            "font-size: 13px; font-weight: 600; background: transparent;"
        )
        self._title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self._title_label, 1)

        self._model_label = QLabel("")
        self._model_label.setStyleSheet(
            "font-size: 11px; color: #71717a; background: transparent;"
        )
        layout.addWidget(self._model_label, 0, Qt.AlignRight)
        return header

    def _build_message_area(self) -> QWidget:
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._container = QWidget()
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(16, 12, 16, 12)
        self._container_layout.setSpacing(14)
        self._container_layout.addStretch(1)
        self._scroll.setWidget(self._container)
        return self._scroll

    def _build_composer(self) -> QWidget:
        composer = QWidget()
        layout = QVBoxLayout(composer)
        layout.setContentsMargins(16, 8, 16, 12)
        layout.setSpacing(6)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #71717a; font-size: 11px;")
        layout.addWidget(self._status_label)

        row = QHBoxLayout()
        row.setSpacing(8)

        self._input = QPlainTextEdit()
        self._input.setObjectName("chatInput")
        self._input.setProperty("role", "input")
        self._input.setPlaceholderText(
            "Message Qwen…  (Enter to send, Shift+Enter for a new line)"
        )
        self._input.setFixedHeight(92)
        self._input.installEventFilter(self)
        row.addWidget(self._input, 1)

        buttons = QVBoxLayout()
        buttons.setSpacing(6)

        self._send_btn = QPushButton("Send")
        self._send_btn.setProperty("variant", "primary")
        self._send_btn.setFixedWidth(96)
        self._send_btn.setCursor(Qt.PointingHandCursor)
        self._send_btn.clicked.connect(self._emit_send)
        buttons.addWidget(self._send_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setFixedWidth(96)
        self._stop_btn.setCursor(Qt.PointingHandCursor)
        self._stop_btn.clicked.connect(self.stop_requested.emit)
        self._stop_btn.setVisible(False)
        buttons.addWidget(self._stop_btn)

        buttons.addStretch(1)
        row.addLayout(buttons)
        layout.addLayout(row)
        return composer

    # ---------------------------------------------------------------- helpers

    def _insert(self, widget: QWidget) -> None:
        """Append a message widget just above the trailing stretch."""
        stick_to_bottom = self.is_at_bottom()
        self._container_layout.insertWidget(
            self._container_layout.count() - 1, widget
        )
        if stick_to_bottom:
            QTimer.singleShot(0, self._scroll_to_bottom)

    def _make_bubble(self, role: str) -> tuple[QWidget, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName(f"bubble_{role}")
        frame.setStyleSheet(
            "QFrame#bubble_user { border: 1px solid #3f3f46; border-radius: 10px;"
            " border-left: 3px solid #2563eb; }"
            "QFrame#bubble_assistant { border: 1px solid #3f3f46; border-radius: 10px;"
            " border-left: 3px solid #4ade80; }"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 10)
        layout.setSpacing(4)

        caption = QLabel("You" if role == "user" else "Qwen")
        color = "#2563eb" if role == "user" else "#4ade80"
        caption.setStyleSheet(
            f"color: {color}; font-size: 11px; font-weight: 600;"
            " border: none; background: transparent;"
        )
        layout.addWidget(caption)
        return frame, layout

    def _is_near_bottom(self) -> bool:
        bar = self._scroll.verticalScrollBar()
        return bar.value() >= bar.maximum() - 24

    # Public alias kept for callers that ask about scroll position.
    def is_at_bottom(self) -> bool:
        return self._is_near_bottom()

    def _scroll_to_bottom(self) -> None:
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    # ----------------------------------------------------------- conversation

    def set_conversation(self, conversation_id: str, title: str, model: str = "") -> None:
        self._active_conversation_id = conversation_id or None
        self._conversation_title = title or "New conversation"
        self._title_label.setText(self._conversation_title)
        self._model_label.setText(f"model: {model}" if model else "")
        self.set_status("", "")

    def conversation_title(self) -> str:
        return self._conversation_title

    def active_conversation_id(self) -> Optional[str]:
        return self._active_conversation_id

    def clear(self) -> None:
        self._stream_block = None
        self._stream_wrapper = None
        while self._container_layout.count() > 1:
            item = self._container_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def show_welcome(self) -> None:
        self.clear()
        banner = QFrame()
        banner.setStyleSheet(
            "QFrame { border: 1px dashed #3f3f46; border-radius: 12px; }"
        )
        layout = QVBoxLayout(banner)
        layout.setContentsMargins(24, 28, 24, 28)
        layout.setSpacing(8)

        heading = QLabel("Chat with Qwen from your desktop")
        heading.setAlignment(Qt.AlignCenter)
        heading.setStyleSheet(
            "font-size: 16px; font-weight: 600; border: none; background: transparent;"
        )
        layout.addWidget(heading)

        body = QLabel(
            "Start typing below to begin a new conversation.\n\n"
            "If you have not connected a key yet, use “Connect Qwen API” in the sidebar.\n"
            "Your conversations are stored locally and stay on this machine."
        )
        body.setAlignment(Qt.AlignCenter)
        body.setWordWrap(True)
        body.setStyleSheet(
            "color: #a1a1aa; font-size: 12px; border: none; background: transparent;"
        )
        layout.addWidget(body)

        self._container_layout.insertWidget(0, banner)

    # --------------------------------------------------------------- messages

    def add_user_message(self, text: str) -> None:
        frame, layout = self._make_bubble("user")
        layout.addWidget(self._markdown_factory(text))
        self._insert(frame)

    def add_assistant_message(self, text: str) -> None:
        frame, layout = self._make_bubble("assistant")
        block = self._markdown_factory(text)
        layout.addWidget(block)
        layout.addLayout(self._copy_row(block, frame))
        self._insert(frame)

    def _copy_row(self, block, frame) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch(1)
        copy_btn = QToolButton()
        copy_btn.setText("Copy")
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.setStyleSheet(
            "QToolButton { color: #71717a; background: transparent; border: none;"
            " padding: 2px 8px; border-radius: 5px; font-size: 11px; }"
            "QToolButton:hover { color: #4ade80; background-color: rgba(127,127,127,0.15); }"
        )
        copy_btn.clicked.connect(lambda: self._copy_block(block, copy_btn))
        row.addWidget(copy_btn, 0, Qt.AlignRight)
        return row

    @staticmethod
    def _copy_block(block, button) -> None:
        text = block.markdown() if hasattr(block, "markdown") else ""
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
        button.setText("Copied")
        QTimer.singleShot(1500, lambda: button.setText("Copy"))

    # -------------------------------------------------------------- streaming

    def begin_assistant_message(self) -> None:
        """Create the assistant bubble that streamed text will fill."""
        frame, layout = self._make_bubble("assistant")
        block = self._markdown_factory("")
        if hasattr(block, "set_plain"):
            block.set_plain(True)
        layout.addWidget(block)
        layout.addLayout(self._copy_row(block, frame))
        self._insert(frame)
        self._stream_wrapper = frame
        self._stream_block = block
        self.set_status("Thinking…", "busy")

    def append_streaming(self, text: str) -> None:
        if self._stream_block is None:
            self.begin_assistant_message()
        if self._stream_block is None:
            return
        if hasattr(self._stream_block, "set_markdown"):
            self._stream_block.set_markdown(text)
        if self._status_label.text() == "Thinking…":
            self.set_status("Streaming…", "busy")

    def end_streaming(
        self,
        *,
        final_text: Optional[str] = None,
        incomplete: bool = False,
        note: str = "",
    ) -> None:
        """Finish the streaming bubble and switch to full markdown rendering."""
        block = self._stream_block
        wrapper = self._stream_wrapper
        self._stream_block = None
        self._stream_wrapper = None
        if block is None:
            return

        text = final_text if final_text is not None else (
            block.markdown() if hasattr(block, "markdown") else ""
        )
        if not text.strip():
            # Nothing arrived: drop the empty bubble instead of leaving a blank card.
            if wrapper is not None:
                self._container_layout.removeWidget(wrapper)
                wrapper.setParent(None)
                wrapper.deleteLater()
            return

        if hasattr(block, "set_plain"):
            block.set_plain(False)
        if hasattr(block, "set_markdown"):
            block.set_markdown(text)

        if incomplete and note:
            if wrapper is not None and wrapper.layout() is not None:
                flag = QLabel(f"⚠ {note}")
                flag.setWordWrap(True)
                flag.setStyleSheet(
                    "color: #fbbf24; font-size: 11px; border: none; background: transparent;"
                )
                wrapper.layout().addWidget(flag)

    # ----------------------------------------------------------------- errors

    def add_error_block(
        self, title: str, detail: str, *, show_retry: bool = True
    ) -> None:
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { border: 1px solid #7f1d1d; border-radius: 10px;"
            " background-color: rgba(127,29,29,0.18); }"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        heading = QLabel(f"⚠ {title}")
        heading.setStyleSheet(
            "color: #f87171; font-weight: 600; font-size: 12px;"
            " border: none; background: transparent;"
        )
        layout.addWidget(heading)

        body = QLabel(detail)
        body.setWordWrap(True)
        body.setStyleSheet(
            "color: #d4d4d8; font-size: 12px; border: none; background: transparent;"
        )
        layout.addWidget(body)

        if show_retry:
            row = QHBoxLayout()
            row.addStretch(1)
            retry = QPushButton("Try again")
            retry.setFixedWidth(100)
            retry.setCursor(Qt.PointingHandCursor)
            retry.clicked.connect(self.retry_requested.emit)
            row.addWidget(retry, 0, Qt.AlignRight)
            layout.addLayout(row)

        self._insert(frame)

    # ------------------------------------------------------------------ state

    def set_busy(self, busy: bool) -> None:
        """Enable/disable the composer and toggle Send vs Stop."""
        self._busy = bool(busy)
        self._send_btn.setVisible(not self._busy)
        self._send_btn.setEnabled(not self._busy)
        self._stop_btn.setVisible(self._busy)
        self._stop_btn.setEnabled(self._busy)
        self._input.setEnabled(not self._busy)
        if not self._busy:
            self._input.setFocus()

    def is_busy(self) -> bool:
        return self._busy

    def set_status(self, text: str, kind: str = "") -> None:
        colors = {
            "busy": "#7dd3fc",
            "error": "#f87171",
            "done": "#4ade80",
        }
        color = colors.get(kind, "#71717a")
        self._status_label.setText(text)
        self._status_label.setStyleSheet(f"color: {color}; font-size: 11px;")

    def focus_input(self) -> None:
        self._input.setFocus()

    # ----------------------------------------------------------------- events

    def _emit_send(self) -> None:
        if self._busy:
            return
        text = self._input.toPlainText().strip()
        if not text:
            return
        self.send_requested.emit(text)
        self._input.clear()

    def eventFilter(self, obj, event) -> bool:
        if obj is self._input and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if event.modifiers() & Qt.ShiftModifier:
                    return False
                self._emit_send()
                return True
        return super().eventFilter(obj, event)
