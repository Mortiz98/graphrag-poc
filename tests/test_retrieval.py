"""Unit tests for retrieval module: sparse vectors, dense search, hybrid search."""

from unittest.mock import MagicMock, patch

from app.core.retrieval import (
    _tokenize,
    search_dense,
    search_hybrid,
    search_sparse,
    text_to_sparse_vector,
)


class TestTokenize:
    def test_simple_text(self):
        assert _tokenize("hello world") == ["hello", "world"]

    def test_lowercases(self):
        assert _tokenize("Hello World") == ["hello", "world"]

    def test_strips_punctuation(self):
        assert _tokenize("Error 368: account restricted!") == ["error", "368", "account", "restricted"]

    def test_empty_string(self):
        assert _tokenize("") == []

    def test_only_punctuation(self):
        assert _tokenize("!!! ???") == []

    def test_underscores_preserved(self):
        assert _tokenize("my_variable") == ["my_variable"]

    def test_numbers_preserved(self):
        assert _tokenize("Error 368") == ["error", "368"]


class TestTextToSparseVector:
    def test_produces_non_empty_vector(self):
        sv = text_to_sparse_vector("hello world")
        assert len(sv.indices) > 0
        assert len(sv.values) > 0
        assert len(sv.indices) == len(sv.values)

    def test_empty_text_returns_empty_vector(self):
        sv = text_to_sparse_vector("")
        assert sv.indices == []
        assert sv.values == []

    def test_term_frequencies_as_values(self):
        text = "error error 368"
        sv = text_to_sparse_vector(text)
        # "error" appears twice, "368" once
        assert 2.0 in sv.values
        assert 1.0 in sv.values

    def test_indices_are_sorted(self):
        sv = text_to_sparse_vector("b a c")
        assert sv.indices == sorted(sv.indices)

    def test_unique_tokens_only(self):
        text = "hello hello hello"
        sv = text_to_sparse_vector(text)
        assert len(sv.indices) == 1
        assert sv.values[0] == 3.0

    def test_indices_are_consistent_for_same_token(self):
        sv1 = text_to_sparse_vector("error 368")
        sv2 = text_to_sparse_vector("error 368")
        assert sv1.indices == sv2.indices

    def test_acceptance_query(self):
        """Test the exact acceptance criterion query."""
        sv = text_to_sparse_vector("Error 368 account restricted")
        # Should have indices for "error", "368", "account", "restricted"
        assert len(sv.indices) == 4
        assert all(v == 1.0 for v in sv.values)


class TestSearchSparse:
    @patch("app.core.retrieval.get_qdrant_client")
    @patch("app.core.retrieval.ensure_collection_exists")
    @patch("app.core.retrieval.get_settings")
    def test_returns_triplets(self, mock_settings, mock_ensure, mock_client):
        mock_settings.return_value = MagicMock(qdrant_collection_name="triplets")

        mock_point = MagicMock()
        mock_point.payload = {
            "subject": "Error 368",
            "predicate": "indicates",
            "object": "account restricted",
            "subject_id": "Error_368",
            "object_id": "account_restricted",
            "chunk_id": "c1",
            "source_doc": "errors.txt",
        }
        mock_point.score = 0.95

        mock_qdrant = MagicMock()
        mock_results = MagicMock()
        mock_results.points = [mock_point]
        mock_qdrant.query_points.return_value = mock_results
        mock_client.return_value = mock_qdrant

        results = search_sparse("Error 368 account restricted")
        assert len(results) == 1
        assert results[0]["subject"] == "Error 368"
        assert results[0]["score"] == 0.95
        # Verify query used sparse vector
        call_kwargs = mock_qdrant.query_points.call_args[1]
        assert call_kwargs["using"] == "sparse"

    @patch("app.core.retrieval.get_qdrant_client")
    @patch("app.core.retrieval.ensure_collection_exists")
    @patch("app.core.retrieval.get_settings")
    def test_empty_query_returns_empty(self, mock_settings, mock_ensure, mock_client):
        mock_settings.return_value = MagicMock(qdrant_collection_name="triplets")
        results = search_sparse("")
        assert results == []

    @patch("app.core.retrieval.get_qdrant_client")
    @patch("app.core.retrieval.ensure_collection_exists")
    @patch("app.core.retrieval.get_settings")
    def test_top_k_passed(self, mock_settings, mock_ensure, mock_client):
        mock_settings.return_value = MagicMock(qdrant_collection_name="triplets")
        mock_qdrant = MagicMock()
        mock_results = MagicMock()
        mock_results.points = []
        mock_qdrant.query_points.return_value = mock_results
        mock_client.return_value = mock_qdrant

        search_sparse("test query", top_k=10)
        call_kwargs = mock_qdrant.query_points.call_args[1]
        assert call_kwargs["limit"] == 10


class TestSearchDense:
    @patch("app.core.retrieval.get_embeddings")
    @patch("app.core.retrieval.get_qdrant_client")
    @patch("app.core.retrieval.ensure_collection_exists")
    @patch("app.core.retrieval.get_settings")
    def test_returns_triplets(self, mock_settings, mock_ensure, mock_client, mock_embeddings):
        mock_settings.return_value = MagicMock(qdrant_collection_name="triplets")

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
        mock_point.score = 0.92

        mock_qdrant = MagicMock()
        mock_results = MagicMock()
        mock_results.points = [mock_point]
        mock_qdrant.query_points.return_value = mock_results
        mock_client.return_value = mock_qdrant

        results = search_dense("What is Python?")
        assert len(results) == 1
        assert results[0]["subject"] == "Python"
        assert results[0]["score"] == 0.92
        # Verify query used dense vector
        call_kwargs = mock_qdrant.query_points.call_args[1]
        assert call_kwargs["using"] == "dense"


class TestSearchHybrid:
    @patch("app.core.retrieval.get_embeddings")
    @patch("app.core.retrieval.get_qdrant_client")
    @patch("app.core.retrieval.ensure_collection_exists")
    @patch("app.core.retrieval.get_settings")
    def test_returns_fused_results(self, mock_settings, mock_ensure, mock_client, mock_embeddings):
        mock_settings.return_value = MagicMock(qdrant_collection_name="triplets")

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
        mock_point.score = 0.9

        mock_qdrant = MagicMock()
        mock_results = MagicMock()
        mock_results.points = [mock_point]
        mock_qdrant.query_points.return_value = mock_results
        mock_client.return_value = mock_qdrant

        results = search_hybrid("What is Python?")
        assert len(results) == 1
        assert results[0]["subject"] == "Python"
        # Verify hybrid query structure with prefetch
        call_kwargs = mock_qdrant.query_points.call_args[1]
        assert "prefetch" in call_kwargs
        assert len(call_kwargs["prefetch"]) == 2

    @patch("app.core.retrieval.search_dense")
    @patch("app.core.retrieval.get_embeddings")
    @patch("app.core.retrieval.get_qdrant_client")
    @patch("app.core.retrieval.ensure_collection_exists")
    @patch("app.core.retrieval.get_settings")
    def test_falls_back_to_dense_when_empty_sparse(  # noqa: E501
        self, mock_settings, mock_ensure, mock_client, mock_embeddings, mock_search_dense
    ):
        mock_settings.return_value = MagicMock(qdrant_collection_name="triplets")
        mock_emb = MagicMock()
        mock_emb.embed_query.return_value = [0.1] * 1536
        mock_embeddings.return_value = mock_emb
        mock_search_dense.return_value = [{"subject": "test", "score": 0.5}]

        # Empty query → empty sparse vector → fallback to dense
        results = search_hybrid("")
        assert results == [{"subject": "test", "score": 0.5}]
        mock_search_dense.assert_called_once()
