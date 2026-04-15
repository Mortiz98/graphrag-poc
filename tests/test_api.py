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

    def test_health_reports_llm_status(self, client):
        response = client.get("/api/v1/health")
        data = response.json()
        assert data["services"]["llm"] in ("configured", "not_configured")


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
        assert data["chunks_count"] > 0

    def test_ingest_unsupported_file_type(self, client):
        response = client.post(
            "/api/v1/ingest",
            files={"file": ("test.csv", b"a,b,c", "text/csv")},
        )
        assert response.status_code == 400
        assert "Unsupported file type" in response.json()["detail"]

    def test_ingest_no_filename(self, client):
        response = client.post(
            "/api/v1/ingest",
            files={"file": ("", b"content", "text/plain")},
        )
        assert response.status_code == 400

    def test_ingest_md_file(self, client):
        content = b"# Test\n\nMarkdown **content** about Python."
        response = client.post(
            "/api/v1/ingest",
            files={"file": ("test.md", content, "text/markdown")},
        )
        assert response.status_code == 200
        assert response.json()["filename"] == "test.md"


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

    def test_query_default_top_k(self, client):
        response = client.post(
            "/api/v1/query",
            json={"question": "What is Django?"},
        )
        assert response.status_code == 200

    def test_query_top_k_bounds(self, client):
        response = client.post(
            "/api/v1/query",
            json={"question": "test", "top_k": 0},
        )
        assert response.status_code == 422

        response = client.post(
            "/api/v1/query",
            json={"question": "test", "top_k": 21},
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

    def test_delete_nonexistent_document(self, client):
        response = client.delete("/api/v1/documents/nonexistent_file_12345.txt")
        assert response.status_code == 404

    def test_delete_and_list_roundtrip(self, client):
        content = b"FastAPI is a framework by Sebastian Ramirez."
        ingest_resp = client.post(
            "/api/v1/ingest",
            files={"file": ("delete_test.txt", content, "text/plain")},
        )
        assert ingest_resp.status_code == 200

        docs_before = client.get("/api/v1/documents").json()
        filenames = [d["filename"] for d in docs_before]
        assert "delete_test.txt" in filenames

        delete_resp = client.delete("/api/v1/documents/delete_test.txt")
        assert delete_resp.status_code == 200
        assert delete_resp.json()["status"] == "deleted"
        assert delete_resp.json()["vectors_deleted"] > 0

        docs_after = client.get("/api/v1/documents").json()
        filenames_after = [d["filename"] for d in docs_after]
        assert "delete_test.txt" not in filenames_after


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
        assert "/api/v1/documents" in spec["paths"]
        assert "/api/v1/documents/{filename}" in spec["paths"]
        assert "/api/v1/graph/stats" in spec["paths"]
