"""Unit tests for vectorstore module."""

from unittest.mock import MagicMock, patch

from app.core.vectorstore import (
    check_qdrant_health,
    ensure_collection_exists,
    get_unique_source_docs,
    scroll_by_source_doc,
)


class TestEnsureCollectionExists:
    @patch("app.core.vectorstore._ensure_payload_indexes")
    def test_creates_collection_if_missing(self, mock_indexes):
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.name = "other"
        mock_client.get_collections.return_value = MagicMock(collections=[mock_collection])

        ensure_collection_exists(mock_client, "test_coll")

        mock_client.create_collection.assert_called_once()

    @patch("app.core.vectorstore._ensure_payload_indexes")
    def test_skips_if_exists(self, mock_indexes):
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.name = "triplets"
        mock_client.get_collections.return_value = MagicMock(collections=[mock_collection])

        ensure_collection_exists(mock_client, "triplets")

        mock_client.create_collection.assert_not_called()


class TestScrollBySourceDoc:
    def test_returns_matching_points(self):
        mock_client = MagicMock()
        point1 = MagicMock()
        point1.payload = {"source_doc": "target.txt"}
        point2 = MagicMock()
        point2.payload = {"source_doc": "other.txt"}

        mock_client.scroll.side_effect = [
            ([point1], "offset_val"),
            ([], None),
        ]

        results = scroll_by_source_doc(mock_client, "triplets", "target.txt")
        assert len(results) == 1

    def test_returns_empty_when_none_match(self):
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)

        results = scroll_by_source_doc(mock_client, "triplets", "nonexistent.txt")
        assert results == []


class TestGetUniqueSourceDocs:
    def test_groups_by_source(self):
        mock_client = MagicMock()
        p1 = MagicMock()
        p1.id = "id1"
        p1.payload = {"source_doc": "a.txt", "chunk_id": "c1"}
        p2 = MagicMock()
        p2.id = "id2"
        p2.payload = {"source_doc": "a.txt", "chunk_id": "c2"}
        p3 = MagicMock()
        p3.id = "id3"
        p3.payload = {"source_doc": "b.txt", "chunk_id": "c3"}

        mock_client.scroll.side_effect = [
            ([p1, p2, p3], None),
        ]

        result = get_unique_source_docs(mock_client, "triplets")
        assert len(result) == 2
        assert result["a.txt"]["triplets_count"] == 2
        assert len(result["a.txt"]["chunk_ids"]) == 2
        assert result["b.txt"]["triplets_count"] == 1

    def test_skips_empty_source(self):
        mock_client = MagicMock()
        p1 = MagicMock()
        p1.id = "id1"
        p1.payload = {"source_doc": ""}

        mock_client.scroll.return_value = ([p1], None)

        result = get_unique_source_docs(mock_client, "triplets")
        assert len(result) == 0


class TestCheckQdrantHealth:
    @patch("app.core.vectorstore.get_qdrant_client")
    def test_healthy(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.get_collections.return_value = MagicMock(collections=[])
        mock_get_client.return_value = mock_client

        result = check_qdrant_health()
        assert result is True

    @patch("app.core.vectorstore.get_qdrant_client")
    def test_unhealthy(self, mock_get_client):
        mock_get_client.side_effect = ConnectionError("fail")

        result = check_qdrant_health()
        assert result is False
