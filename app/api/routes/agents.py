"""Agent API route handlers for support and AM agents."""

from fastapi import APIRouter, Depends, HTTPException

from app.core.agent_runner import (
    Runner,
    Session,
    SessionStore,
    create_session,
    get_runner,
    get_session_store,
)
from app.models.schemas import (
    AgentQueryRequest,
    AgentQueryResponse,
    AgentStateResponse,
    SessionInfo,
    SessionListResponse,
)

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


def _run_agent_query(
    request: AgentQueryRequest,
    agent_type: str,
    runner: Runner,
    store: SessionStore,
) -> AgentQueryResponse:
    session: Session | None = None
    if request.session_id:
        session = store.get(request.session_id)
    if session is None:
        session = create_session(agent_type=agent_type)
        store.put(session)

    try:
        answer = runner.run(agent_type=agent_type, question=request.question, session=session)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Agent error: {e}") from e

    return AgentQueryResponse(
        answer=answer,
        session_id=session.session_id,
        agent_type=agent_type,
    )


@router.post(
    "/support/query",
    response_model=AgentQueryResponse,
    summary="Support agent sync query",
    description="Submit a question to the support agent and receive a synchronous response.",
)
async def support_query(
    request: AgentQueryRequest,
    runner: Runner = Depends(get_runner),
    store: SessionStore = Depends(get_session_store),
) -> AgentQueryResponse:
    return _run_agent_query(request, "support", runner, store)


@router.post(
    "/am/query",
    response_model=AgentQueryResponse,
    summary="AM agent sync query",
    description="Submit a question to the AM (Account Manager) agent and receive a synchronous response.",
)
async def am_query(
    request: AgentQueryRequest,
    runner: Runner = Depends(get_runner),
    store: SessionStore = Depends(get_session_store),
) -> AgentQueryResponse:
    return _run_agent_query(request, "am", runner, store)


@router.get(
    "/am/state/{session_id}",
    response_model=AgentStateResponse,
    summary="AM agent state",
    description="Get the current state of an AM agent session.",
)
async def am_state(
    session_id: str,
    store: SessionStore = Depends(get_session_store),
) -> AgentStateResponse:
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return AgentStateResponse(
        session_id=session.session_id,
        agent_type=session.agent_type,
        status=session.status,
        message_count=session.message_count,
        created_at=session.created_at,
    )


@router.post(
    "/sessions",
    response_model=SessionInfo,
    summary="Create a new agent session",
    description="Create a new session for the specified agent type.",
)
async def create_agent_session(
    agent_type: str,
    store: SessionStore = Depends(get_session_store),
) -> SessionInfo:
    session = create_session(agent_type=agent_type)
    store.put(session)
    return SessionInfo(
        session_id=session.session_id,
        agent_type=session.agent_type,
        status=session.status,
        created_at=session.created_at,
    )


@router.get(
    "/sessions",
    response_model=SessionListResponse,
    summary="List agent sessions",
    description="List all sessions, optionally filtered by agent type.",
)
async def list_sessions(
    agent_type: str | None = None,
    store: SessionStore = Depends(get_session_store),
) -> SessionListResponse:
    sessions = store.list_sessions(agent_type=agent_type)
    return SessionListResponse(
        sessions=[
            SessionInfo(
                session_id=s.session_id,
                agent_type=s.agent_type,
                status=s.status,
                created_at=s.created_at,
            )
            for s in sessions
        ],
    )


@router.delete(
    "/sessions/{session_id}",
    summary="Delete an agent session",
    description="End and remove an agent session.",
)
async def delete_session(
    session_id: str,
    store: SessionStore = Depends(get_session_store),
) -> dict[str, str]:
    removed = store.remove(session_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return {"status": "deleted", "session_id": session_id}
