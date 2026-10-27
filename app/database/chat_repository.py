"""Persistence for conversations and messages (SQLite).

Every write goes through :func:`app.database.db.database`, which wraps the work
in a transaction and rolls back on error, so a failed write cannot leave a
half-saved conversation behind.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from app.database.db import database, database_path, initialize_schema


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class ChatRepository:
    """All conversation and message persistence for the app."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._db_path: Path = db_path or database_path()
        self._ensure_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _ensure_schema(self) -> None:
        with database(self._db_path) as conn:
            initialize_schema(conn)

    # ---------------------------------------------------------- conversations

    def list_conversations(self, limit: int = 200) -> List[dict]:
        with database(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, title, created_at, updated_at, system_prompt
                FROM conversations
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [dict(r) for r in rows]

    def search_conversations(self, query: str, limit: int = 100) -> List[dict]:
        """Search conversation titles, ids, and message contents.

        Searching message content is what makes "find that thing I asked last
        week" work; title-only search misses almost everything.
        """
        if not query.strip():
            return self.list_conversations(limit=limit)
        like = f"%{query}%"
        with database(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT c.id, c.title, c.created_at, c.updated_at, c.system_prompt
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id
                WHERE c.title LIKE ? OR c.id LIKE ? OR m.content LIKE ?
                ORDER BY c.updated_at DESC
                LIMIT ?
                """,
                (like, like, like, int(limit)),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_conversation(self, conversation_id: str) -> Optional[dict]:
        with database(self._db_path) as conn:
            row = conn.execute(
                """
                SELECT id, title, created_at, updated_at, system_prompt
                FROM conversations
                WHERE id = ?
                """,
                (conversation_id,),
            ).fetchone()
        return dict(row) if row else None

    def conversation_exists(self, conversation_id: str) -> bool:
        return self.get_conversation(conversation_id) is not None

    def create_conversation(
        self,
        title: str,
        system_prompt: str = "",
        conversation_id: Optional[str] = None,
    ) -> dict:
        now = utc_now_iso()
        cid = conversation_id or str(uuid.uuid4())
        with database(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO conversations(id, title, created_at, updated_at, system_prompt)
                VALUES (?, ?, ?, ?, ?)
                """,
                (cid, title, now, now, system_prompt),
            )
        return {
            "id": cid,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "system_prompt": system_prompt,
        }

    def update_conversation_title(self, conversation_id: str, title: str) -> bool:
        with database(self._db_path) as conn:
            cur = conn.execute(
                """
                UPDATE conversations
                SET title = ?, updated_at = ?
                WHERE id = ?
                """,
                (title, utc_now_iso(), conversation_id),
            )
            return cur.rowcount > 0

    def update_conversation_system_prompt(
        self, conversation_id: str, system_prompt: str
    ) -> bool:
        with database(self._db_path) as conn:
            cur = conn.execute(
                """
                UPDATE conversations
                SET system_prompt = ?, updated_at = ?
                WHERE id = ?
                """,
                (system_prompt, utc_now_iso(), conversation_id),
            )
            return cur.rowcount > 0

    def touch_conversation(self, conversation_id: str) -> None:
        with database(self._db_path) as conn:
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (utc_now_iso(), conversation_id),
            )

    def delete_conversation(self, conversation_id: str) -> bool:
        with database(self._db_path) as conn:
            cur = conn.execute(
                "DELETE FROM conversations WHERE id = ?",
                (conversation_id,),
            )
            return cur.rowcount > 0

    # --------------------------------------------------------------- messages

    def list_messages(self, conversation_id: str) -> List[dict]:
        with database(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, role, content, created_at, row_order
                FROM messages
                WHERE conversation_id = ?
                ORDER BY row_order ASC
                """,
                (conversation_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def append_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
    ) -> int:
        """Append one message and bump the conversation timestamp."""
        now = utc_now_iso()
        with database(self._db_path) as conn:
            row = conn.execute(
                """
                SELECT COALESCE(MAX(row_order), 0) FROM messages
                WHERE conversation_id = ?
                """,
                (conversation_id,),
            ).fetchone()
            next_order = (int(row[0]) if row is not None else 0) + 1
            cur = conn.execute(
                """
                INSERT INTO messages(conversation_id, role, content, created_at, row_order)
                VALUES (?, ?, ?, ?, ?)
                """,
                (conversation_id, role, content, now, next_order),
            )
            message_id = int(cur.lastrowid)
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )
        return message_id

    def update_message_content(self, message_id: int, content: str) -> bool:
        """Overwrite one message body (used while streaming an answer)."""
        with database(self._db_path) as conn:
            cur = conn.execute(
                "UPDATE messages SET content = ? WHERE id = ?",
                (content, int(message_id)),
            )
            return cur.rowcount > 0

    def delete_message(self, message_id: int) -> bool:
        with database(self._db_path) as conn:
            cur = conn.execute("DELETE FROM messages WHERE id = ?", (int(message_id),))
            return cur.rowcount > 0

    def delete_messages(self, conversation_id: str) -> int:
        with database(self._db_path) as conn:
            cur = conn.execute(
                "DELETE FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            )
            return int(cur.rowcount)

    def last_message_with_role(
        self, conversation_id: str, role: str
    ) -> Optional[dict]:
        """Return the newest message with the given role, if any."""
        with database(self._db_path) as conn:
            row = conn.execute(
                """
                SELECT id, role, content, created_at, row_order
                FROM messages
                WHERE conversation_id = ? AND role = ?
                ORDER BY row_order DESC
                LIMIT 1
                """,
                (conversation_id, role),
            ).fetchone()
        return dict(row) if row else None

    def count_messages(self, conversation_id: str) -> int:
        with database(self._db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        return int(row[0]) if row is not None else 0

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def generate_initial_title(first_user_message: str, max_length: int = 80) -> str:
        """Build a short conversation title from the first message.

        Only the first line is used, and it is truncated rather than rewritten:
        the title should stay recognisably the user's own words.
        """
        text = (first_user_message or "").strip()
        if not text:
            return "New conversation"
        first_line = text.split("\n", 1)[0].strip()
        if not first_line:
            return "New conversation"
        if len(first_line) > max_length:
            first_line = first_line[: max_length - 3].rstrip() + "..."
        return first_line or "New conversation"
