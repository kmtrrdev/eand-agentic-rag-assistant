"""
app/memory/store.py
-------------------
Abstract base class for conversation memory stores.
Concrete implementations (e.g., SQLiteMemoryStore) must inherit from this.
"""
import abc
from typing import Any, Dict, List, Optional


class MemoryStore(abc.ABC):
    """Protocol for conversation persistence backends."""

    @abc.abstractmethod
    def save_turn(
        self,
        conversation_id: str,
        user_message: str,
        assistant_message: str,
    ) -> None:
        """Persist one user-assistant exchange."""

    @abc.abstractmethod
    def get_history(
        self,
        conversation_id: str,
        max_turns: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """
        Load history as a list of {"role": "user"/"assistant", "content": "..."} dicts.
        Returns an empty list if conversation_id is unknown.
        """

    @abc.abstractmethod
    def conversation_exists(self, conversation_id: str) -> bool:
        """Return True if conversation_id has any stored turns."""

    @abc.abstractmethod
    def clear_conversation(self, conversation_id: str) -> None:
        """Delete all turns for a conversation_id."""

    @abc.abstractmethod
    def list_conversations(self) -> List[str]:
        """Return all known conversation IDs."""
