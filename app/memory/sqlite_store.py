"""Persistent per-session conversation history, SQLite/WAL-backed."""
import functools
import sqlite3
import threading
from typing import Dict, List

from app.config import settings

_lock = threading.Lock()


class SQLiteMemoryStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self) -> None:
        with _lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_turns_conv ON turns(conversation_id, id)")

    def save_turn(self, conversation_id: str, question: str, answer: str) -> None:
        with _lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO turns (conversation_id, role, content) VALUES (?, 'user', ?)",
                (conversation_id, question),
            )
            conn.execute(
                "INSERT INTO turns (conversation_id, role, content) VALUES (?, 'assistant', ?)",
                (conversation_id, answer),
            )

    def get_history(self, conversation_id: str, max_turns: int) -> List[Dict[str, str]]:
        limit = max(1, max_turns) * 2
        with _lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT role, content FROM turns WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
                (conversation_id, limit),
            ).fetchall()
        return [{"role": role, "content": content} for role, content in reversed(rows)]

    def clear_conversation(self, conversation_id: str) -> None:
        with _lock, self._connect() as conn:
            conn.execute("DELETE FROM turns WHERE conversation_id = ?", (conversation_id,))
            conn.commit()

    def clear_all(self) -> None:
        with _lock, self._connect() as conn:
            conn.execute("DELETE FROM turns")
            conn.commit()


@functools.lru_cache(maxsize=1)
def get_memory_store() -> SQLiteMemoryStore:
    return SQLiteMemoryStore(settings.MEMORY_DB_PATH)


def reset_memory_database() -> None:
    """Wipes all previous conversation history and cleans the database."""
    store = get_memory_store()
    store.clear_all()
