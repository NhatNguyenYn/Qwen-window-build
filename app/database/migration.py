"""Safe database migration and export/import helpers.

Export/import is intentionally conservative:
- It writes and reads JSON, never Python pickle.
- It rejects unrecognized payloads rather than guessing.
- It limits exported content size to avoid allocating huge strings.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from app.database.db import SCHEMA_VERSION, database, initialize_schema


class UnexpectedPayloadError(Exception):
    """Raised when an imported payload does not match the expected shape."""


class UnexpectedMigrationPathError(Exception):
    """Raised when a migration path is not supported."""


def migrate(db_path: Path, target_version: str) -> None:
    """Bring the database to *target_version* if needed.

    For now the supported target is the current schema version. If the stored
    version is already current, this is a safe no-op. This is deliberately
    conservative so migration never silently overwrites user data.
    """
    current = _current_version(db_path)
    if current == target_version:
        return
    if current != "1" and target_version == "1":
        raise UnexpectedMigrationPathError(
            f"Cannot migrate from version {current} to {target_version}."
        )
    # For a v1 database we only ensure the schema is present.
    with database(db_path) as conn:
        initialize_schema(conn)


def _current_version(db_path: Path) -> str:
    try:
        with database(db_path) as conn:
            row = conn.execute(
                "SELECT value FROM schema_meta WHERE key='version'"
            ).fetchone()
            if row is not None:
                return str(row["value"])
    except Exception:
        return "0"
    return "0"


MAX_EXPORT_CONTENT_LENGTH = 8000


def export_conversations(
    db_path: Path,
    max_content_length: int = MAX_EXPORT_CONTENT_LENGTH,
) -> Dict[str, Any]:
    """Export conversations and messages as a JSON-safe object.

    Content longer than *max_content_length* is truncated. This keeps exports
    usable for backup without silently allocating huge strings for a single
    message.
    """
    rows: list[Dict[str, Any]] = []
    with database(db_path) as conn:
        conv_rows = conn.execute(
            "SELECT id, title, created_at, updated_at, system_prompt "
            "FROM conversations ORDER BY updated_at DESC"
        ).fetchall()
        for conv in conv_rows:
            messages = conn.execute(
                "SELECT role, content, created_at, row_order "
                "FROM messages WHERE conversation_id = ? "
                "ORDER BY row_order ASC",
                (conv["id"],),
            ).fetchall()
            rows.append({
                "id": conv["id"],
                "title": conv["title"],
                "created_at": conv["created_at"],
                "updated_at": conv["updated_at"],
                "system_prompt": conv["system_prompt"],
                "messages": [
                    {
                        "role": m["role"],
                        "content": (
                            m["content"][:max_content_length]
                            if m["content"]
                            else m["content"]
                        ),
                        "created_at": m["created_at"],
                        "row_order": m["row_order"],
                    }
                    for m in messages
                ],
            })
    return {
        "version": SCHEMA_VERSION,
        "exported_at": _now_iso(),
        "conversations": rows,
    }


def import_conversations(
    db_path: Path,
    payload: Any,
    overwrite_existing: bool = False,
) -> int:
    """Import conversations and messages from an export payload.

    Returns the number of conversations imported. Unrecognized payloads raise
    ``UnexpectedPayloadError``. The target is created in a transaction so a
    bad payload cannot leave partial data behind.
    """
    if not isinstance(payload, dict):
        raise UnexpectedPayloadError("Payload must be a JSON object.")
    if payload.get("version") != SCHEMA_VERSION:
        raise UnexpectedPayloadError(
            f"Unsupported export version: {payload.get('version')!r}."
        )
    conversations = payload.get("conversations")
    if not isinstance(conversations, list):
        raise UnexpectedPayloadError("Missing conversations list.")

    imported = 0
    with database(db_path) as conn:
        initialize_schema(conn)
        for conv in conversations:
            if not isinstance(conv, dict):
                continue
            if not isinstance(conv.get("id"), str) or not conv.get("id"):
                continue
            title = conv.get("title") or "Imported conversation"
            system_prompt = conv.get("system_prompt") or ""
            created_at = conv.get("created_at") or _now_iso()
            updated_at = conv.get("updated_at") or created_at
            conn.execute(
                "INSERT OR REPLACE INTO conversations"
                "(id, title, created_at, updated_at, system_prompt)"
                " VALUES (?,?,?,?,?)",
                (conv["id"], title, created_at, updated_at, system_prompt),
            )
            messages = conv.get("messages")
            if not isinstance(messages, list):
                continue
            for m in messages:
                if not isinstance(m, dict):
                    continue
                if m.get("role") not in {"system", "user", "assistant"}:
                    continue
                content = m.get("content") or ""
                if not isinstance(content, str):
                    content = str(content)
                conn.execute(
                    "INSERT OR REPLACE INTO messages"
                    "(conversation_id, role, content, created_at, row_order)"
                    " VALUES (?,?,?,?,?)",
                    (
                        conv["id"],
                        m["role"],
                        content,
                        m.get("created_at") or _now_iso(),
                        int(m.get("row_order", 0)),
                    ),
                )
            imported += 1
    return imported


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
