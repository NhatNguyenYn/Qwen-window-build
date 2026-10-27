"""Left sidebar: conversation list, search, new chat, connect, status, settings.

The sidebar is a dumb view: it emits intent signals and never talks to the
database or the API itself. The controller decides what each action means.
"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

SEARCH_DEBOUNCE_MS = 250
COLLAPSED_WIDTH = 0


class Sidebar(QWidget):
    """Conversation sidebar."""

    conversation_selected = Signal(str)
    new_chat_requested = Signal()
    search_requested = Signal(str)
    rename_requested = Signal(str)
    delete_requested = Signal(str)
    clear_history_requested = Signal()
    connect_requested = Signal()
    settings_requested = Signal()
    toggle_requested = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._collapsed = False
        self._conversations: List[dict] = []
        self._selected_id: Optional[str] = None
        self._width = 280

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(SEARCH_DEBOUNCE_MS)
        self._search_timer.timeout.connect(self._emit_search)

        self._build_ui()

    # --------------------------------------------------------------- building

    def _build_ui(self) -> None:
        self.setMinimumWidth(200)
        self.setMaximumWidth(420)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addWidget(self._build_search())
        root.addWidget(self._list_area(), 1)
        root.addWidget(self._build_footer())

    def _build_header(self) -> QWidget:
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(12, 12, 8, 8)
        layout.setSpacing(8)

        title = QLabel("Qwen Desktop Chat")
        title.setStyleSheet("font-size: 13px; font-weight: 600;")
        layout.addWidget(title, 1)

        self._collapse_btn = QToolButton()
        self._collapse_btn.setText("◀")
        self._collapse_btn.setToolTip("Collapse sidebar")
        self._collapse_btn.setCursor(Qt.PointingHandCursor)
        self._collapse_btn.setStyleSheet(
            "QToolButton { border: none; padding: 2px 6px; border-radius: 5px; }"
            "QToolButton:hover { background-color: rgba(127,127,127,0.18); }"
        )
        self._collapse_btn.clicked.connect(self._toggle_collapsed)
        layout.addWidget(self._collapse_btn, 0, Qt.AlignRight)
        return header

    def _build_search(self) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(10, 0, 10, 8)
        layout.setSpacing(6)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search title or message text…")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.textChanged.connect(lambda _: self._search_timer.start())
        layout.addWidget(self._search_input)
        return wrapper

    def _list_area(self) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(8, 0, 8, 4)
        layout.setSpacing(4)

        self._list = QListWidget()
        self._list.setSpacing(2)
        self._list.setWordWrap(True)
        self._list.setUniformItemSizes(False)
        self._list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._show_context_menu)
        self._list.itemClicked.connect(self._on_item_activated)
        self._list.itemActivated.connect(self._on_item_activated)
        layout.addWidget(self._list, 1)
        return wrapper

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        layout = QVBoxLayout(footer)
        layout.setContentsMargins(10, 6, 10, 10)
        layout.setSpacing(6)

        self._new_btn = QPushButton("+  New chat")
        self._new_btn.setProperty("variant", "primary")
        self._new_btn.setCursor(Qt.PointingHandCursor)
        self._new_btn.clicked.connect(self.new_chat_requested.emit)
        layout.addWidget(self._new_btn)

        self._connect_btn = QPushButton("Connect Qwen API")
        self._connect_btn.setCursor(Qt.PointingHandCursor)
        self._connect_btn.clicked.connect(self.connect_requested.emit)
        layout.addWidget(self._connect_btn)

        status_row = QWidget()
        status_layout = QHBoxLayout(status_row)
        status_layout.setContentsMargins(0, 2, 0, 0)
        status_layout.setSpacing(6)

        self._status_dot = QLabel()
        self._status_dot.setFixedSize(8, 8)
        self._status_dot.setStyleSheet(
            "background-color: #71717a; border-radius: 4px;"
        )
        status_layout.addWidget(self._status_dot, 0, Qt.AlignLeft)

        self._status_text = QLabel("Not connected")
        self._status_text.setStyleSheet("color: #71717a; font-size: 11px;")
        status_layout.addWidget(self._status_text, 1)
        layout.addWidget(status_row)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet("color: #3f3f46;")
        layout.addWidget(divider)

        self._settings_btn = QPushButton("Settings")
        self._settings_btn.setCursor(Qt.PointingHandCursor)
        self._settings_btn.clicked.connect(self.settings_requested.emit)
        layout.addWidget(self._settings_btn)
        return footer

    # ---------------------------------------------------------------- behaviour

    def _toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)
        self.toggle_requested.emit(self._collapsed)

    def _emit_search(self) -> None:
        self.search_requested.emit(self._search_input.text())

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        conversation_id = item.data(Qt.UserRole)
        if isinstance(conversation_id, str) and conversation_id:
            self._selected_id = conversation_id
            self.conversation_selected.emit(conversation_id)

    def _show_context_menu(self, position) -> None:
        item = self._list.itemAt(position)
        if item is None:
            return
        conversation_id = item.data(Qt.UserRole)
        if not isinstance(conversation_id, str) or not conversation_id:
            return

        menu = QMenu(self)
        open_action = menu.addAction("Open")
        rename_action = menu.addAction("Rename…")
        menu.addSeparator()
        delete_action = menu.addAction("Delete…")

        chosen = menu.exec(self._list.mapToGlobal(position))
        if chosen is open_action:
            self._on_item_activated(item)
        elif chosen is rename_action:
            self.rename_requested.emit(conversation_id)
        elif chosen is delete_action:
            self.delete_requested.emit(conversation_id)

    # ------------------------------------------------------------------- state

    def set_conversations(self, conversations: List[dict]) -> None:
        """Replace the list contents.

        Accepts plain dicts (repository rows) and objects carrying the same
        attributes, so a service change cannot silently blank the list.
        """
        self._conversations = [self._as_dict(c) for c in conversations]
        self._refresh_list()

    @staticmethod
    def _as_dict(conversation) -> dict:
        if isinstance(conversation, dict):
            return conversation
        return {
            "id": getattr(conversation, "id", ""),
            "title": getattr(conversation, "title", "Untitled"),
        }

    def _refresh_list(self) -> None:
        self._list.clear()
        if not self._conversations:
            placeholder = QListWidgetItem("No conversations yet.")
            placeholder.setFlags(Qt.NoItemFlags)
            placeholder.setForeground(Qt.gray)
            self._list.addItem(placeholder)
            return
        for conversation in self._conversations:
            title = conversation.get("title") or "Untitled"
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, conversation.get("id"))
            item.setToolTip(title)
            item.setSizeHint(item.sizeHint().expandedTo(item.sizeHint()))
            self._list.addItem(item)

    def select_conversation(self, conversation_id: str) -> None:
        for index in range(self._list.count()):
            item = self._list.item(index)
            if item.data(Qt.UserRole) == conversation_id:
                self._list.setCurrentItem(item)
                self._selected_id = conversation_id
                return

    def selected_conversation_id(self) -> Optional[str]:
        return self._selected_id

    def set_status(self, state: str, message: str = "") -> None:
        colors = {
            "connected": "#4ade80",
            "connecting": "#7dd3fc",
            "busy": "#7dd3fc",
            "error": "#f87171",
            "disconnected": "#71717a",
        }
        color = colors.get(state, "#71717a")
        self._status_dot.setStyleSheet(
            f"background-color: {color}; border-radius: 4px;"
        )
        self._status_text.setText(message or state.capitalize())
        self._status_text.setStyleSheet(f"color: {color}; font-size: 11px;")

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = bool(collapsed)
        self._collapse_btn.setText("▶" if self._collapsed else "◀")

    def is_collapsed(self) -> bool:
        return self._collapsed

    def preferred_width(self) -> int:
        return self._width

    def set_sensitive(self, enabled: bool) -> None:
        self._new_btn.setEnabled(enabled)
        self._connect_btn.setEnabled(enabled)
