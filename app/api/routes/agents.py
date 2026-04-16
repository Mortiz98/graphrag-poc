import json
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.agents.account_manager_agent import account_manager_agent
from app.agents.support_agent import support_agent
from app.core import logger

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

_session_service = InMemorySessionService()

_runners: dict[str, Runner] = {}


def _get_runner(agent_name: str) -> Runner:
    if agent_name not in _runners:
        agent = support_agent if agent_name == "support" else account_manager_agent
        _runners[agent_name] = Runner(
            app_name="graphrag",
            agent=agent,
            session_service=_session_service,
        )
    return _runners[agent_name]


async def _ensure_session(user_id: str, session_id: str | None = None) -> str:
    if session_id is None:
        session_id = str(uuid4())
    try:
        await _session_service.get_session(app_name="graphrag", user_id=user_id, session_id=session_id)
    except Exception:
        await _session_service.create_session(app_name="graphrag", user_id=user_id, session_id=session_id)
    return session_id


@router.post(
    "/support/query",
    summary="Query the support agent",
    description="Send a question to the support agent. The agent uses retrieval tools "
    "to search the knowledge base and provide grounded answers.",
)
async def support_query(question: str, user_id: str = "default", session_id: str | None = None):
    try:
        sid = await _ensure_session(user_id, session_id)
        runner = _get_runner("support")
        content = types.Content(role="user", parts=[types.Part(text=question)])
        events = []
        async for event in runner.run_async(user_id=user_id, session_id=sid, new_message=content):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        events.append(part.text)
        answer = "\n".join(events) if events else "No response generated."
        return {"answer": answer, "session_id": sid}
    except Exception as e:
        logger.error("support_agent_error", error=str(e))
        raise HTTPException(status_code=503, detail=f"Agent error: {str(e)}")


@router.post(
    "/support/query/stream",
    summary="Stream query to the support agent",
    description="Same as /support/query but streams the response token-by-token using SSE.",
)
async def support_query_stream(question: str, user_id: str = "default", session_id: str | None = None):
    try:
        sid = await _ensure_session(user_id, session_id)
        runner = _get_runner("support")
        content = types.Content(role="user", parts=[types.Part(text=question)])

        async def event_stream():
            yield f"data: {json.dumps({'type': 'metadata', 'session_id': sid})}\n\n"
            async for event in runner.run_async(user_id=user_id, session_id=sid, new_message=content):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            token_event = {"type": "token", "content": part.text}
                            yield f"data: {json.dumps(token_event)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")
    except Exception as e:
        logger.error("support_agent_stream_error", error=str(e))
        raise HTTPException(status_code=503, detail=f"Agent error: {str(e)}")


@router.post(
    "/am/query",
    summary="Query the Account Manager agent",
    description="Send a question to the Account Manager agent for a specific account. "
    "The agent retrieves account state, commitments, and stakeholder information.",
)
async def am_query(question: str, account_id: str, user_id: str = "default", session_id: str | None = None):
    try:
        sid = await _ensure_session(user_id, session_id)
        runner = _get_runner("am")
        content = types.Content(role="user", parts=[types.Part(text=question)])
        events = []
        async for event in runner.run_async(
            user_id=user_id,
            session_id=sid,
            new_message=content,
            state_delta={"account_id": account_id},
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        events.append(part.text)
        answer = "\n".join(events) if events else "No response generated."
        return {"answer": answer, "session_id": sid, "account_id": account_id}
    except Exception as e:
        logger.error("am_agent_error", error=str(e))
        raise HTTPException(status_code=503, detail=f"Agent error: {str(e)}")


@router.get(
    "/am/state/{account_id}",
    summary="Get account state",
    description="Retrieve the current state of an account including facts, commitments, and stakeholders.",
)
async def am_state(account_id: str):
    try:
        from app.agents.tools.account_tools import get_account_state, get_commitments, get_stakeholder_map

        state = get_account_state(account_id)
        commitments = get_commitments(account_id)
        stakeholders = get_stakeholder_map(account_id)
        return {
            "account_id": account_id,
            "state": state,
            "commitments": commitments,
            "stakeholders": stakeholders,
        }
    except Exception as e:
        logger.error("am_state_error", error=str(e))
        raise HTTPException(status_code=503, detail=f"Error retrieving account state: {str(e)}")
