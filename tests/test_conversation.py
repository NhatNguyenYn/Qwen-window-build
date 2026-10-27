"""Tests for the conversation service.

These use a real SQLite repository in a temporary directory rather than a mock,
because the original defect in this area was a mismatch between the service and
the repository API — a mock would have hidden it.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.chat_repository import ChatRepository
from app.services.conversation import ConversationService, DEFAULT_TITLE
from app.services.state import RequestState


class FakeClient:
    """Stand-in for QwenApiClient; records nothing but satisfies the interface."""

    def stream_chat_completion(self, request, token=None):
        yield "unused"

    def test_connection(self):
        return {"models": [], "count": 0, "message": "ok"}


class ConversationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._db = Path(self._tmp.name) / "chat.db"
        self.repo = ChatRepository(self._db)
        self.service = ConversationService(self.repo, FakeClient())

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _send(self, conversation_id: str, text: str, **kwargs):
        defaults = dict(
            model="qwen-turbo",
            temperature=0.0,
            max_tokens=128,
            request_timeout_seconds=30.0,
        )
        defaults.update(kwargs)
        return self.service.send_message(conversation_id, text, **defaults)


class TestConversationLifecycle(ConversationTestCase):
    def test_new_conversation_is_persisted_and_active(self) -> None:
        conversation_id = self.service.new_conversation(system_prompt="Be brief.")
        self.assertTrue(conversation_id)
        self.assertEqual(self.service.active_id, conversation_id)
        stored = self.repo.get_conversation(conversation_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored["system_prompt"], "Be brief.")

    def test_set_active_rejects_unknown(self) -> None:
        self.assertFalse(self.service.set_active("does-not-exist"))

    def test_set_active_accepts_existing(self) -> None:
        conversation_id = self.service.new_conversation()
        self.service.close_active()
        self.assertTrue(self.service.set_active(conversation_id))
        self.assertEqual(self.service.active_id, conversation_id)

    def test_rename_and_delete(self) -> None:
        conversation_id = self.service.new_conversation()
        self.assertTrue(self.service.rename(conversation_id, "Renamed"))
        self.assertEqual(self.repo.get_conversation(conversation_id)["title"], "Renamed")
        self.assertTrue(self.service.delete(conversation_id))
        self.assertIsNone(self.service.active_id)

    def test_rename_rejects_blank(self) -> None:
        conversation_id = self.service.new_conversation()
        self.assertFalse(self.service.rename(conversation_id, "   "))

    def test_delete_all_removes_everything(self) -> None:
        self.service.new_conversation()
        self.service.new_conversation()
        removed = self.service.delete_all()
        self.assertEqual(removed, 2)
        self.assertEqual(self.service.list_recent(), [])
        self.assertIsNone(self.service.active_id)

    def test_list_recent_forwards_limit(self) -> None:
        for _ in range(3):
            self.service.new_conversation()
        self.assertEqual(len(self.service.list_recent(limit=2)), 2)

    def test_search_matches_message_content(self) -> None:
        """Searching history must look inside messages, not just titles."""
        conversation_id = self.service.new_conversation()
        self._send(conversation_id, "How do I configure the flux capacitor?")
        results = self.service.search("flux capacitor")
        self.assertTrue(any(r["id"] == conversation_id for r in results))


class TestSendMessage(ConversationTestCase):
    def test_send_persists_user_and_assistant_placeholder(self) -> None:
        conversation_id = self.service.new_conversation()
        handle = self._send(conversation_id, "Hello there")

        messages = self.repo.list_messages(conversation_id)
        self.assertEqual([m["role"] for m in messages], ["user", "assistant"])
        self.assertEqual(messages[0]["content"], "Hello there")
        self.assertEqual(messages[1]["content"], "")
        self.assertEqual(handle.assistant_message_id, messages[1]["id"])

    def test_request_contains_system_prompt_and_history(self) -> None:
        conversation_id = self.service.new_conversation(system_prompt="Be terse.")
        handle = self._send(conversation_id, "Hi")
        request = handle.request
        self.assertEqual(request.model, "qwen-turbo")
        self.assertEqual(request.messages[0].role, "system")
        self.assertEqual(request.messages[0].content, "Be terse.")
        self.assertEqual(request.messages[-1].content, "Hi")
        self.assertTrue(request.stream)

    def test_system_prompt_override_wins(self) -> None:
        conversation_id = self.service.new_conversation(system_prompt="Original")
        handle = self._send(conversation_id, "Hi", system_prompt_override="Override")
        self.assertEqual(handle.request.messages[0].content, "Override")

    def test_empty_system_prompt_omits_system_message(self) -> None:
        conversation_id = self.service.new_conversation(system_prompt="")
        handle = self._send(conversation_id, "Hi", system_prompt_override="")
        roles = [m.role for m in handle.request.messages]
        self.assertNotIn("system", roles)

    def test_title_is_generated_from_first_message(self) -> None:
        conversation_id = self.service.new_conversation()
        self._send(conversation_id, "Explain quantum tunnelling simply")
        stored = self.repo.get_conversation(conversation_id)
        self.assertEqual(stored["title"], "Explain quantum tunnelling simply")

    def test_history_does_not_leak_across_conversations(self) -> None:
        """A request must never include another conversation's messages."""
        first = self.service.new_conversation()
        self._send(first, "secret from conversation one")
        second = self.service.new_conversation()
        handle = self._send(second, "message in conversation two")

        contents = [m.content for m in handle.request.messages]
        self.assertNotIn("secret from conversation one", contents)
        self.assertEqual(handle.request.messages[-1].content, "message in conversation two")

    def test_empty_message_rejected(self) -> None:
        conversation_id = self.service.new_conversation()
        with self.assertRaises(ValueError):
            self._send(conversation_id, "   ")

    def test_unknown_conversation_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._send("no-such-conversation", "hello")

    def test_context_limit_is_respected(self) -> None:
        self.service.max_context_messages = 2
        conversation_id = self.service.new_conversation()
        for index in range(5):
            self._send(conversation_id, f"message {index}")
        handle = self._send(conversation_id, "latest")
        non_system = [m for m in handle.request.messages if m.role != "system"]
        self.assertLessEqual(len(non_system), 2)

    def test_empty_assistant_placeholder_is_not_sent_to_api(self) -> None:
        conversation_id = self.service.new_conversation()
        self._send(conversation_id, "first")
        handle = self._send(conversation_id, "second")
        # The blank assistant slot from the first exchange must be filtered out.
        contents = [m.content for m in handle.request.messages]
        self.assertNotIn("", contents)


class TestRetry(ConversationTestCase):
    def test_retry_does_not_duplicate_user_message(self) -> None:
        conversation_id = self.service.new_conversation()
        self._send(conversation_id, "only once")
        before = self.repo.list_messages(conversation_id)

        handle = self.service.retry_last_message(conversation_id)
        self.assertIsNotNone(handle)
        after = self.repo.list_messages(conversation_id)

        user_messages = [m for m in after if m["role"] == "user"]
        self.assertEqual(len(user_messages), 1, "retry must not resend a new user message")
        self.assertEqual(len(after), len(before))
        self.assertEqual(handle.user_message_id, user_messages[0]["id"])

    def test_retry_without_user_message_returns_none(self) -> None:
        conversation_id = self.service.new_conversation()
        self.assertIsNone(self.service.retry_last_message(conversation_id))

    def test_retry_reuses_empty_assistant_slot(self) -> None:
        conversation_id = self.service.new_conversation()
        self._send(conversation_id, "question")
        handle = self.service.retry_last_message(conversation_id)
        assistants = [
            m for m in self.repo.list_messages(conversation_id) if m["role"] == "assistant"
        ]
        self.assertEqual(len(assistants), 1)
        self.assertEqual(handle.assistant_message_id, assistants[0]["id"])

    def test_retry_after_filled_answer_adds_new_slot(self) -> None:
        conversation_id = self.service.new_conversation()
        handle = self._send(conversation_id, "question")
        self.service.store_assistant_text(handle.assistant_message_id, "an answer")
        retry_handle = self.service.retry_last_message(conversation_id)
        assistants = [
            m for m in self.repo.list_messages(conversation_id) if m["role"] == "assistant"
        ]
        self.assertEqual(len(assistants), 2)
        self.assertNotEqual(retry_handle.assistant_message_id, handle.assistant_message_id)


class TestRequestStateTracking(ConversationTestCase):
    def test_state_progresses_to_completed(self) -> None:
        conversation_id = self.service.new_conversation()
        handle = self._send(conversation_id, "hi")
        self.assertTrue(self.service.has_active_request())

        self.service.mark_streaming(handle)
        self.assertEqual(self.service.active_request_state(), RequestState.STREAMING)

        self.service.finish_request(handle, RequestState.COMPLETED)
        self.assertFalse(self.service.has_active_request())

    def test_cancelled_state(self) -> None:
        conversation_id = self.service.new_conversation()
        handle = self._send(conversation_id, "hi")
        self.service.mark_streaming(handle)
        self.service.finish_request(handle, RequestState.CANCELLED)
        self.assertFalse(self.service.has_active_request())

    def test_cancel_pending_aborts_token(self) -> None:
        conversation_id = self.service.new_conversation()
        handle = self._send(conversation_id, "hi")
        self.assertFalse(handle.abort_token.is_aborted())
        self.assertTrue(self.service.cancel_pending())
        self.assertTrue(handle.abort_token.is_aborted())

    def test_on_close_aborts_in_flight(self) -> None:
        conversation_id = self.service.new_conversation()
        handle = self._send(conversation_id, "hi")
        self.service.on_close()
        self.assertTrue(handle.abort_token.is_aborted())
        self.assertTrue(self.service.close_requested)

    def test_finishing_an_unknown_handle_is_safe(self) -> None:
        conversation_id = self.service.new_conversation()
        handle = self._send(conversation_id, "hi")
        self.service.finish_request(handle, RequestState.COMPLETED)
        # Finishing twice must not raise.
        self.service.finish_request(handle, RequestState.COMPLETED)


class TestPartialContentPersistence(ConversationTestCase):
    def test_partial_answer_is_kept(self) -> None:
        """A cancelled request must not lose the text that already arrived."""
        conversation_id = self.service.new_conversation()
        handle = self._send(conversation_id, "hi")
        self.service.store_assistant_text(handle.assistant_message_id, "partial ans")
        stored = self.repo.list_messages(conversation_id)[-1]
        self.assertEqual(stored["content"], "partial ans")

    def test_messages_survive_a_new_repository_instance(self) -> None:
        """Reopening the database must return the same history."""
        conversation_id = self.service.new_conversation()
        handle = self._send(conversation_id, "persist me")
        self.service.store_assistant_text(handle.assistant_message_id, "saved answer")

        reopened = ChatRepository(self._db)
        messages = reopened.list_messages(conversation_id)
        self.assertEqual([m["content"] for m in messages], ["persist me", "saved answer"])


if __name__ == "__main__":
    unittest.main()
