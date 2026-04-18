"""Unit tests for RetrievalEngine extended methods."""

from unittest.mock import MagicMock, patch

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
    @patch("app.core.retrieval.get_embeddings")
    @patch("app.core.retrieval.get_qdrant_client")
    @patch("app.core.retrieval.ensure_collection_exists")
    def test_scope_merged_into_filter(self, mock_ensure, mock_client, mock_embeddings):
        reset_retrieval_engine()
        mock_emb = MagicMock()
        mock_emb.embed_query.return_value = [0.1] * 768
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
