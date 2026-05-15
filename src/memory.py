"""In-process conversation memory keyed by session_id.

Bonus deliverable #12 — gives the graph a real chat history so follow-up
questions ("what about the second one?") have context. The store lives in
the API process; per-session capacity is bounded to keep prompts small.
For multi-worker deployments swap the backend for Redis or Postgres —
the public interface here stays the same.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Literal, TypedDict

Role = Literal["user", "assistant"]


class Turn(TypedDict):
    role: Role
    content: str


_MAX_TURNS_PER_SESSION = 12  # 6 user + 6 assistant


class ConversationMemory:
    """Bounded, thread-safe per-session chat history.

    Beyond the chat log, this also keeps two small per-session slots
    used by the conversational ticketing flow:

    * `pending_complaint` — the complaint text we're waiting on contact
      info for. The next user message is parsed by `src/contact.py` and
      then re-routed as that original complaint.
    * `contact` — name/phone/email captured for the session. Once set,
      subsequent complaints in the same session reuse it without asking.
    """

    def __init__(self, max_turns: int = _MAX_TURNS_PER_SESSION) -> None:
        self._max_turns = max_turns
        self._store: dict[str, deque[Turn]] = {}
        self._pending: dict[str, str] = {}
        self._contact: dict[str, dict] = {}
        self._lock = threading.RLock()

    def get(self, session_id: str) -> list[Turn]:
        with self._lock:
            return list(self._store.get(session_id, ()))

    def append(self, session_id: str, role: Role, content: str) -> None:
        if not content:
            return
        with self._lock:
            buf = self._store.setdefault(
                session_id, deque(maxlen=self._max_turns)
            )
            buf.append(Turn(role=role, content=content))

    def clear(self, session_id: str) -> bool:
        with self._lock:
            cleared = self._store.pop(session_id, None) is not None
            self._pending.pop(session_id, None)
            self._contact.pop(session_id, None)
            return cleared

    def reset(self) -> None:
        """Wipe every session — only used in tests."""
        with self._lock:
            self._store.clear()
            self._pending.clear()
            self._contact.clear()

    # --------------------- pending-complaint slot ---------------------
    def set_pending_complaint(self, session_id: str, complaint: str) -> None:
        with self._lock:
            self._pending[session_id] = complaint

    def get_pending_complaint(self, session_id: str) -> str | None:
        with self._lock:
            return self._pending.get(session_id)

    def clear_pending_complaint(self, session_id: str) -> None:
        with self._lock:
            self._pending.pop(session_id, None)

    # --------------------- per-session contact ------------------------
    def set_contact(self, session_id: str, contact: dict) -> None:
        with self._lock:
            self._contact[session_id] = dict(contact)

    def get_contact(self, session_id: str) -> dict | None:
        with self._lock:
            stored = self._contact.get(session_id)
            return dict(stored) if stored else None


memory = ConversationMemory()
