"""Tests for agent API endpoints covering sync queries and session lifecycle.

All tests use a mocked ADK runner to avoid external service dependencies.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.agent_runner import InMemoryRunner, Session, SessionStore
from app.main import app


@pytest.fixture()
def mock_runner():
    """Mocked ADK runner that returns deterministic responses."""
    runner = MagicMock(spec=InMemoryRunner)
    runner.run.return_value = "Mocked agent response"
    return runner


@pytest.fixture()
def fresh_store():
    """Fresh session store for each test to avoid cross-test pollution."""
    return SessionStore()


@pytest.fixture()
def client(mock_runner, fresh_store):
    """FastAPI test client with mocked runner and fresh session store."""
    from app.api.routes import agents as agents_module

    app.dependency_overrides[agents_module.get_runner] = lambda: mock_runner
    app.dependency_overrides[agents_module.get_session_store] = lambda: fresh_store

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.dependency_overrides.clear()


class TestSupportAgentSyncQuery:
    """Tests for POST /api/v1/agents/support/query."""

    def test_support_query_returns_200(self, client, mock_runner):
        response = client.post(
            "/api/v1/agents/support/query",
            json={"question": "How do I reset my password?"},
        )
        assert response.status_code == 200

    def test_support_query_returns_answer(self, client, mock_runner):
        response = client.post(
            "/api/v1/agents/support/query",
            json={"question": "How do I reset my password?"},
        )
        data = response.json()
        assert data["answer"] == "Mocked agent response"
        assert data["agent_type"] == "support"
        assert "session_id" in data

    def test_support_query_calls_runner(self, client, mock_runner):
        client.post(
            "/api/v1/agents/support/query",
            json={"question": "How do I reset my password?"},
        )
        mock_runner.run.assert_called_once()
        call_kwargs = mock_runner.run.call_args
        assert call_kwargs[1]["agent_type"] == "support"
        assert call_kwargs[1]["question"] == "How do I reset my password?"

    def test_support_query_empty_question_fails(self, client):
        response = client.post(
            "/api/v1/agents/support/query",
            json={"question": ""},
        )
        assert response.status_code == 422

    def test_support_query_with_existing_session(self, client, mock_runner, fresh_store):
        session = Session(agent_type="support", session_id="existing-session-1")
        session.add_message("user", "previous question")
        fresh_store.put(session)

        response = client.post(
            "/api/v1/agents/support/query",
            json={"question": "Follow-up question", "session_id": "existing-session-1"},
        )
        assert response.status_code == 200
        assert response.json()["session_id"] == "existing-session-1"
        # Runner should receive the existing session
        call_kwargs = mock_runner.run.call_args
        assert call_kwargs[1]["session"].session_id == "existing-session-1"

    def test_support_query_runner_error(self, client, mock_runner):
        mock_runner.run.side_effect = RuntimeError("LLM unavailable")
        response = client.post(
            "/api/v1/agents/support/query",
            json={"question": "test"},
        )
        assert response.status_code == 503
        assert "Agent error" in response.json()["detail"]


class TestAMAgentSyncQuery:
    """Tests for POST /api/v1/agents/am/query."""

    def test_am_query_returns_200(self, client, mock_runner):
        response = client.post(
            "/api/v1/agents/am/query",
            json={"question": "What is my account balance?"},
        )
        assert response.status_code == 200

    def test_am_query_returns_answer(self, client, mock_runner):
        response = client.post(
            "/api/v1/agents/am/query",
            json={"question": "What is my account balance?"},
        )
        data = response.json()
        assert data["answer"] == "Mocked agent response"
        assert data["agent_type"] == "am"
        assert "session_id" in data

    def test_am_query_calls_runner_with_am_type(self, client, mock_runner):
        client.post(
            "/api/v1/agents/am/query",
            json={"question": "What is my account balance?"},
        )
        call_kwargs = mock_runner.run.call_args
        assert call_kwargs[1]["agent_type"] == "am"

    def test_am_query_empty_question_fails(self, client):
        response = client.post(
            "/api/v1/agents/am/query",
            json={"question": ""},
        )
        assert response.status_code == 422


class TestAMStateEndpoint:
    """Tests for GET /api/v1/agents/am/state/{session_id}."""

    def test_state_returns_200_for_existing_session(self, client, fresh_store):
        session = Session(agent_type="am", session_id="state-test-1")
        session.add_message("user", "question 1")
        session.add_message("assistant", "answer 1")
        fresh_store.put(session)

        response = client.get("/api/v1/agents/am/state/state-test-1")
        assert response.status_code == 200

    def test_state_returns_session_details(self, client, fresh_store):
        session = Session(agent_type="am", session_id="state-test-2")
        session.add_message("user", "hello")
        session.add_message("assistant", "hi")
        fresh_store.put(session)

        response = client.get("/api/v1/agents/am/state/state-test-2")
        data = response.json()
        assert data["session_id"] == "state-test-2"
        assert data["agent_type"] == "am"
        assert data["status"] == "active"
        assert data["message_count"] == 2

    def test_state_returns_404_for_missing_session(self, client):
        response = client.get("/api/v1/agents/am/state/nonexistent-session")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_state_with_zero_messages(self, client, fresh_store):
        session = Session(agent_type="am", session_id="empty-session")
        fresh_store.put(session)

        response = client.get("/api/v1/agents/am/state/empty-session")
        data = response.json()
        assert data["message_count"] == 0


class TestSessionLifecycle:
    """Tests for session create, list, and delete endpoints."""

    def test_create_session(self, client, fresh_store):
        response = client.post("/api/v1/agents/sessions", params={"agent_type": "support"})
        assert response.status_code == 200
        data = response.json()
        assert data["agent_type"] == "support"
        assert data["status"] == "active"
        assert "session_id" in data
        assert "created_at" in data

    def test_list_sessions_empty(self, client):
        response = client.get("/api/v1/agents/sessions")
        assert response.status_code == 200
        assert response.json()["sessions"] == []

    def test_list_sessions_after_create(self, client, fresh_store):
        client.post("/api/v1/agents/sessions", params={"agent_type": "support"})
        client.post("/api/v1/agents/sessions", params={"agent_type": "am"})

        response = client.get("/api/v1/agents/sessions")
        data = response.json()
        assert len(data["sessions"]) == 2

    def test_list_sessions_filtered_by_agent_type(self, client, fresh_store):
        client.post("/api/v1/agents/sessions", params={"agent_type": "support"})
        client.post("/api/v1/agents/sessions", params={"agent_type": "am"})

        response = client.get("/api/v1/agents/sessions", params={"agent_type": "am"})
        data = response.json()
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["agent_type"] == "am"

    def test_delete_session(self, client, fresh_store):
        create_resp = client.post("/api/v1/agents/sessions", params={"agent_type": "support"})
        session_id = create_resp.json()["session_id"]

        delete_resp = client.delete(f"/api/v1/agents/sessions/{session_id}")
        assert delete_resp.status_code == 200
        assert delete_resp.json()["status"] == "deleted"

    def test_delete_nonexistent_session_returns_404(self, client):
        response = client.delete("/api/v1/agents/sessions/nonexistent-id")
        assert response.status_code == 404

    def test_session_persists_across_queries(self, client, mock_runner, fresh_store):
        """Verify that a session created via query can be listed and deleted."""
        query_resp = client.post(
            "/api/v1/agents/support/query",
            json={"question": "Hello"},
        )
        session_id = query_resp.json()["session_id"]

        list_resp = client.get("/api/v1/agents/sessions")
        sessions = list_resp.json()["sessions"]
        assert any(s["session_id"] == session_id for s in sessions)

        delete_resp = client.delete(f"/api/v1/agents/sessions/{session_id}")
        assert delete_resp.status_code == 200

        list_after = client.get("/api/v1/agents/sessions")
        assert not any(s["session_id"] == session_id for s in list_after.json()["sessions"])

    def test_full_lifecycle_create_query_state_delete(self, client, mock_runner, fresh_store):
        """End-to-end session lifecycle: create → query → state → delete."""

        # Make mock_runner behave like the real runner (adds messages to session)
        def mock_run(agent_type, question, session):
            session.add_message("user", question)
            session.add_message("assistant", "Mocked agent response")
            return "Mocked agent response"

        mock_runner.run.side_effect = mock_run

        # 1. Create session
        create_resp = client.post("/api/v1/agents/sessions", params={"agent_type": "am"})
        assert create_resp.status_code == 200
        session_id = create_resp.json()["session_id"]

        # 2. Query using that session
        query_resp = client.post(
            "/api/v1/agents/am/query",
            json={"question": "Check balance", "session_id": session_id},
        )
        assert query_resp.status_code == 200
        assert query_resp.json()["session_id"] == session_id

        # 3. Check state
        state_resp = client.get(f"/api/v1/agents/am/state/{session_id}")
        assert state_resp.status_code == 200
        assert state_resp.json()["message_count"] == 2  # user + assistant
        assert state_resp.json()["status"] == "active"

        # 4. Delete
        delete_resp = client.delete(f"/api/v1/agents/sessions/{session_id}")
        assert delete_resp.status_code == 200

        # 5. Verify state is gone
        state_after = client.get(f"/api/v1/agents/am/state/{session_id}")
        assert state_after.status_code == 404
