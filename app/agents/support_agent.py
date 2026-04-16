from google.adk.agents import LlmAgent

from app.agents.base import get_adk_model
from app.agents.prompts.support_system import SUPPORT_SYSTEM_PROMPT
from app.agents.tools.retrieval_tools import search_by_metadata, search_knowledge_base, traverse_issue_graph

support_agent = LlmAgent(
    name="support_agent",
    model=get_adk_model(),
    description="Support agent that answers questions grounded in the knowledge base with traceability.",
    instruction=SUPPORT_SYSTEM_PROMPT,
    tools=[
        search_knowledge_base,
        search_by_metadata,
        traverse_issue_graph,
    ],
)
