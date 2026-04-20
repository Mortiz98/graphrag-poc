"""Unit tests for ADK agent integration."""

from unittest.mock import MagicMock, patch


class TestGetAdkModel:
    @patch("app.agents.base.get_settings")
    def test_returns_gemini_model(self, mock_settings):
        mock_settings.return_value = MagicMock(
            gemini_api_key="sk-gemini-test",
            gemini_model="gemini-2.0-flash",
            gemini_embedding_model="gemini-embedding-exp-03-07",
        )
        from app.agents.base import get_adk_model

        model = get_adk_model()
        assert model == "gemini-2.0-flash"


class TestRetrievalTools:
    @patch("app.agents.tools.retrieval_tools.get_retrieval_engine")
    def test_search_knowledge_base_returns_formatted(self, mock_get_engine):
        from app.agents.tools.retrieval_tools import search_knowledge_base

        mock_engine = MagicMock()
        mock_result = MagicMock()
        mock_result.subject = "Python"
        mock_result.predicate = "is_a"
        mock_result.object = "Language"
        mock_result.score = 0.95
        mock_result.source_doc = "test.txt"
        mock_engine.search_dense.return_value = [mock_result]
        mock_get_engine.return_value = mock_engine

        result = search_knowledge_base("What is Python?")
        assert "Python is_a Language" in result
        assert "0.95" in result
        call_kwargs = mock_engine.search_dense.call_args.kwargs
        assert call_kwargs["active_only"] is True

    @patch("app.agents.tools.retrieval_tools.get_retrieval_engine")
    def test_search_knowledge_base_with_system(self, mock_get_engine):
        from app.agents.tools.retrieval_tools import search_knowledge_base

        mock_engine = MagicMock()
        mock_engine.search_dense.return_value = []
        mock_get_engine.return_value = mock_engine

        search_knowledge_base("test", system="am")
        call_kwargs = mock_engine.search_dense.call_args.kwargs
        assert call_kwargs["scope"] == {"system": "am"}

    @patch("app.agents.tools.retrieval_tools.get_retrieval_engine")
    def test_search_knowledge_base_empty(self, mock_get_engine):
        from app.agents.tools.retrieval_tools import search_knowledge_base

        mock_engine = MagicMock()
        mock_engine.search_dense.return_value = []
        mock_get_engine.return_value = mock_engine

        result = search_knowledge_base("Obscure question")
        assert "No results" in result

    @patch("app.agents.tools.retrieval_tools.get_retrieval_engine")
    def test_search_by_metadata_with_filters(self, mock_get_engine):
        from app.agents.tools.retrieval_tools import search_by_metadata

        mock_engine = MagicMock()
        mock_result = MagicMock()
        mock_result.subject = "API"
        mock_result.predicate = "has_error"
        mock_result.object = "Timeout"
        mock_result.score = 0.8
        mock_result.source_doc = "ticket.txt"
        mock_engine.search_dense.return_value = [mock_result]
        mock_get_engine.return_value = mock_engine

        result = search_by_metadata("API timeout", system="support", product="API", severity="high")
        assert "API has_error Timeout" in result
        call_kwargs = mock_engine.search_dense.call_args.kwargs
        assert call_kwargs["filters"] == {"product": "API", "severity": "high"}
        assert call_kwargs["active_only"] is True

    @patch("app.agents.tools.retrieval_tools.get_retrieval_engine")
    def test_traverse_issue_graph(self, mock_get_engine):
        from app.agents.tools.retrieval_tools import traverse_issue_graph

        mock_engine = MagicMock()
        mock_result = MagicMock()
        mock_result.subject = "Error"
        mock_result.predicate = "caused_by"
        mock_result.object = "Timeout"
        mock_engine.expand_from_graph.return_value = [mock_result]
        mock_get_engine.return_value = mock_engine

        result = traverse_issue_graph("Error")
        assert "Error caused_by Timeout" in result


class TestAccountTools:
    @patch("app.agents.tools.account_tools.get_retrieval_engine")
    def test_search_episodes(self, mock_get_engine):
        from app.agents.tools.account_tools import search_episodes

        mock_engine = MagicMock()
        mock_result = MagicMock()
        mock_result.subject = "Meeting"
        mock_result.predicate = "discussed"
        mock_result.object = "Renewal"
        mock_result.score = 0.9
        mock_engine.search_dense.return_value = [mock_result]
        mock_get_engine.return_value = mock_engine

        result = search_episodes("quarterly review", "ACC-1")
        assert "Meeting discussed Renewal" in result

    @patch("app.core.account_store.get_retrieval_engine")
    def test_get_account_state(self, mock_get_engine):
        from app.agents.tools.account_tools import get_account_state

        mock_engine = MagicMock()
        mock_result = MagicMock()
        mock_result.subject = "ACC-1"
        mock_result.predicate = "has_tier"
        mock_result.object = "Enterprise"
        mock_result.metadata = {"fact_type": "fact", "valid_from": "2024-01-01"}
        mock_engine.search_by_filter.return_value = [mock_result]
        mock_get_engine.return_value = mock_engine

        result = get_account_state("ACC-1")
        assert "ACC-1" in result

    @patch("app.agents.tools.account_tools.get_retrieval_engine")
    def test_get_commitments_empty(self, mock_get_engine):
        from app.agents.tools.account_tools import get_commitments

        mock_engine = MagicMock()
        mock_engine.search_by_filter.return_value = []
        mock_get_engine.return_value = mock_engine

        result = get_commitments("ACC-1")
        assert "No commitments" in result

    @patch("app.agents.tools.account_tools.get_retrieval_engine")
    def test_get_stakeholder_map_empty(self, mock_get_engine):
        from app.agents.tools.account_tools import get_stakeholder_map

        mock_engine = MagicMock()
        mock_engine.search_by_filter.return_value = []
        mock_get_engine.return_value = mock_engine

        result = get_stakeholder_map("ACC-1")
        assert "No stakeholders" in result


class TestAgentDefinitions:
    def test_support_agent_defined(self):
        from app.agents.support_agent import support_agent

        assert support_agent.name == "support_agent"
        assert len(support_agent.tools) == 6

    def test_account_manager_agent_defined(self):
        from app.agents.account_manager_agent import account_manager_agent

        assert account_manager_agent.name == "account_manager_agent"
        assert len(account_manager_agent.tools) == 10


class TestAdkHealthCheck:
    def test_adk_available(self):
        from app.api.routes.health import _check_adk

        assert _check_adk() is True


class TestToolTraceLogging:
    @patch("app.agents.tools.retrieval_tools.get_retrieval_engine")
    def test_search_knowledge_base_logs_trace(self, mock_get_engine):
        from app.agents.tools.retrieval_tools import search_knowledge_base

        mock_engine = MagicMock()
        mock_engine.search_dense.return_value = []
        mock_get_engine.return_value = mock_engine

        search_knowledge_base("test query")
        mock_engine.log_trace.assert_called()
        call_kwargs = mock_engine.log_trace.call_args.kwargs
        assert call_kwargs["phase"] == "tool:search_knowledge_base"
        assert call_kwargs["query"] == "test query"

    @patch("app.agents.tools.retrieval_tools.get_retrieval_engine")
    def test_search_by_product_logs_trace(self, mock_get_engine):
        from app.agents.tools.retrieval_tools import search_by_product

        mock_engine = MagicMock()
        mock_engine.search_by_filter.return_value = []
        mock_get_engine.return_value = mock_engine

        search_by_product("Qdrant")
        mock_engine.log_trace.assert_called()
        call_kwargs = mock_engine.log_trace.call_args.kwargs
        assert call_kwargs["phase"] == "tool:search_by_product"
        assert call_kwargs["query"] == "Qdrant"

    @patch("app.agents.tools.retrieval_tools.get_retrieval_engine")
    def test_get_resolution_history_logs_two_traces(self, mock_get_engine):
        from app.agents.tools.retrieval_tools import get_resolution_history

        mock_engine = MagicMock()
        mock_result = MagicMock()
        mock_result.subject = "Bug1"
        mock_result.predicate = "has_symptom"
        mock_result.object = "Crash"
        mock_result.score = 0.9
        mock_result.source_doc = "doc1.txt"
        mock_result.subject_id = "Bug1"
        mock_result.object_id = "Crash"
        mock_engine.search_dense.return_value = [mock_result]
        mock_engine.expand_from_graph.return_value = []
        mock_get_engine.return_value = mock_engine

        get_resolution_history("Bug1 causes crashes")
        assert mock_engine.log_trace.call_count == 2

    @patch("app.agents.tools.retrieval_tools.get_retrieval_engine")
    def test_escalation_path_logs_two_traces(self, mock_get_engine):
        from app.agents.tools.retrieval_tools import escalation_path

        mock_engine = MagicMock()
        mock_result = MagicMock()
        mock_result.subject = "Bug1"
        mock_result.predicate = "escalated_to"
        mock_result.object = "TeamA"
        mock_result.score = 0.85
        mock_result.source_doc = "doc1.txt"
        mock_result.subject_id = "Bug1"
        mock_result.object_id = "TeamA"
        mock_engine.search_dense.return_value = [mock_result]
        mock_engine.expand_from_graph.return_value = []
        mock_get_engine.return_value = mock_engine

        escalation_path("Bug1 needs escalation")
        assert mock_engine.log_trace.call_count == 2


class TestExtractToolCalls:
    def test_extracts_function_calls(self):
        from app.api.routes.agents import _extract_tool_calls

        mock_part = MagicMock()
        mock_part.text = None
        mock_part.function_call = MagicMock()
        mock_part.function_call.name = "search_knowledge_base"
        mock_part.function_call.args = {"query": "test"}
        mock_part.function_response = None

        mock_event = MagicMock()
        mock_event.content.parts = [mock_part]

        result = _extract_tool_calls([mock_event])
        assert len(result) == 1
        assert result[0]["name"] == "search_knowledge_base"
        assert result[0]["args"]["query"] == "test"

    def test_extracts_function_responses(self):
        from app.api.routes.agents import _extract_tool_calls

        mock_part = MagicMock()
        mock_part.text = None
        mock_part.function_call = None
        mock_part.function_response = MagicMock()
        mock_part.function_response.name = "search_knowledge_base"

        mock_event = MagicMock()
        mock_event.content.parts = [mock_part]

        result = _extract_tool_calls([mock_event])
        assert len(result) == 1
        assert result[0]["name"] == "search_knowledge_base"
        assert result[0]["response"] == "ok"

    def test_skips_text_only_events(self):
        from app.api.routes.agents import _extract_tool_calls

        mock_part = MagicMock()
        mock_part.text = "Hello"
        mock_part.function_call = None
        mock_part.function_response = None

        mock_event = MagicMock()
        mock_event.content.parts = [mock_part]

        result = _extract_tool_calls([mock_event])
        assert len(result) == 0


class TestLogInteraction:
    @patch("app.api.routes.agents.get_retrieval_engine")
    def test_logs_interaction_trace(self, mock_get_engine):
        from app.api.routes.agents import _log_interaction

        mock_engine = MagicMock()
        mock_get_engine.return_value = mock_engine

        _log_interaction(
            agent_name="support",
            question="What is Qdrant?",
            answer="Qdrant is a vector DB",
            session_id="sess-1",
            tool_calls=[{"name": "search_knowledge_base", "args": {"query": "Qdrant"}}],
            duration_ms=1234.5,
            trace_id="abc123",
        )

        mock_engine.log_trace.assert_called_once()
        call_kwargs = mock_engine.log_trace.call_args.kwargs
        assert call_kwargs["phase"] == "agent:support"
        assert call_kwargs["query"] == "What is Qdrant?"
        assert call_kwargs["trace_id"] == "abc123"
        assert call_kwargs["session_id"] == "sess-1"
        assert call_kwargs["metadata"]["tool_count"] == 1
