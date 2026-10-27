"""SQLite bootstrap and path resolution for the local chat database."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


DB_FILE_NAME = "chat.db"
SCHEMA_VERSION = 1


def database_path() -> Path:
    data_dir = Path.home() / ".qwen-desktop-chat"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / DB_FILE_NAME


def open_database(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(
        str(db_path),
        timeout=10.0,
        isolation_level="DEFERRED",
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def database(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = open_database(db_path)
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            system_prompt TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('system','user','assistant')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            row_order INTEGER NOT NULL,
            UNIQUE(conversation_id, row_order)
        );

        CREATE INDEX IF NOT EXISTS idx_messages_conversation
            ON messages(conversation_id, row_order);

        CREATE INDEX IF NOT EXISTS idx_conversations_updated
            ON conversations(updated_at DESC);

        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)
    conn.execute(
        "INSERT OR IGNORE INTO schema_meta(key,value) VALUES('version',?)",
        (str(SCHEMA_VERSION),),
    )
