"""Conversation lifecycle and request orchestration.

This module owns the chat workflow: creating conversations, tracking the active
conversation, persisting messages, and assembling the request that will be sent
to the API. It contains no Qt code, so it can be exercised in tests with a fake
repository and a fake client.

Invariants that matter for correctness:

* A request is built only from the messages of its own conversation.
* Only ``role`` and ``content`` ever reach the API; UI metadata never does.
* A finished or superseded request can never write into a newer conversation.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, List, Optional

from app.api.client import (
    AbortToken,
    ApiClient,
    ChatMessage,
    CompletionRequest,
)
from app.database.chat_repository import ChatRepository
from app.services.state import (
    InFlightRequest,
    RequestState,
    StateTransitionError,
    finish_in_flight,
)

# How many past messages to replay to the model. Sending an unbounded history
# eventually exceeds the model context window and costs money for nothing.
DEFAULT_MAX_CONTEXT_MESSAGES = 40
DEFAULT_TITLE = "New conversation"


@dataclass
class SendHandle:
    """Everything the UI needs to track one outgoing request."""

    conversation_id: str
    request: CompletionRequest
    assistant_message_id: int
    request_id: str
    abort_token: AbortToken = field(default_factory=AbortToken)
    user_message_id: Optional[int] = None

    # Historical aliases so older call sites keep working.
    @property
    def _request(self) -> CompletionRequest:
        return self.request

    @property
    def abort_handle(self) -> AbortToken:
        return self.abort_token


class ConversationService:
    """High-level conversation workflow."""

    def __init__(
        self,
        repository: ChatRepository,
        client: ApiClient,
        *,
        max_context_messages: int = DEFAULT_MAX_CONTEXT_MESSAGES,
    ) -> None:
        self.repository = repository
        self.client = client
        self.max_context_messages = int(max_context_messages)
        self.active_id: Optional[str] = None
        self._in_flight: dict[str, InFlightRequest] = {}
        self._pending: Optional[SendHandle] = None
        self._close_requested = False

    # ---------------------------------------------------------- conversations

    def new_conversation(
        self,
        title: str = DEFAULT_TITLE,
        system_prompt: str = "",
    ) -> str:
        """Create a conversation and make it active."""
        record = self.repository.create_conversation(title, system_prompt)
        self.active_id = record["id"]
        return str(record["id"])

    def set_active(self, conversation_id: str) -> bool:
        if not self.repository.conversation_exists(conversation_id):
            return False
        self.active_id = conversation_id
        return True

    def close_active(self) -> None:
        """Forget the active conversation (used after deleting all history)."""
        self.active_id = None

    def rename(self, conversation_id: str, title: str) -> bool:
        cleaned = (title or "").strip()
        if not cleaned:
            return False
        return self.repository.update_conversation_title(conversation_id, cleaned)

    def delete(self, conversation_id: str) -> bool:
        removed = self.repository.delete_conversation(conversation_id)
        if removed and self.active_id == conversation_id:
            self.active_id = None
        return removed

    def delete_all(self) -> int:
        """Delete every conversation. Returns how many were removed."""
        removed = 0
        for conversation in self.repository.list_conversations(limit=100000):
            if self.repository.delete_conversation(conversation["id"]):
                removed += 1
        self.active_id = None
        return removed

    def get_conversation(self, conversation_id: str) -> Optional[dict]:
        return self.repository.get_conversation(conversation_id)

    def list_recent(self, limit: int = 50) -> List[dict]:
        return self.repository.list_conversations(limit=limit)

    def search(self, query: str, limit: int = 100) -> List[dict]:
        return self.repository.search_conversations(query, limit=limit)

    def messages(self, conversation_id: str) -> List[dict]:
        return self.repository.list_messages(conversation_id)

    def set_system_prompt(self, conversation_id: str, system_prompt: str) -> bool:
        return self.repository.update_conversation_system_prompt(
            conversation_id, system_prompt
        )

    # --------------------------------------------------------------- requests

    def _resolve_system_prompt(
        self,
        conversation: dict,
        override: Optional[str],
    ) -> str:
        if override is not None:
            return override
        return conversation.get("system_prompt") or ""

    def _build_messages(
        self,
        conversation_id: str,
        system_prompt: str,
    ) -> List[ChatMessage]:
        """Assemble the message list for the API from this conversation only.

        A trailing empty assistant placeholder is dropped: it exists only as a
        place for streamed text to land, and the API must not see it.
        """
        stored = self.repository.list_messages(conversation_id)
        usable = [
            m for m in stored
            if (m.get("content") or "").strip()
            and m.get("role") in ("user", "assistant")
        ]
        if self.max_context_messages > 0:
            usable = usable[-self.max_context_messages:]

        messages: List[ChatMessage] = []
        if system_prompt.strip():
            messages.append(ChatMessage(role="system", content=system_prompt))
        for row in usable:
            messages.append(
                ChatMessage(role=row["role"], content=row["content"])
            )
        return messages

    def build_request(
        self,
        conversation_id: str,
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        request_timeout_seconds: float,
        system_prompt_override: Optional[str] = None,
    ) -> CompletionRequest:
        conversation = self.repository.get_conversation(conversation_id)
        if conversation is None:
            raise ValueError(f"Conversation {conversation_id} not found.")
        system_prompt = self._resolve_system_prompt(conversation, system_prompt_override)
        return CompletionRequest(
            model=model,
            messages=self._build_messages(conversation_id, system_prompt),
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            request_timeout_seconds=request_timeout_seconds,
        )

    def _register(
        self,
        conversation_id: str,
        request: CompletionRequest,
        assistant_message_id: int,
        user_message_id: Optional[int],
    ) -> SendHandle:
        request_id = str(uuid.uuid4())
        handle = SendHandle(
            conversation_id=conversation_id,
            request=request,
            assistant_message_id=assistant_message_id,
            request_id=request_id,
            user_message_id=user_message_id,
        )
        self._in_flight[request_id] = InFlightRequest(
            request_id=request_id,
            conversation_id=conversation_id,
            assistant_message_id=assistant_message_id,
            state=RequestState.IDLE,
            abort_handle=handle.abort_token,
        )
        self._pending = handle
        return handle

    def send_message(
        self,
        conversation_id: str,
        user_message: str,
        *,
        model: str = "qwen-turbo",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        request_timeout_seconds: float = 60.0,
        system_prompt_override: Optional[str] = None,
    ) -> SendHandle:
        """Persist the user message and prepare the outgoing request."""
        text = (user_message or "").strip()
        if not text:
            raise ValueError("Cannot send an empty message.")

        conversation = self.repository.get_conversation(conversation_id)
        if conversation is None:
            raise ValueError(f"Conversation {conversation_id} not found.")

        user_message_id = self.repository.append_message(
            conversation_id, "user", text
        )

        # Name an untitled conversation after its first user message.
        existing_title = (conversation.get("title") or "").strip()
        if existing_title in ("", DEFAULT_TITLE):
            generated = self.repository.generate_initial_title(text)
            if generated and generated != existing_title:
                self.repository.update_conversation_title(conversation_id, generated)
                conversation["title"] = generated

        assistant_message_id = self.repository.append_message(
            conversation_id, "assistant", ""
        )
        request = self.build_request(
            conversation_id,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            request_timeout_seconds=request_timeout_seconds,
            system_prompt_override=system_prompt_override,
        )
        return self._register(
            conversation_id, request, assistant_message_id, user_message_id
        )

    def retry_last_message(
        self,
        conversation_id: str,
        *,
        model: str = "qwen-turbo",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        request_timeout_seconds: float = 60.0,
        system_prompt_override: Optional[str] = None,
    ) -> Optional[SendHandle]:
        """Re-run the newest user message without inserting a duplicate.

        Retrying deliberately reuses the stored user message, so a retry cannot
        silently send the same prompt twice and double the cost.
        """
        last_user = self.repository.last_message_with_role(conversation_id, "user")
        if last_user is None:
            return None

        # Reuse the newest assistant slot if it is empty, otherwise add one.
        last_assistant = self.repository.last_message_with_role(
            conversation_id, "assistant"
        )
        if last_assistant is not None and not (last_assistant.get("content") or "").strip():
            assistant_message_id = int(last_assistant["id"])
        else:
            assistant_message_id = self.repository.append_message(
                conversation_id, "assistant", ""
            )

        request = self.build_request(
            conversation_id,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            request_timeout_seconds=request_timeout_seconds,
            system_prompt_override=system_prompt_override,
        )
        return self._register(
            conversation_id,
            request,
            assistant_message_id,
            int(last_user["id"]),
        )

    # ------------------------------------------------- request state tracking

    def mark_streaming(self, handle: SendHandle) -> None:
        inflight = self._in_flight.get(handle.request_id)
        if inflight is None or inflight.state != RequestState.IDLE:
            return
        try:
            inflight.transition(RequestState.CONNECTING)
            inflight.transition(RequestState.STREAMING)
        except StateTransitionError:
            pass

    def finish_request(self, handle: SendHandle, state: str) -> None:
        inflight = self._in_flight.pop(handle.request_id, None)
        if inflight is None:
            return
        if inflight.state != state:
            try:
                inflight.transition(state)
            except StateTransitionError:
                inflight.state = state
        finish_in_flight(inflight)
        if self._pending is handle:
            self._pending = None

    def cancel_pending(self) -> bool:
        """Cancel the request currently being streamed, if any."""
        handle = self._pending
        if handle is None:
            return False
        handle.abort_token.abort()
        return True

    def active_request_state(self) -> Optional[str]:
        if self._pending is None:
            return None
        inflight = self._in_flight.get(self._pending.request_id)
        return inflight.state if inflight is not None else None

    def has_active_request(self) -> bool:
        state = self.active_request_state()
        return state is not None and not RequestState.is_terminal(state)

    def on_close(self) -> None:
        """Abort anything in flight because the window is closing."""
        self._close_requested = True
        self.cancel_pending()

    @property
    def close_requested(self) -> bool:
        return self._close_requested

    # ---------------------------------------------- assistant message writing

    def store_assistant_text(self, message_id: int, text: str) -> bool:
        """Persist streamed assistant text for a message.

        Called during streaming (throttled by the caller) and once more when the
        request finishes, so a cancelled or failed request keeps whatever text
        did arrive.
        """
        return self.repository.update_message_content(message_id, text)
