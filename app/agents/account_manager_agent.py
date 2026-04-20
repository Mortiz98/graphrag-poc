from google.adk.agents import LlmAgent

from app.agents.base import get_adk_model
from app.agents.prompts.am_system import AM_SYSTEM_PROMPT
from app.agents.tools.account_tools import (
    get_account_state,
    get_commitments,
    get_stakeholder_map,
    search_episodes,
    update_fact,
    write_commitment,
    write_fact,
    write_stakeholder,
)
from app.agents.tools.retrieval_tools import search_by_metadata, search_knowledge_base

account_manager_agent = LlmAgent(
    name="account_manager_agent",
    model=get_adk_model(),
    description="Account Manager agent that maintains relational and operational continuity across sessions.",
    instruction=AM_SYSTEM_PROMPT,
    tools=[
        search_knowledge_base,
        search_by_metadata,
        search_episodes,
        get_account_state,
        get_commitments,
        get_stakeholder_map,
        write_fact,
        update_fact,
        write_commitment,
        write_stakeholder,
    ],
)
