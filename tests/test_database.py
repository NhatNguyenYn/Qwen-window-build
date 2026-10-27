"""Tests for the SQLite repository layer."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.chat_repository import ChatRepository
from app.database.db import database_path, initialize_schema, database


class TestDatabase(unittest.TestCase):
    def setUp(self) -> None:
        fd, self._path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._path = self._path.replace("\\", "/")
        self._repo = ChatRepository(db_path=self._path)

    def tearDown(self) -> None:
        try:
            os.remove(self._path)
        except Exception:
            pass

    def test_create_and_retrieve_conversation(self) -> None:
        conv = self._repo.create_conversation("Test chat")
        self.assertEqual(conv["title"], "Test chat")
        self.assertTrue(conv["id"])
        found = self._repo.get_conversation(conv["id"])
        self.assertIsNotNone(found)
        self.assertEqual(found["title"], "Test chat")

    def test_list_and_search(self) -> None:
        id1 = self._repo.create_conversation("Alpha")["id"]
        id2 = self._repo.create_conversation("Beta")["id"]
        self._repo.create_conversation("Gamma")
        convs = self._repo.list_conversations()
        titles = [c["title"] for c in convs]
        self.assertIn("Alpha", titles)
        self.assertIn("Beta", titles)
        results = self._repo.search_conversations("Beta")
        self.assertTrue(any(c["id"] == id2 for c in results))
        results = self._repo.search_conversations("missing")
        self.assertEqual(len(results), 0)

    def test_messages_roundtrip(self) -> None:
        conv = self._repo.create_conversation("Msg test")
        self._repo.append_message(conv["id"], "user", "Hello")
        self._repo.append_message(conv["id"], "assistant", "Hi there")
        messages = self._repo.list_messages(conv["id"])
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["content"], "Hello")
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[1]["content"], "Hi there")

    def test_rename_and_delete(self) -> None:
        conv = self._repo.create_conversation("Old")
        ok = self._repo.update_conversation_title(conv["id"], "New")
        self.assertTrue(ok)
        self.assertEqual(self._repo.get_conversation(conv["id"])["title"], "New")
        ok = self._repo.delete_conversation(conv["id"])
        self.assertTrue(ok)
        self.assertIsNone(self._repo.get_conversation(conv["id"]))

    def test_title_generation(self) -> None:
        self.assertEqual(
            self._repo.generate_initial_title("How do I write a test?"),
            "How do I write a test?",
        )
        self.assertEqual(
            self._repo.generate_initial_title("Short prompt"),
            "Short prompt",
        )
        self.assertEqual(
            self._repo.generate_initial_title("   "),
            "New conversation",
        )

    def test_schema_initialization_idempotent(self) -> None:
        with database(self._path) as conn:
            initialize_schema(conn)
            row = conn.execute(
                "SELECT value FROM schema_meta WHERE key='version'"
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["value"], "1")

    def test_delete_cascades_messages(self) -> None:
        conv = self._repo.create_conversation("Cascade")
        self._repo.append_message(conv["id"], "user", "x")
        self._repo.append_message(conv["id"], "assistant", "y")
        self._repo.delete_conversation(conv["id"])
        self.assertEqual(self._repo.list_messages(conv["id"]), [])


if __name__ == "__main__":
    unittest.main()
