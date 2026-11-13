"""Thread-safe in-memory per-chat and per-user session state store."""
import threading
from typing import Any, Dict, Optional

from io_manager_modules.telegram_validator import TelegramValidator


class TelegramSessionStore:
    """Encapsulates active company selections and per-chat UI configuration state."""

    def __init__(self, default_top_n: int = 3):
        self._lock = threading.RLock()
        self._default_top_n = default_top_n
        self._sessions: Dict[int, Dict[str, Any]] = {}
        self._user_active_company: Dict[int, str] = {}

    def get_session(self, chat_id: int) -> Dict[str, Any]:
        """Returns the session dictionary for chat_id, initializing defaults if needed."""
        with self._lock:
            if chat_id not in self._sessions:
                self._sessions[chat_id] = {
                    "top_n": self._default_top_n,
                    "pending_rule_text": None,
                }
            return self._sessions[chat_id]

    def get_top_n(self, chat_id: int) -> int:
        """Returns the stored shortlist limit for chat_id."""
        with self._lock:
            return int(self.get_session(chat_id).get("top_n", self._default_top_n))

    def set_top_n(self, chat_id: int, val: int) -> None:
        """Persists a new shortlist limit for chat_id."""
        with self._lock:
            self.get_session(chat_id)["top_n"] = int(val)

    def get_effective_top_n(self, chat_id: int, resume_count: int) -> int:
        """Returns session top_n capped to resume_count (when > 0) and syncs session."""
        with self._lock:
            session = self.get_session(chat_id)
            effective_n, was_capped = TelegramValidator.cap_top_n(
                session.get("top_n", self._default_top_n),
                resume_count,
            )
            if was_capped:
                session["top_n"] = effective_n
            return effective_n

    def get_pending_rule_text(self, chat_id: int) -> Optional[str]:
        """Returns pending rule text awaiting priority selection for chat_id."""
        with self._lock:
            return self.get_session(chat_id).get("pending_rule_text")

    def set_pending_rule_text(self, chat_id: int, text: Optional[str]) -> None:
        """Stores or clears pending rule text for chat_id."""
        with self._lock:
            self.get_session(chat_id)["pending_rule_text"] = text

    def get_active_company_name(self, user_id: int) -> Optional[str]:
        """Returns the active company name selected by user_id, if any."""
        with self._lock:
            return self._user_active_company.get(user_id)

    def set_active_company_name(self, user_id: int, company_name: str) -> None:
        """Sets the active company name for user_id."""
        with self._lock:
            self._user_active_company[user_id] = company_name

    def clear_active_company(self, user_id: int) -> None:
        """Logs user_id out of their active company selection."""
        with self._lock:
            self._user_active_company.pop(user_id, None)

