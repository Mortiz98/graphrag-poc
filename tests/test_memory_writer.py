"""Unit tests for memory writer."""

from unittest.mock import MagicMock, patch

from app.pipelines.memory_writer import record_fact, supersede_fact, write_facts_to_store


class TestWriteFactsToStore:
    @patch("app.pipelines.memory_writer.get_embeddings")
    @patch("app.pipelines.memory_writer.get_qdrant_client")
    @patch("app.pipelines.memory_writer.ensure_collection_exists")
    def test_writes_facts(self, mock_ensure, mock_client, mock_embeddings):
        mock_emb = MagicMock()
        mock_emb.embed_documents.return_value = [[0.1] * 768]
        mock_embeddings.return_value = mock_emb
        mock_qdrant = MagicMock()
        mock_client.return_value = mock_qdrant

        facts = [{"id": "id1", "subject": "A", "predicate": "b", "object": "C", "system": "am"}]
        result = write_facts_to_store(facts, system="am")
        assert result == 1
        mock_qdrant.upsert.assert_called_once()

    def test_empty_facts(self):
        result = write_facts_to_store([])
        assert result == 0


class TestRecordFact:
    @patch("app.pipelines.memory_writer.write_facts_to_store", return_value=1)
    def test_records_fact(self, mock_write):
        fact_id = record_fact(
            subject="ACC-1",
            predicate="has_tier",
            object_="Enterprise",
            system="am",
            account_id="ACC-1",
            fact_type="fact",
        )
        assert fact_id is not None
        mock_write.assert_called_once()
        call_args = mock_write.call_args[0][0]
        assert call_args[0]["subject"] == "ACC-1"
        assert call_args[0]["system"] == "am"

    @patch("app.pipelines.memory_writer.write_facts_to_store", return_value=1)
    def test_fact_with_validity(self, mock_write):
        fact_id = record_fact(
            subject="Commitment",
            predicate="due_by",
            object_="Q2 2026",
            fact_type="commitment",
            valid_from="2026-01-01T00:00:00Z",
            valid_to="2026-06-30T23:59:59Z",
        )
        assert fact_id is not None
        call_args = mock_write.call_args[0][0]
        assert call_args[0]["valid_from"] == "2026-01-01T00:00:00Z"
        assert call_args[0]["valid_to"] == "2026-06-30T23:59:59Z"


class TestSupersedeFact:
    @patch("app.pipelines.memory_writer.get_qdrant_client")
    @patch("app.pipelines.memory_writer.write_facts_to_store", return_value=1)
    def test_supersedes_old_fact(self, mock_write, mock_client):
        mock_qdrant = MagicMock()
        mock_client.return_value = mock_qdrant

        new_id = supersede_fact(
            old_fact_id="old-123",
            new_subject="ACC-1",
            new_predicate="has_tier",
            new_object="Premium",
            system="am",
            account_id="ACC-1",
        )
        assert new_id is not None
        mock_qdrant.set_payload.assert_called_once()
        mock_write.assert_called_once()
