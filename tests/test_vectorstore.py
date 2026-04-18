"""Unit tests for vectorstore module."""

from unittest.mock import MagicMock, PropertyMock, patch

from app.core.vectorstore import (
    _collection_has_sparse_vectors,
    _create_collection_with_sparse,
    _migrate_collection_to_sparse,
    check_qdrant_health,
    ensure_collection_exists,
    get_unique_source_docs,
    scroll_by_source_doc,
)


def _mock_collection_info_with_sparse():
    """Return a mock collection info that has sparse vectors configured."""
    mock_info = MagicMock()
    sparse_vectors = MagicMock()
    sparse_vectors.__len__ = MagicMock(return_value=1)
    type(mock_info.config.params).sparse_vectors = PropertyMock(return_value=sparse_vectors)
    return mock_info


def _mock_collection_info_without_sparse():
    """Return a mock collection info that has no sparse vectors."""
    mock_info = MagicMock()
    type(mock_info.config.params).sparse_vectors = PropertyMock(return_value=None)
    return mock_info


class TestCollectionHasSparseVectors:
    def test_returns_true_when_sparse_configured(self):
        mock_client = MagicMock()
        mock_client.get_collection.return_value = _mock_collection_info_with_sparse()
        assert _collection_has_sparse_vectors(mock_client, "test_coll") is True

    def test_returns_false_when_no_sparse(self):
        mock_client = MagicMock()
        mock_client.get_collection.return_value = _mock_collection_info_without_sparse()
        assert _collection_has_sparse_vectors(mock_client, "test_coll") is False

    def test_returns_false_when_empty_sparse_dict(self):
        mock_client = MagicMock()
        mock_info = MagicMock()
        sparse_vectors = MagicMock()
        sparse_vectors.__len__ = MagicMock(return_value=0)
        type(mock_info.config.params).sparse_vectors = PropertyMock(return_value=sparse_vectors)
        mock_client.get_collection.return_value = mock_info
        assert _collection_has_sparse_vectors(mock_client, "test_coll") is False

    def test_returns_false_on_exception(self):
        mock_client = MagicMock()
        mock_client.get_collection.side_effect = Exception("fail")
        assert _collection_has_sparse_vectors(mock_client, "test_coll") is False


class TestCreateCollectionWithSparse:
    def test_creates_with_dense_and_sparse(self):
        mock_client = MagicMock()
        _create_collection_with_sparse(mock_client, "test_coll", 1536)
        mock_client.create_collection.assert_called_once()
        call_kwargs = mock_client.create_collection.call_args[1]
        assert call_kwargs["collection_name"] == "test_coll"
        assert "dense" in call_kwargs["vectors_config"]
        assert "sparse" in call_kwargs["sparse_vectors_config"]


class TestMigrateCollectionToSparse:
    def test_deletes_and_recreates(self):
        mock_client = MagicMock()
        _migrate_collection_to_sparse(mock_client, "test_coll", 1536)
        mock_client.delete_collection.assert_called_once_with("test_coll")
        mock_client.create_collection.assert_called_once()


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
    def test_skips_if_exists_with_sparse(self, mock_indexes):
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.name = "triplets"
        mock_client.get_collections.return_value = MagicMock(collections=[mock_collection])
        mock_client.get_collection.return_value = _mock_collection_info_with_sparse()

        ensure_collection_exists(mock_client, "triplets")

        mock_client.create_collection.assert_not_called()
        mock_client.delete_collection.assert_not_called()

    @patch("app.core.vectorstore._ensure_payload_indexes")
    def test_migrates_if_exists_without_sparse(self, mock_indexes):
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.name = "triplets"
        mock_client.get_collections.return_value = MagicMock(collections=[mock_collection])
        mock_client.get_collection.return_value = _mock_collection_info_without_sparse()

        ensure_collection_exists(mock_client, "triplets")

        mock_client.delete_collection.assert_called_once_with("triplets")
        mock_client.create_collection.assert_called_once()


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
    async def test_healthy(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.get_collections.return_value = MagicMock(collections=[])
        mock_get_client.return_value = mock_client

        result = await check_qdrant_health()
        assert result is True

    @patch("app.core.vectorstore.get_qdrant_client")
    async def test_unhealthy(self, mock_get_client):
        mock_get_client.side_effect = ConnectionError("fail")

        result = await check_qdrant_health()
        assert result is False
