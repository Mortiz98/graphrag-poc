"""Unit tests for query pipeline."""

from unittest.mock import MagicMock, patch

from app.core.retrieval import SearchResult, reset_retrieval_engine
from app.pipelines.query import (
    _compute_confidence,
    _fuse_context,
    generate_answer,
    query,
    search_similar_triplets,
    traverse_graph,
)


def make_search_result(**kwargs) -> SearchResult:
    defaults = {
        "subject": "",
        "predicate": "",
        "object": "",
        "score": 0.0,
        "source_doc": "",
        "chunk_id": "",
        "subject_id": "",
        "object_id": "",
        "metadata": {},
        "retrieval_method": "",
        "scope": {},
    }
    defaults.update(kwargs)
    return SearchResult(**defaults)


class TestFuseContext:
    def test_deduplication(self):
        vector_triplets = [
            make_search_result(subject="Python", predicate="is_a", object="Language"),
        ]
        graph_triplets = [
            make_search_result(subject="Python", predicate="is_a", object="Language"),
        ]
        context, fused = _fuse_context(vector_triplets, graph_triplets)
        assert len(fused) == 1

    def test_different_triplets_combined(self):
        vector_triplets = [
            make_search_result(subject="Python", predicate="created_by", object="Guido"),
        ]
        graph_triplets = [
            make_search_result(subject="Python", predicate="is_a", object="Language"),
        ]
        context, fused = _fuse_context(vector_triplets, graph_triplets)
        assert len(fused) == 2
        assert "Python created_by Guido" in context
        assert "Python is_a Language" in context

    def test_empty_inputs(self):
        context, fused = _fuse_context([], [])
        assert context == ""
        assert len(fused) == 0

    def test_context_format(self):
        triplets = [
            make_search_result(subject="A", predicate="b", object="C"),
            make_search_result(subject="D", predicate="e", object="F"),
        ]
        context, fused = _fuse_context(triplets, [])
        assert "- A b C" in context
        assert "- D e F" in context

    def test_vector_triplets_come_first(self):
        vector_triplets = [
            make_search_result(subject="V", predicate="pv", object="VV"),
        ]
        graph_triplets = [
            make_search_result(subject="G", predicate="pg", object="GG"),
        ]
        context, fused = _fuse_context(vector_triplets, graph_triplets)
        assert fused[0].subject == "V"
        assert fused[1].subject == "G"


class TestComputeConfidence:
    def test_empty_triplets(self):
        assert _compute_confidence([], 0) == 0.0

    def test_high_similarity(self):
        triplets = [make_search_result(score=0.95) for _ in range(3)]
        confidence = _compute_confidence(triplets, 5)
        assert confidence > 0.5
        assert confidence <= 1.0

    def test_low_similarity(self):
        triplets = [make_search_result(score=0.1)]
        confidence = _compute_confidence(triplets, 1)
        assert confidence < 0.5

    def test_no_scores(self):
        triplets = [make_search_result(score=0.0)]
        confidence = _compute_confidence(triplets, 1)
        assert 0.0 <= confidence <= 1.0

    def test_confidence_bounded(self):
        triplets = [make_search_result(score=0.0)]
        confidence = _compute_confidence(triplets, 0)
        assert confidence >= 0.0

    def test_coverage_factor_increases_confidence(self):
        triplets = [make_search_result(score=0.8)]
        low_coverage = _compute_confidence(triplets, 1)
        high_coverage = _compute_confidence(triplets, 10)
        assert high_coverage >= low_coverage


class TestSearchSimilarTriplets:
    @patch("app.core.retrieval.get_embeddings")
    @patch("app.core.retrieval.get_qdrant_client")
    @patch("app.core.retrieval.ensure_collection_exists")
    def test_returns_triplets(self, mock_ensure, mock_client, mock_embeddings):
        reset_retrieval_engine()

        mock_emb = MagicMock()
        mock_emb.embed_query.return_value = [0.1] * 1536
        mock_embeddings.return_value = mock_emb

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
        mock_point.score = 0.95

        mock_qdrant = MagicMock()
        mock_results = MagicMock()
        mock_results.points = [mock_point]
        mock_qdrant.query_points.return_value = mock_results
        mock_client.return_value = mock_qdrant

        results = search_similar_triplets("What is Python?")
        assert len(results) == 1
        assert results[0].score == 0.95
        assert results[0].subject == "Python"


class TestTraverseGraph:
    def test_empty_entity_ids(self):
        result = traverse_graph([])
        assert result == []

    @patch("app.core.retrieval.get_nebula_session")
    def test_successful_traversal(self, mock_session_ctx):
        mock_session = MagicMock()
        mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

        mock_row = MagicMock()
        mock_row.values = [MagicMock(), MagicMock(), MagicMock()]
        mock_row.values[0].get_sVal.return_value = b"Python"
        mock_row.values[1].get_sVal.return_value = b"Language"
        mock_row.values[2].get_sVal.return_value = b"is_a"

        go_result = MagicMock()
        go_result.is_succeeded.return_value = True
        go_result.rows.return_value = [mock_row]

        failed_result = MagicMock()
        failed_result.is_succeeded.return_value = False

        mock_session.execute.side_effect = [go_result, go_result, failed_result, failed_result]

        results = traverse_graph(["Python"])
        assert len(results) >= 1

    @patch("app.core.retrieval.get_nebula_session")
    def test_failed_query_returns_empty(self, mock_session_ctx):
        mock_session = MagicMock()
        mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

        failed_result = MagicMock()
        failed_result.is_succeeded.return_value = False
        mock_session.execute.return_value = failed_result

        results = traverse_graph(["nonexistent"])
        assert results == []


class TestGenerateAnswer:
    @patch("app.pipelines.query.get_llm")
    def test_returns_answer(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Python is a programming language."
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        answer = generate_answer("What is Python?", "- Python is_a Language")
        assert answer == "Python is a programming language."

    @patch("app.pipelines.query.get_llm")
    def test_empty_context_returns_default(self, mock_get_llm):
        answer = generate_answer("What is Python?", "")
        assert "could not find" in answer.lower()
        mock_get_llm.assert_not_called()


class TestQuery:
    @patch("app.pipelines.query.generate_answer")
    @patch("app.pipelines.query._compute_confidence", return_value=0.85)
    @patch("app.pipelines.query.traverse_graph", return_value=[])
    @patch("app.pipelines.query.search_similar_triplets")
    def test_full_query(self, mock_search, mock_traverse, mock_conf, mock_answer):
        mock_search.return_value = [
            make_search_result(
                subject="Python",
                predicate="is_a",
                object="Language",
                subject_id="Python",
                object_id="Language",
                chunk_id="c1",
                source_doc="test.txt",
                score=0.95,
            )
        ]
        mock_answer.return_value = "Python is a language."

        result = query("What is Python?")
        assert result.answer == "Python is a language."
        assert result.confidence == 0.85
        assert len(result.sources) == 1
        assert "Python" in result.entities_found

    @patch("app.pipelines.query.generate_answer")
    @patch("app.pipelines.query._compute_confidence", return_value=0.0)
    @patch("app.pipelines.query.traverse_graph", return_value=[])
    @patch("app.pipelines.query.search_similar_triplets", return_value=[])
    def test_no_results(self, mock_search, mock_traverse, mock_conf, mock_answer):
        mock_answer.return_value = "No info found."
        result = query("Obscure question")
        assert result.confidence == 0.0
        assert result.sources == []
