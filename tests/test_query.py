"""Unit tests for query pipeline."""

from unittest.mock import MagicMock, patch

from app.pipelines.query import (
    _compute_confidence,
    _fuse_context,
    _fuse_expansion_results,
    expand_query,
    generate_answer,
    query,
    search_similar_triplets,
    search_with_expansion,
    traverse_graph,
)


class TestFuseContext:
    def test_deduplication(self):
        vector_triplets = [
            {"subject": "Python", "predicate": "is_a", "object": "Language"},
        ]
        graph_triplets = [
            {"subject": "Python", "predicate": "is_a", "object": "Language"},
        ]
        context, fused = _fuse_context(vector_triplets, graph_triplets)
        assert len(fused) == 1

    def test_different_triplets_combined(self):
        vector_triplets = [
            {"subject": "Python", "predicate": "created_by", "object": "Guido"},
        ]
        graph_triplets = [
            {"subject": "Python", "predicate": "is_a", "object": "Language"},
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
            {"subject": "A", "predicate": "b", "object": "C"},
            {"subject": "D", "predicate": "e", "object": "F"},
        ]
        context, fused = _fuse_context(triplets, [])
        assert "- A b C" in context
        assert "- D e F" in context

    def test_vector_triplets_come_first(self):
        vector_triplets = [
            {"subject": "V", "predicate": "pv", "object": "VV"},
        ]
        graph_triplets = [
            {"subject": "G", "predicate": "pg", "object": "GG"},
        ]
        context, fused = _fuse_context(vector_triplets, graph_triplets)
        assert fused[0]["subject"] == "V"
        assert fused[1]["subject"] == "G"


class TestComputeConfidence:
    def test_empty_triplets(self):
        assert _compute_confidence([], 0) == 0.0

    def test_high_similarity(self):
        triplets = [{"score": 0.95}] * 3
        confidence = _compute_confidence(triplets, 5)
        assert confidence > 0.5
        assert confidence <= 1.0

    def test_low_similarity(self):
        triplets = [{"score": 0.1}]
        confidence = _compute_confidence(triplets, 1)
        assert confidence < 0.5

    def test_no_scores(self):
        triplets = [{}]
        confidence = _compute_confidence(triplets, 1)
        assert 0.0 <= confidence <= 1.0

    def test_confidence_bounded(self):
        triplets = [{"score": 0.0}]
        confidence = _compute_confidence(triplets, 0)
        assert confidence >= 0.0

    def test_coverage_factor_increases_confidence(self):
        triplets = [{"score": 0.8}]
        low_coverage = _compute_confidence(triplets, 1)
        high_coverage = _compute_confidence(triplets, 10)
        assert high_coverage >= low_coverage


class TestSearchSimilarTriplets:
    @patch("app.pipelines.query.get_embeddings")
    @patch("app.pipelines.query.get_qdrant_client")
    @patch("app.pipelines.query.ensure_collection_exists")
    def test_returns_triplets(self, mock_ensure, mock_client, mock_embeddings):
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
        assert results[0]["score"] == 0.95
        assert results[0]["subject"] == "Python"


class TestTraverseGraph:
    def test_empty_entity_ids(self):
        result = traverse_graph([])
        assert result == []

    @patch("app.pipelines.query.get_nebula_session")
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

    @patch("app.pipelines.query.get_nebula_session")
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
            {
                "subject": "Python",
                "predicate": "is_a",
                "object": "Language",
                "subject_id": "Python",
                "object_id": "Language",
                "chunk_id": "c1",
                "source_doc": "test.txt",
                "score": 0.95,
            }
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

    @patch("app.pipelines.query.generate_answer")
    @patch("app.pipelines.query._compute_confidence", return_value=0.85)
    @patch("app.pipelines.query.traverse_graph", return_value=[])
    @patch("app.pipelines.query.search_similar_triplets")
    def test_default_expand_is_false(self, mock_search, mock_traverse, mock_conf, mock_answer):
        """When expand is not passed, search_similar_triplets is called directly (no expansion)."""
        mock_search.return_value = [
            {
                "subject": "Python",
                "predicate": "is_a",
                "object": "Language",
                "subject_id": "Python",
                "object_id": "Language",
                "chunk_id": "c1",
                "source_doc": "test.txt",
                "score": 0.95,
            }
        ]
        mock_answer.return_value = "A language."

        query("What is Python?")
        mock_search.assert_called_once_with("What is Python?", 5)

    @patch("app.pipelines.query.generate_answer")
    @patch("app.pipelines.query._compute_confidence", return_value=0.85)
    @patch("app.pipelines.query.traverse_graph", return_value=[])
    @patch("app.pipelines.query.search_with_expansion")
    def test_expand_true_uses_expansion(self, mock_expand_search, mock_traverse, mock_conf, mock_answer):
        """When expand=True, search_with_expansion is used instead of search_similar_triplets."""
        mock_expand_search.return_value = [
            {
                "subject": "Python",
                "predicate": "is_a",
                "object": "Language",
                "subject_id": "Python",
                "object_id": "Language",
                "chunk_id": "c1",
                "source_doc": "test.txt",
                "score": 0.95,
            }
        ]
        mock_answer.return_value = "A language."

        result = query("What is Python?", expand=True)
        mock_expand_search.assert_called_once_with("What is Python?", 5)
        assert result.answer == "A language."


class TestExpandQuery:
    @patch("app.pipelines.query.get_settings")
    @patch("app.pipelines.query.gemini_generate")
    def test_expand_with_gemini(self, mock_gemini, mock_settings):
        """When Gemini is configured, use gemini_generate for expansion."""
        mock_settings.return_value.is_gemini_configured = True
        mock_gemini.return_value = "What programming language is Python?\nWho created Python?"

        variations = expand_query("Python")
        assert len(variations) == 2
        assert "What programming language is Python?" in variations
        assert "Who created Python?" in variations

    @patch("app.pipelines.query.get_settings")
    @patch("app.pipelines.query.get_llm")
    def test_expand_fallback_to_llm(self, mock_get_llm, mock_settings):
        """When Gemini is not configured, fall back to LangChain LLM."""
        mock_settings.return_value.is_gemini_configured = False
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "What kind of language is Python?\nExplain Python language"
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        variations = expand_query("Python")
        assert len(variations) == 2
        mock_get_llm.assert_called_once_with(temperature=0.3)

    @patch("app.pipelines.query.get_settings")
    @patch("app.pipelines.query.gemini_generate", side_effect=Exception("API error"))
    def test_expand_exception_returns_empty(self, mock_gemini, mock_settings):
        """When expansion fails, return an empty list (graceful degradation)."""
        mock_settings.return_value.is_gemini_configured = True
        variations = expand_query("Python")
        assert variations == []

    @patch("app.pipelines.query.get_settings")
    @patch("app.pipelines.query.gemini_generate")
    def test_expand_strips_blank_lines(self, mock_gemini, mock_settings):
        """Blank lines in LLM output are filtered out."""
        mock_settings.return_value.is_gemini_configured = True
        mock_gemini.return_value = "\nWhat is Python language?\n\nWho uses Python?\n"

        variations = expand_query("Python")
        assert len(variations) == 2

    @patch("app.pipelines.query.get_settings")
    @patch("app.pipelines.query.gemini_generate")
    def test_expand_vague_query_gets_relevant_terms(self, mock_gemini, mock_settings):
        """Vague queries get expanded with more specific terminology."""
        mock_settings.return_value.is_gemini_configured = True
        mock_gemini.return_value = (
            "What is the Python programming language used for?\n"
            "Explain the Python coding language\n"
            "What are applications of Python software"
        )

        variations = expand_query("tell me about python")
        assert len(variations) == 3
        # Each variation should contain relevant expanded terms
        for v in variations:
            assert len(v) > len("tell me about python") or "python" in v.lower()


class TestFuseExpansionResults:
    def test_deduplication_across_sets(self):
        """Same triplet from different queries should be deduplicated."""
        set_a = [{"subject": "Python", "predicate": "is_a", "object": "Language", "score": 0.9}]
        set_b = [{"subject": "Python", "predicate": "is_a", "object": "Language", "score": 0.85}]
        fused = _fuse_expansion_results([set_a, set_b])
        assert len(fused) == 1
        assert fused[0]["score"] == 0.9  # keeps higher score

    def test_different_triplets_combined(self):
        """Different triplets from different queries should all be kept."""
        set_a = [{"subject": "Python", "predicate": "is_a", "object": "Language", "score": 0.9}]
        set_b = [{"subject": "Guido", "predicate": "created", "object": "Python", "score": 0.8}]
        fused = _fuse_expansion_results([set_a, set_b])
        assert len(fused) == 2

    def test_sorted_by_score_descending(self):
        """Results should be sorted by score from highest to lowest."""
        set_a = [{"subject": "A", "predicate": "p", "object": "B", "score": 0.5}]
        set_b = [{"subject": "C", "predicate": "q", "object": "D", "score": 0.95}]
        set_c = [{"subject": "E", "predicate": "r", "object": "F", "score": 0.7}]
        fused = _fuse_expansion_results([set_a, set_b, set_c])
        assert fused[0]["score"] == 0.95
        assert fused[1]["score"] == 0.7
        assert fused[2]["score"] == 0.5

    def test_empty_input_sets(self):
        """Empty input list returns empty results."""
        fused = _fuse_expansion_results([])
        assert fused == []

    def test_empty_result_sets(self):
        """List of empty result sets returns empty results."""
        fused = _fuse_expansion_results([[], [], []])
        assert fused == []

    def test_single_set(self):
        """Single result set works correctly."""
        set_a = [
            {"subject": "A", "predicate": "p", "object": "B", "score": 0.9},
            {"subject": "C", "predicate": "q", "object": "D", "score": 0.8},
        ]
        fused = _fuse_expansion_results([set_a])
        assert len(fused) == 2

    def test_keeps_highest_score_for_duplicates(self):
        """When the same triplet appears with different scores, keep the highest."""
        set_a = [{"subject": "X", "predicate": "rel", "object": "Y", "score": 0.5}]
        set_b = [{"subject": "X", "predicate": "rel", "object": "Y", "score": 0.99}]
        set_c = [{"subject": "X", "predicate": "rel", "object": "Y", "score": 0.7}]
        fused = _fuse_expansion_results([set_a, set_b, set_c])
        assert len(fused) == 1
        assert fused[0]["score"] == 0.99


class TestSearchWithExpansion:
    @patch("app.pipelines.query.search_similar_triplets")
    @patch("app.pipelines.query.expand_query")
    def test_searches_original_and_variations(self, mock_expand, mock_search):
        """Search is called for the original query plus each variation."""
        mock_expand.return_value = ["What is Python language?", "Explain Python"]
        mock_search.return_value = []

        search_with_expansion("Python", top_k=5)

        assert mock_search.call_count == 3  # original + 2 variations
        mock_search.assert_any_call("Python", 5)
        mock_search.assert_any_call("What is Python language?", 5)
        mock_search.assert_any_call("Explain Python", 5)

    @patch("app.pipelines.query.search_similar_triplets")
    @patch("app.pipelines.query.expand_query")
    def test_fuses_results_across_variations(self, mock_expand, mock_search):
        """Results from all variations are fused and deduplicated."""
        mock_expand.return_value = ["What is Python language?"]

        result_a = [{"subject": "Python", "predicate": "is_a", "object": "Language", "score": 0.9}]
        result_b = [{"subject": "Python", "predicate": "is_a", "object": "Language", "score": 0.8}]
        mock_search.side_effect = [result_a, result_b]

        fused = search_with_expansion("Python", top_k=5)
        assert len(fused) == 1  # deduplicated
        assert fused[0]["score"] == 0.9  # keeps higher score

    @patch("app.pipelines.query.search_similar_triplets")
    @patch("app.pipelines.query.expand_query")
    def test_no_variations_searches_only_original(self, mock_expand, mock_search):
        """When expansion returns no variations, only the original query is searched."""
        mock_expand.return_value = []
        mock_search.return_value = [{"subject": "A", "predicate": "b", "object": "C", "score": 0.8}]

        fused = search_with_expansion("Python", top_k=5)
        mock_search.assert_called_once_with("Python", 5)
        assert len(fused) == 1

    @patch("app.pipelines.query.search_similar_triplets")
    @patch("app.pipelines.query.expand_query")
    def test_expansion_retrieves_documents_original_missed(self, mock_expand, mock_search):
        """Expanded queries can retrieve triplets the original query missed."""
        mock_expand.return_value = ["Who created the Python language?"]

        # Original finds only "is_a" triplet
        original_result = [{"subject": "Python", "predicate": "is_a", "object": "Language", "score": 0.9}]
        # Variation finds an additional "created_by" triplet
        variation_result = [{"subject": "Python", "predicate": "created_by", "object": "Guido", "score": 0.85}]
        mock_search.side_effect = [original_result, variation_result]

        fused = search_with_expansion("Python", top_k=5)
        assert len(fused) == 2
        predicates = {t["predicate"] for t in fused}
        assert "is_a" in predicates
        assert "created_by" in predicates
