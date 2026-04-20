"""Unit tests for RetrievalEngine extended methods and retrieval tools."""

from unittest.mock import MagicMock, patch

from app.agents.tools.retrieval_tools import (
    escalation_path,
    get_resolution_history,
    search_by_product,
    traverse_issue_graph,
)
from app.core.retrieval import RetrievalEngine, SearchResult, reset_retrieval_engine


def _make_result(**kwargs):
    defaults = {
        "subject": "Python",
        "predicate": "is_a",
        "object": "Language",
        "score": 0.95,
        "source_doc": "test.txt",
        "chunk_id": "c1",
        "subject_id": "Python",
        "object_id": "Language",
        "retrieval_method": "dense",
        "scope": {},
    }
    defaults.update(kwargs)
    return SearchResult(**defaults)


class TestSearchDenseWithScope:
    @patch("app.core.retrieval.embed_query")
    @patch("app.core.retrieval.get_qdrant_client")
    @patch("app.core.retrieval.ensure_collection_exists")
    def test_scope_merged_into_filter(self, mock_ensure, mock_client, mock_embed):
        reset_retrieval_engine()
        mock_embed.return_value = [0.1] * 768

        mock_point = MagicMock()
        mock_point.payload = {
            "subject": "Python",
            "predicate": "is_a",
            "object": "Language",
            "subject_id": "Python",
            "object_id": "Language",
            "chunk_id": "c1",
            "source_doc": "test.txt",
        }
        mock_point.score = 0.9
        mock_results = MagicMock()
        mock_results.points = [mock_point]
        mock_qdrant = MagicMock()
        mock_qdrant.query_points.return_value = mock_results
        mock_client.return_value = mock_qdrant

        engine = RetrievalEngine()
        results = engine.search_dense(
            query="test",
            scope={"system": "support", "account_id": "ACC-1"},
        )
        assert len(results) == 1
        assert results[0].retrieval_method == "dense"
        assert results[0].scope == {"system": "support", "account_id": "ACC-1"}
        call_kwargs = mock_qdrant.query_points.call_args
        assert call_kwargs.kwargs["query_filter"] is not None


class TestSearchSparseFallback:
    @patch.object(RetrievalEngine, "search_dense", return_value=[_make_result(retrieval_method="dense")])
    def test_sparse_falls_back_to_dense(self, mock_dense):
        reset_retrieval_engine()
        engine = RetrievalEngine()
        results = engine.search_sparse("test query", scope={"system": "support"})
        assert len(results) == 1
        mock_dense.assert_called_once()


class TestSearchHybridFallback:
    @patch.object(RetrievalEngine, "search_dense", return_value=[_make_result(retrieval_method="dense")])
    def test_hybrid_falls_back_to_dense(self, mock_dense):
        reset_retrieval_engine()
        engine = RetrievalEngine()
        results = engine.search_hybrid("test query", scope={"system": "am"})
        assert len(results) == 1
        mock_dense.assert_called_once()


class TestRerank:
    def test_rerank_passthrough(self):
        reset_retrieval_engine()
        engine = RetrievalEngine()
        candidates = [_make_result(), _make_result(subject="Java")]
        results = engine.rerank(candidates, "test")
        assert results == candidates


class TestGetSupportingChunks:
    @patch("app.core.retrieval.get_qdrant_client")
    @patch("app.core.retrieval.ensure_collection_exists")
    def test_returns_chunks_by_ids(self, mock_ensure, mock_client):
        reset_retrieval_engine()
        mock_point = MagicMock()
        mock_point.payload = {
            "subject": "Python",
            "predicate": "is_a",
            "object": "Language",
            "subject_id": "Python",
            "object_id": "Language",
            "chunk_id": "c1",
            "source_doc": "test.txt",
            "subject_type": "",
            "object_type": "",
        }
        mock_qdrant = MagicMock()
        mock_qdrant.scroll.return_value = ([mock_point], None)
        mock_client.return_value = mock_qdrant

        engine = RetrievalEngine()
        results = engine.get_supporting_chunks(["c1"])
        assert len(results) == 1
        assert results[0].retrieval_method == "chunk_lookup"

    def test_empty_ids_returns_empty(self):
        reset_retrieval_engine()
        engine = RetrievalEngine()
        results = engine.get_supporting_chunks([])
        assert results == []


class TestBuildFilter:
    @patch("app.core.retrieval.get_qdrant_client")
    @patch("app.core.retrieval.ensure_collection_exists")
    def test_none_filters_and_scope(self, mock_ensure, mock_client):
        reset_retrieval_engine()
        engine = RetrievalEngine()
        result = engine._build_filter(None, None)
        assert result is None

    def test_scope_only(self):
        reset_retrieval_engine()
        engine = RetrievalEngine()
        result = engine._build_filter(None, {"system": "support"})
        assert result is not None

    def test_filters_only(self):
        reset_retrieval_engine()
        engine = RetrievalEngine()
        result = engine._build_filter({"source_doc": "test.txt"}, None)
        assert result is not None

    def test_both_merged(self):
        reset_retrieval_engine()
        engine = RetrievalEngine()
        result = engine._build_filter({"source_doc": "test.txt"}, {"system": "support"})
        assert result is not None
        assert len(result.must) == 2


class TestSearchByFilter:
    @patch("app.core.retrieval.get_qdrant_client")
    @patch("app.core.retrieval.ensure_collection_exists")
    def test_returns_results_with_score_one(self, mock_ensure, mock_client):
        reset_retrieval_engine()
        mock_point = MagicMock()
        mock_point.payload = {
            "subject": "Qdrant",
            "predicate": "is_a",
            "object": "Database",
            "subject_id": "Qdrant",
            "object_id": "Database",
            "chunk_id": "c1",
            "source_doc": "test.txt",
            "subject_type": "",
            "object_type": "",
        }
        mock_qdrant = MagicMock()
        mock_qdrant.scroll.return_value = ([mock_point], None)
        mock_client.return_value = mock_qdrant

        engine = RetrievalEngine()
        results = engine.search_by_filter(
            filters={"product": "Qdrant"},
            scope={"system": "support"},
            active_only=True,
        )
        assert len(results) == 1
        assert results[0].score == 1.0
        assert results[0].retrieval_method == "filter"


class TestSearchByProductTool:
    @patch("app.agents.tools.retrieval_tools.get_retrieval_engine")
    def test_returns_formatted_results(self, mock_engine_get):
        mock_engine = MagicMock()
        mock_engine.search_by_filter.return_value = [
            _make_result(subject="Qdrant", predicate="affects", object="v1.17", source_doc="doc1.txt"),
        ]
        mock_engine_get.return_value = mock_engine

        result = search_by_product("Qdrant")
        assert "Qdrant" in result
        assert "doc1.txt" in result

    @patch("app.agents.tools.retrieval_tools.get_retrieval_engine")
    def test_no_results(self, mock_engine_get):
        mock_engine = MagicMock()
        mock_engine.search_by_filter.return_value = []
        mock_engine_get.return_value = mock_engine

        result = search_by_product("NonExistent")
        assert "No results found" in result

    @patch("app.agents.tools.retrieval_tools.get_retrieval_engine")
    def test_passes_version_filter(self, mock_engine_get):
        mock_engine = MagicMock()
        mock_engine.search_by_filter.return_value = []
        mock_engine_get.return_value = mock_engine

        search_by_product("Qdrant", version="1.17")
        call_args = mock_engine.search_by_filter.call_args
        filters = call_args.kwargs["filters"]
        assert "version" in filters


class TestGetResolutionHistoryTool:
    @patch("app.agents.tools.retrieval_tools.get_retrieval_engine")
    def test_returns_resolution_chain(self, mock_engine_get):
        mock_engine = MagicMock()
        mock_engine.search_dense.return_value = [
            _make_result(
                subject="Bug1",
                predicate="has_symptom",
                object="Crash",
                subject_id="Bug1",
                object_id="Crash",
                score=0.9,
            ),
        ]
        mock_engine.expand_from_graph.return_value = [
            SearchResult(
                subject="Bug1",
                predicate="resolved_by",
                object="Patch1",
                score=1.0,
                source_doc="",
                chunk_id="",
                subject_id="Bug1",
                object_id="Patch1",
            ),
        ]
        mock_engine_get.return_value = mock_engine

        result = get_resolution_history("Bug1 causes crashes")
        assert "Bug1" in result
        assert "resolved_by" in result
        assert "Patch1" in result

    @patch("app.agents.tools.retrieval_tools.get_retrieval_engine")
    def test_no_issues_found(self, mock_engine_get):
        mock_engine = MagicMock()
        mock_engine.search_dense.return_value = []
        mock_engine_get.return_value = mock_engine

        result = get_resolution_history("nonexistent issue")
        assert "No issues found" in result


class TestEscalationPathTool:
    @patch("app.agents.tools.retrieval_tools.get_retrieval_engine")
    def test_returns_escalation_paths(self, mock_engine_get):
        mock_engine = MagicMock()
        mock_engine.search_dense.return_value = [
            _make_result(
                subject="Bug1",
                predicate="escalated_to",
                object="TeamA",
                subject_id="Bug1",
                object_id="TeamA",
                score=0.85,
            ),
        ]
        mock_engine.expand_from_graph.return_value = [
            SearchResult(
                subject="Bug1",
                predicate="escalated_to",
                object="SeniorSupport",
                score=1.0,
                source_doc="",
                chunk_id="",
                subject_id="Bug1",
                object_id="SeniorSupport",
            ),
        ]
        mock_engine_get.return_value = mock_engine

        result = escalation_path("Bug1 needs escalation")
        assert "escalated_to" in result
        assert "SeniorSupport" in result

    @patch("app.agents.tools.retrieval_tools.get_retrieval_engine")
    def test_no_issues_found(self, mock_engine_get):
        mock_engine = MagicMock()
        mock_engine.search_dense.return_value = []
        mock_engine_get.return_value = mock_engine

        result = escalation_path("nonexistent issue")
        assert "No issues found" in result


class TestTraverseIssueGraphTool:
    @patch("app.agents.tools.retrieval_tools.get_retrieval_engine")
    def test_includes_source_label(self, mock_engine_get):
        mock_engine = MagicMock()
        mock_engine.expand_from_graph.return_value = [
            SearchResult(
                subject="Bug1",
                predicate="caused_by",
                object="Misconfig",
                score=1.0,
                source_doc="doc1.txt",
                chunk_id="",
                subject_id="Bug1",
                object_id="Misconfig",
            ),
        ]
        mock_engine_get.return_value = mock_engine

        result = traverse_issue_graph("Bug1")
        assert "Bug1" in result
        assert "caused_by" in result
        assert "doc1.txt" in result

    @patch("app.agents.tools.retrieval_tools.get_retrieval_engine")
    def test_graph_source_when_no_source_doc(self, mock_engine_get):
        mock_engine = MagicMock()
        mock_engine.expand_from_graph.return_value = [
            SearchResult(
                subject="Bug1",
                predicate="caused_by",
                object="Misconfig",
                score=1.0,
                source_doc="",
                chunk_id="",
                subject_id="Bug1",
                object_id="Misconfig",
            ),
        ]
        mock_engine_get.return_value = mock_engine

        result = traverse_issue_graph("Bug1")
        assert "grafo" in result
