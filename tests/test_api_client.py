"""Unit tests for the Streamlit API client."""

from unittest.mock import MagicMock, patch

from ui.components.api_client import (
    DEFAULT_BASE_URL,
    AgentQueryResult,
    ApiClient,
    DocumentInfo,
    GraphStats,
    HealthStatus,
    IngestResult,
)


class TestApiClientInit:
    def test_default_base_url(self):
        client = ApiClient()
        assert client.base_url == DEFAULT_BASE_URL

    def test_custom_base_url(self):
        client = ApiClient(base_url="http://custom:9000/api/v1/")
        assert client.base_url == "http://custom:9000/api/v1"

    def test_default_timeout(self):
        client = ApiClient()
        assert client.timeout == 120.0

    def test_custom_timeout(self):
        client = ApiClient(timeout=30.0)
        assert client.timeout == 30.0


class TestHealth:
    @patch("ui.components.api_client.httpx.Client")
    def test_healthy(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "healthy",
            "services": {"qdrant": "ok", "nebulagraph": "ok", "llm": "configured"},
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        client = ApiClient()
        health = client.health()

        assert isinstance(health, HealthStatus)
        assert health.status == "healthy"
        assert health.qdrant == "ok"
        assert health.nebulagraph == "ok"
        assert health.llm == "configured"

    @patch("ui.components.api_client.httpx.Client")
    def test_degraded(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "degraded",
            "services": {"qdrant": "unavailable", "nebulagraph": "ok", "llm": "not_configured"},
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        client = ApiClient()
        health = client.health()
        assert health.status == "degraded"
        assert health.qdrant == "unavailable"


class TestIngest:
    @patch("ui.components.api_client.httpx.Client")
    def test_successful_ingest(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "filename": "test.txt",
            "chunks_count": 5,
            "triplets_count": 12,
            "status": "processed",
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        client = ApiClient()
        result = client.ingest("test.txt", b"content")

        assert isinstance(result, IngestResult)
        assert result.filename == "test.txt"
        assert result.chunks_count == 5
        assert result.triplets_count == 12
        assert result.status == "processed"
        mock_client.post.assert_called_once()


class TestAgentQuery:
    @patch("ui.components.api_client.httpx.Client")
    def test_successful_support_query(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "answer": "Python is a programming language.",
            "session_id": "sess_123",
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        client = ApiClient()
        result = client.agent_query("What is Python?", agent="support")

        assert isinstance(result, AgentQueryResult)
        assert result.answer == "Python is a programming language."
        assert result.session_id == "sess_123"

    @patch("ui.components.api_client.httpx.Client")
    def test_am_query_with_account_id(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "answer": "The account has 3 open commitments.",
            "session_id": "sess_456",
            "account_id": "acme_corp",
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        client = ApiClient()
        result = client.agent_query("Status?", agent="am", account_id="acme_corp")

        assert isinstance(result, AgentQueryResult)
        assert result.session_id == "sess_456"


class TestListDocuments:
    @patch("ui.components.api_client.httpx.Client")
    def test_returns_documents(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"id": "id1", "filename": "a.txt", "chunks_count": 3, "triplets_count": 10},
            {"id": "id2", "filename": "b.pdf", "chunks_count": 5, "triplets_count": 20},
        ]
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        client = ApiClient()
        docs = client.list_documents()

        assert len(docs) == 2
        assert all(isinstance(d, DocumentInfo) for d in docs)
        assert docs[0].filename == "a.txt"
        assert docs[1].triplets_count == 20

    @patch("ui.components.api_client.httpx.Client")
    def test_empty_list(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        client = ApiClient()
        docs = client.list_documents()
        assert docs == []


class TestDeleteDocument:
    @patch("ui.components.api_client.httpx.Client")
    def test_successful_delete(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "filename": "test.txt",
            "vectors_deleted": 10,
            "entities_deleted_from_graph": 5,
            "status": "deleted",
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.delete.return_value = mock_response
        mock_client_cls.return_value = mock_client

        client = ApiClient()
        result = client.delete_document("test.txt")

        assert result["status"] == "deleted"
        assert result["vectors_deleted"] == 10


class TestGraphStats:
    @patch("ui.components.api_client.httpx.Client")
    def test_returns_stats(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "entity_count": 42,
            "edge_count": 87,
            "space": "graphrag",
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        client = ApiClient()
        stats = client.graph_stats()

        assert isinstance(stats, GraphStats)
        assert stats.entity_count == 42
        assert stats.edge_count == 87


class TestGraphEdges:
    @patch("ui.components.api_client.httpx.Client")
    def test_returns_graph_data(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "nodes": [{"id": "Python", "label": "Python", "type": "Technology", "degree": 3}],
            "edges": [{"source": "Python", "target": "Language", "relation": "is_a"}],
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        client = ApiClient()
        data = client.graph_edges()

        assert len(data.nodes) == 1
        assert len(data.edges) == 1
        assert data.edges[0]["relation"] == "is_a"


class TestGraphEntities:
    @patch("ui.components.api_client.httpx.Client")
    def test_returns_entities(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"id": "Python", "name": "Python", "type": "Technology", "degree": 3},
        ]
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        client = ApiClient()
        entities = client.graph_entities()
        assert len(entities) == 1


class TestGraphSubgraph:
    @patch("ui.components.api_client.httpx.Client")
    def test_returns_subgraph(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "nodes": [{"id": "Python"}],
            "edges": [{"source": "Python", "target": "Language", "relation": "is_a"}],
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        client = ApiClient()
        data = client.graph_subgraph("Python", hops=2)

        call_args = mock_client.get.call_args
        assert call_args[1]["params"]["entity"] == "Python"
        assert call_args[1]["params"]["hops"] == 2
        assert len(data.nodes) == 1


class TestGraphFilters:
    @patch("ui.components.api_client.httpx.Client")
    def test_returns_filters(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "entity_types": ["Technology", "Person"],
            "relation_types": ["is_a", "developed_by"],
            "source_docs": ["test.txt"],
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        client = ApiClient()
        filters = client.graph_filters()
        assert filters.entity_types == ["Technology", "Person"]
        assert filters.relation_types == ["is_a", "developed_by"]
        assert filters.source_docs == ["test.txt"]


class TestSeed:
    @patch("ui.components.api_client.httpx.Client")
    def test_successful_seed(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "filename": "sample.txt",
            "chunks_count": 3,
            "triplets_count": 15,
            "status": "processed",
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        client = ApiClient()
        result = client.seed()

        assert isinstance(result, IngestResult)
        assert result.filename == "sample.txt"
        assert result.triplets_count == 15
        mock_client.post.assert_called_once_with("/seed")
