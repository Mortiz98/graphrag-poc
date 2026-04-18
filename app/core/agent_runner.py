"""Agent runner abstraction for ADK-style agent execution."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol


class Session:
    """Represents an agent session with message history."""

    def __init__(self, agent_type: str, session_id: str | None = None) -> None:
        self.session_id = session_id or str(uuid.uuid4())
        self.agent_type = agent_type
        self.status = "active"
        self.created_at = datetime.now(UTC).isoformat()
        self.messages: list[dict[str, str]] = []

    def add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})

    @property
    def message_count(self) -> int:
        return len(self.messages)


class Runner(Protocol):
    """Protocol for ADK-style agent runners."""

    def run(self, agent_type: str, question: str, session: Session) -> str:
        """Execute a query and return the answer text."""
        ...


class InMemoryRunner:
    """Simple in-memory runner that echoes back a templated response.

    In production this would call an LLM-backed agent via the ADK.
    """

    def run(self, agent_type: str, question: str, session: Session) -> str:
        session.add_message("user", question)
        answer = f"[{agent_type}] Response to: {question}"
        session.add_message("assistant", answer)
        return answer


class SessionStore:
    """In-memory store for agent sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def put(self, session: Session) -> None:
        self._sessions[session.session_id] = session

    def remove(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def list_sessions(self, agent_type: str | None = None) -> list[Session]:
        sessions = list(self._sessions.values())
        if agent_type:
            sessions = [s for s in sessions if s.agent_type == agent_type]
        return sessions


def create_session(agent_type: str, session_id: str | None = None) -> Session:
    return Session(agent_type=agent_type, session_id=session_id)


# Module-level singletons
_default_runner: InMemoryRunner = InMemoryRunner()
_session_store: SessionStore = SessionStore()


def get_runner() -> Runner:
    return _default_runner


def get_session_store() -> SessionStore:
    return _session_store
