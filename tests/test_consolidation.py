"""Tests for the consolidation pipeline (real logic, mocked Qdrant)."""

from unittest.mock import MagicMock

from app.pipelines.consolidation import apply_supersession


class TestApplySupersession:
    """Exercise the real consolidation logic with only Qdrant mocked."""

    def test_superseded_fact_fields(self):
        """Old fact gets valid_to, is_active=False, superseded_by."""
        mock_client = MagicMock()

        old_fact_id = "old-fact-001"
        old_fact = {
            "subject": "Python",
            "predicate": "version",
            "object": "3.11",
            "is_active": True,
            "valid_from": "2024-01-01T00:00:00+00:00",
        }

        new_fact_id = "new-fact-002"
        new_fact = {
            "subject": "Python",
            "predicate": "version",
            "object": "3.12",
            "_vector": [0.1] * 1536,
        }

        apply_supersession(old_fact_id, old_fact, new_fact_id, new_fact, mock_client, "triplets")

        # Old fact is no longer active
        assert old_fact["is_active"] is False
        # A valid_to timestamp was set
        assert old_fact["valid_to"] is not None
        # The superseding fact is referenced
        assert old_fact["superseded_by"] == new_fact_id

    def test_new_fact_fields(self):
        """New fact has valid_from and is_active=True."""
        mock_client = MagicMock()

        old_fact_id = "old-fact-001"
        old_fact = {
            "subject": "Python",
            "predicate": "version",
            "object": "3.11",
            "is_active": True,
        }

        new_fact_id = "new-fact-002"
        new_fact = {
            "subject": "Python",
            "predicate": "version",
            "object": "3.12",
            "_vector": [0.1] * 1536,
        }

        apply_supersession(old_fact_id, old_fact, new_fact_id, new_fact, mock_client, "triplets")

        # New fact is active
        assert new_fact["is_active"] is True
        # A valid_from timestamp was set
        assert new_fact["valid_from"] is not None

    def test_qdrant_set_payload_called(self):
        """set_payload is called on the Qdrant client for the old fact."""
        mock_client = MagicMock()

        old_fact_id = "old-fact-001"
        old_fact = {"subject": "A", "predicate": "b", "object": "C", "is_active": True}
        new_fact_id = "new-fact-002"
        new_fact = {"subject": "A", "predicate": "b", "object": "D", "_vector": [0.1] * 1536}

        apply_supersession(old_fact_id, old_fact, new_fact_id, new_fact, mock_client, "triplets")

        mock_client.set_payload.assert_called_once()
        call_kwargs = mock_client.set_payload.call_args[1]
        assert call_kwargs["collection_name"] == "triplets"
        assert call_kwargs["payload"]["is_active"] is False
        assert call_kwargs["payload"]["superseded_by"] == new_fact_id
        assert "valid_to" in call_kwargs["payload"]
        assert call_kwargs["points"] == [old_fact_id]

    def test_qdrant_upsert_called(self):
        """upsert is called on the Qdrant client for the new fact."""
        mock_client = MagicMock()

        old_fact_id = "old-fact-001"
        old_fact = {"subject": "A", "predicate": "b", "object": "C", "is_active": True}
        new_fact_id = "new-fact-002"
        new_fact = {"subject": "A", "predicate": "b", "object": "D", "_vector": [0.1] * 1536}

        apply_supersession(old_fact_id, old_fact, new_fact_id, new_fact, mock_client, "triplets")

        mock_client.upsert.assert_called_once()
        call_kwargs = mock_client.upsert.call_args[1]
        assert call_kwargs["collection_name"] == "triplets"
        assert len(call_kwargs["points"]) == 1
        point = call_kwargs["points"][0]
        assert point.id == new_fact_id
        assert point.payload["is_active"] is True
        assert "valid_from" in point.payload
        # _vector key must not leak into the payload
        assert "_vector" not in point.payload

    def test_vector_popped_from_new_fact_payload(self):
        """The _vector key is removed from the payload dict before it reaches Qdrant."""
        mock_client = MagicMock()

        old_fact = {"subject": "A", "predicate": "b", "object": "C", "is_active": True}
        new_fact = {"subject": "A", "predicate": "b", "object": "D", "_vector": [0.1] * 1536}

        apply_supersession("old-1", old_fact, "new-1", new_fact, mock_client, "triplets")

        # After the call, _vector should have been popped from new_fact
        assert "_vector" not in new_fact
