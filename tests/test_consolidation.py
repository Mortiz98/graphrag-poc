"""Unit tests for consolidation pipeline."""

from unittest.mock import MagicMock, patch

from app.models.schemas import CaseMetadata, FactMetadata
from app.pipelines.consolidation import (
    MEMORY_TYPE_EPISODIC,
    MEMORY_TYPE_PROCEDURAL,
    MEMORY_TYPE_SEMANTIC,
    MEMORY_TYPE_STATE,
    classify_memory,
    deduplicate_against_existing,
    run_consolidation_pipeline,
)


class TestClassifyMemory:
    def test_fact_type_fact(self):
        assert classify_memory("fact") == MEMORY_TYPE_STATE

    def test_fact_type_episode(self):
        assert classify_memory("episode") == MEMORY_TYPE_EPISODIC

    def test_fact_type_commitment(self):
        assert classify_memory("commitment") == MEMORY_TYPE_STATE

    def test_fact_type_stakeholder(self):
        assert classify_memory("stakeholder") == MEMORY_TYPE_STATE

    def test_fact_type_preference(self):
        assert classify_memory("preference") == MEMORY_TYPE_PROCEDURAL

    def test_none_support_system(self):
        assert classify_memory(None, "support") == MEMORY_TYPE_SEMANTIC

    def test_none_am_system(self):
        assert classify_memory(None, "am") == MEMORY_TYPE_EPISODIC


class TestDeduplicateAgainstExisting:
    @patch("app.pipelines.consolidation.get_retrieval_engine")
    def test_removes_duplicates(self, mock_get_engine):
        mock_engine = MagicMock()
        from app.core.retrieval import SearchResult

        dup_result = SearchResult(
            subject="Python",
            predicate="is_a",
            object="Language",
            score=0.99,
            source_doc="",
            chunk_id="",
            subject_id="",
            object_id="",
        )
        mock_engine.search_dense.return_value = [dup_result]
        mock_get_engine.return_value = mock_engine

        triplets = [{"subject": "Python", "predicate": "is_a", "object": "Language"}]
        result = deduplicate_against_existing(triplets)
        assert len(result) == 0

    @patch("app.pipelines.consolidation.get_retrieval_engine")
    def test_keeps_unique(self, mock_get_engine):
        mock_engine = MagicMock()
        mock_engine.search_dense.return_value = []
        mock_get_engine.return_value = mock_engine

        triplets = [{"subject": "Java", "predicate": "is_a", "object": "Language"}]
        result = deduplicate_against_existing(triplets)
        assert len(result) == 1

    @patch("app.pipelines.consolidation.get_retrieval_engine")
    def test_mixed_results(self, mock_get_engine):
        mock_engine = MagicMock()
        from app.core.retrieval import SearchResult

        dup = SearchResult(
            subject="Python",
            predicate="is_a",
            object="Language",
            score=0.99,
            source_doc="",
            chunk_id="",
            subject_id="",
            object_id="",
        )
        mock_engine.search_dense.side_effect = [[dup], []]
        mock_get_engine.return_value = mock_engine

        triplets = [
            {"subject": "Python", "predicate": "is_a", "object": "Language"},
            {"subject": "Java", "predicate": "is_a", "object": "Language"},
        ]
        result = deduplicate_against_existing(triplets)
        assert len(result) == 1
        assert result[0]["subject"] == "Java"


class TestRunConsolidationPipeline:
    @patch("app.pipelines.consolidation.apply_supersession", side_effect=lambda x, **kw: x)
    @patch("app.pipelines.consolidation.deduplicate_against_existing", side_effect=lambda x, **kw: x)
    def test_adds_metadata(self, mock_dedup, mock_supersede):
        triplets = [{"subject": "A", "predicate": "b", "object": "C"}]
        result = run_consolidation_pipeline(
            triplets,
            system="support",
            source_doc="test.txt",
            fact_metadata=FactMetadata(account_id="ACC-1", fact_type="episode"),
        )
        assert len(result) == 1
        assert result[0]["system"] == "support"
        assert result[0]["source_doc"] == "test.txt"
        assert result[0]["account_id"] == "ACC-1"
        assert result[0]["memory_type"] == MEMORY_TYPE_EPISODIC
        assert "created_at" in result[0]
        assert "ingestion_batch" in result[0]

    @patch("app.pipelines.consolidation.apply_supersession", side_effect=lambda x, **kw: x)
    @patch("app.pipelines.consolidation.deduplicate_against_existing", side_effect=lambda x, **kw: x)
    def test_case_metadata_merged(self, mock_dedup, mock_supersede):
        triplets = [{"subject": "A", "predicate": "b", "object": "C"}]
        result = run_consolidation_pipeline(
            triplets,
            system="support",
            case_metadata=CaseMetadata(case_id="CASE-1", product="API"),
        )
        assert result[0]["case_id"] == "CASE-1"
        assert result[0]["product"] == "API"

    @patch("app.pipelines.consolidation.apply_supersession", side_effect=lambda x, **kw: x)
    def test_skip_dedup(self, mock_supersede):
        triplets = [{"subject": "A", "predicate": "b", "object": "C"}]
        result = run_consolidation_pipeline(triplets, skip_dedup=True)
        assert len(result) == 1

    @patch("app.pipelines.consolidation.deduplicate_against_existing", side_effect=lambda x, **kw: x)
    def test_skip_supersede(self, mock_dedup):
        triplets = [{"subject": "A", "predicate": "b", "object": "C"}]
        result = run_consolidation_pipeline(triplets, skip_supersede=True)
        assert len(result) == 1
