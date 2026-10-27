"""Tests for database migration and JSON export/import."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.chat_repository import ChatRepository
from app.database.db import SCHEMA_VERSION, database, initialize_schema
from app.database.migration import (
    UnexpectedMigrationPathError,
    UnexpectedPayloadError,
    export_conversations,
    import_conversations,
    migrate,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class MigrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "chat.db"

    def tearDown(self) -> None:
        self._tmp.cleanup()


class TestMigrate(MigrationTestCase):
    def test_no_op_when_already_current(self) -> None:
        with database(self.path) as conn:
            initialize_schema(conn)
        migrate(self.path, str(SCHEMA_VERSION))
        with database(self.path) as conn:
            row = conn.execute(
                "SELECT value FROM schema_meta WHERE key='version'"
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(str(row["value"]), str(SCHEMA_VERSION))

    def test_unknown_previous_version_is_rejected(self) -> None:
        """An unrecognised version must fail loudly instead of overwriting data."""
        with database(self.path) as conn:
            conn.execute("CREATE TABLE schema_meta(key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("INSERT INTO schema_meta(key,value) VALUES('version','99')")
        with self.assertRaises(UnexpectedMigrationPathError):
            migrate(self.path, str(SCHEMA_VERSION))

    def test_failed_migration_keeps_existing_data(self) -> None:
        with database(self.path) as conn:
            initialize_schema(conn)
            conn.execute(
                "INSERT INTO conversations(id,title,created_at,updated_at,system_prompt)"
                " VALUES('c1','Keep me',?,?,'')",
                (_now_iso(), _now_iso()),
            )
            conn.execute("UPDATE schema_meta SET value='99' WHERE key='version'")

        with self.assertRaises(UnexpectedMigrationPathError):
            migrate(self.path, str(SCHEMA_VERSION))

        repo = ChatRepository(self.path)
        self.assertIsNotNone(repo.get_conversation("c1"))


class TestExportImport(MigrationTestCase):
    def _seed(self, title: str = "Hello") -> Path:
        repo = ChatRepository(self.path)
        conversation = repo.create_conversation(title)
        repo.append_message(conversation["id"], "user", "Hi there")
        repo.append_message(conversation["id"], "assistant", "Hello!")
        return self.path

    def test_roundtrip_preserves_conversation_and_messages(self) -> None:
        self._seed()
        payload = export_conversations(self.path)
        self.assertEqual(str(payload["version"]), str(SCHEMA_VERSION))
        self.assertEqual(len(payload["conversations"]), 1)
        self.assertEqual(len(payload["conversations"][0]["messages"]), 2)

        target = Path(self._tmp.name) / "imported.db"
        imported = import_conversations(target, payload)
        self.assertEqual(imported, 1)

        repo = ChatRepository(target)
        conversations = repo.list_conversations()
        self.assertEqual([c["title"] for c in conversations], ["Hello"])
        messages = repo.list_messages(conversations[0]["id"])
        self.assertEqual([m["content"] for m in messages], ["Hi there", "Hello!"])

    def test_import_does_not_delete_existing_data(self) -> None:
        self._seed("Existing")
        payload = export_conversations(self.path)
        import_conversations(self.path, payload)
        repo = ChatRepository(self.path)
        titles = {c["title"] for c in repo.list_conversations()}
        self.assertIn("Existing", titles)

    def test_rejects_non_object_payload(self) -> None:
        repo = ChatRepository(self.path)
        with self.assertRaises(UnexpectedPayloadError):
            import_conversations(self.path, ["not", "an", "object"])

    def test_rejects_wrong_version(self) -> None:
        ChatRepository(self.path)
        with self.assertRaises(UnexpectedPayloadError):
            import_conversations(self.path, {"version": "0", "conversations": []})

    def test_rejects_missing_conversations_key(self) -> None:
        ChatRepository(self.path)
        with self.assertRaises(UnexpectedPayloadError):
            import_conversations(self.path, {"version": SCHEMA_VERSION})

    def test_rejects_malformed_entries_without_partial_write(self) -> None:
        ChatRepository(self.path)
        payload = {
            "version": SCHEMA_VERSION,
            "conversations": [
                {"id": "", "title": "no id"},          # skipped
                {"title": "no id either"},             # skipped
                {
                    "id": "valid",
                    "title": "Valid",
                    "created_at": _now_iso(),
                    "updated_at": _now_iso(),
                    "system_prompt": "",
                    "messages": [
                        {"role": "user", "content": "hi", "row_order": 1},
                        {"role": "tool", "content": "bad role", "row_order": 2},
                    ],
                },
            ],
        }
        imported = import_conversations(self.path, payload)
        self.assertEqual(imported, 1)
        repo = ChatRepository(self.path)
        messages = repo.list_messages("valid")
        # The unsupported role must be skipped, the valid one kept.
        self.assertEqual([m["role"] for m in messages], ["user"])

    def test_export_truncates_very_long_content(self) -> None:
        repo = ChatRepository(self.path)
        conversation = repo.create_conversation("Long")
        repo.append_message(conversation["id"], "user", "x" * 5000)
        payload = export_conversations(self.path, max_content_length=100)
        self.assertEqual(
            len(payload["conversations"][0]["messages"][0]["content"]), 100
        )

    def test_exported_json_is_serialisable(self) -> None:
        import json

        self._seed()
        payload = export_conversations(self.path)
        # The payload must survive a JSON round trip, since that is how backups work.
        restored = json.loads(json.dumps(payload))
        self.assertEqual(restored["version"], payload["version"])


if __name__ == "__main__":
    unittest.main()
