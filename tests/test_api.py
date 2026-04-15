"""Integration tests for API endpoints using FastAPI TestClient."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app, raise_server_exceptions=True)


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("healthy", "degraded")
        assert "services" in data
        assert "qdrant" in data["services"]
        assert "nebulagraph" in data["services"]

    def test_health_has_config(self, client):
        response = client.get("/api/v1/health")
        data = response.json()
        assert "config" in data
        assert "llm_model" in data["config"]


class TestIngestEndpoint:
    def test_ingest_txt_file(self, client):
        with open("test_data/sample.txt", "rb") as f:
            response = client.post(
                "/api/v1/ingest",
                files={"file": ("sample.txt", f, "text/plain")},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "sample.txt"
        assert data["triplets_count"] > 0
        assert data["status"] == "processed"

    def test_ingest_unsupported_file_type(self, client):
        response = client.post(
            "/api/v1/ingest",
            files={"file": ("test.csv", b"a,b,c", "text/csv")},
        )
        assert response.status_code == 400
        assert "Unsupported file type" in response.json()["detail"]


class TestQueryEndpoint:
    def test_query_returns_answer(self, client):
        response = client.post(
            "/api/v1/query",
            json={"question": "What is Python?", "top_k": 3},
        )
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "entities_found" in data
        assert "confidence" in data
        assert isinstance(data["sources"], list)

    def test_query_empty_question_fails(self, client):
        response = client.post(
            "/api/v1/query",
            json={"question": "", "top_k": 5},
        )
        assert response.status_code == 422


class TestDocumentsEndpoint:
    def test_list_documents(self, client):
        response = client.get("/api/v1/documents")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_graph_stats(self, client):
        response = client.get("/api/v1/graph/stats")
        assert response.status_code == 200
        data = response.json()
        assert "entity_count" in data
        assert "edge_count" in data
        assert data["space"] == "graphrag"


class TestSwaggerDocs:
    def test_docs_page(self, client):
        response = client.get("/docs")
        assert response.status_code == 200

    def test_openapi_spec(self, client):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        spec = response.json()
        assert "paths" in spec
        assert "/api/v1/ingest" in spec["paths"]
        assert "/api/v1/query" in spec["paths"]
        assert "/api/v1/health" in spec["paths"]
