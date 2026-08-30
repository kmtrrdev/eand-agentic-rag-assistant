"""
app/memory/sqlite_store.py
--------------------------
SQLite-backed persistent conversation memory store.

Design principles:
- Thread-safe via per-connection approach (check_same_thread=False + pragmas).
- Idempotent schema creation (CREATE TABLE IF NOT EXISTS).
- Graceful degradation: all public methods log errors and return safe defaults
  rather than propagating exceptions into the agent pipeline.
- Soft message limit via MAX_HISTORY_MESSAGES from settings.
"""
import json
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from typing import Dict, Generator, List, Optional

from app.config import settings
from app.memory.store import MemoryStore

logger = logging.getLogger("memory.sqlite")

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,
    role        TEXT    NOT NULL CHECK(role IN ('user', 'assistant')),
    content     TEXT    NOT NULL,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_conversations_session
    ON conversations (session_id, id);
"""


class SQLiteMemoryStore(MemoryStore):
    """
    Persistent conversation memory backed by a local SQLite database.

    Usage:
        store = SQLiteMemoryStore()
        conv_id = "abc123"
        store.save_turn(conv_id, "ايه باقات حكاية؟", "يوجد باقة مكسات وإنترنت...")
        history = store.get_history(conv_id)
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.MEMORY_DB_PATH
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        try:
            conn = self._connect()
            conn.executescript(SCHEMA)
            conn.commit()
            conn.close()
            logger.info(f"SQLiteMemoryStore initialized at: {self.db_path}")
        except Exception as exc:
            logger.error(f"SQLiteMemoryStore init failed: {exc}")

    def save_turn(
        self,
        conversation_id: str,
        user_message: str,
        assistant_message: str,
    ) -> None:
        """Persist one user-assistant exchange atomically."""
        try:
            conn = self._connect()
            conn.execute(
                "INSERT INTO conversations (session_id, role, content) VALUES (?, ?, ?)",
                (conversation_id, "user", user_message),
            )
            conn.execute(
                "INSERT INTO conversations (session_id, role, content) VALUES (?, ?, ?)",
                (conversation_id, "assistant", assistant_message),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error(f"save_turn failed for {conversation_id}: {exc}")

    def get_history(
        self,
        conversation_id: str,
        max_turns: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """
        Load history as list of {"role": ..., "content": ...} dicts.
        Returns up to 2 * max_turns rows (each turn = 1 user + 1 assistant row).
        """
        limit = (max_turns or settings.MAX_HISTORY_MESSAGES) * 2
        try:
            conn = self._connect()
            rows = conn.execute(
                """
                SELECT role, content FROM (
                    SELECT id, role, content
                    FROM conversations
                    WHERE session_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                ) sub
                ORDER BY id ASC
                """,
                (conversation_id, limit),
            ).fetchall()
            conn.close()
            return [{"role": row["role"], "content": row["content"]} for row in rows]
        except Exception as exc:
            logger.error(f"get_history failed for {conversation_id}: {exc}")
            return []

    def conversation_exists(self, conversation_id: str) -> bool:
        try:
            conn = self._connect()
            count = conn.execute(
                "SELECT COUNT(*) FROM conversations WHERE session_id = ?",
                (conversation_id,),
            ).fetchone()[0]
            conn.close()
            return count > 0
        except Exception:
            return False

    def clear_conversation(self, conversation_id: str) -> None:
        try:
            conn = self._connect()
            conn.execute(
                "DELETE FROM conversations WHERE session_id = ?",
                (conversation_id,),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error(f"clear_conversation failed for {conversation_id}: {exc}")

    def list_conversations(self) -> List[str]:
        try:
            conn = self._connect()
            rows = conn.execute(
                "SELECT DISTINCT session_id FROM conversations ORDER BY id DESC"
            ).fetchall()
            conn.close()
            return [row["session_id"] for row in rows]
        except Exception as exc:
            logger.error(f"list_conversations failed: {exc}")
            return []


# Module-level singleton factory (lazy init)
_store: Optional[SQLiteMemoryStore] = None


def get_memory_store() -> Optional[SQLiteMemoryStore]:
    """
    Return the singleton SQLiteMemoryStore, or None if persistent memory
    is disabled (PERSISTENT_MEMORY_ENABLED=false) or unavailable.
    """
    global _store
    if not settings.PERSISTENT_MEMORY_ENABLED:
        return None
    if _store is None:
        try:
            _store = SQLiteMemoryStore()
        except Exception as exc:
            logger.warning(f"Persistent memory unavailable: {exc}. Falling back to per-request mode.")
            return None
    return _store
