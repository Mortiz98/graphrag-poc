"""Unit tests for Pydantic schemas."""

from uuid import UUID

import pytest

from app.models.schemas import (
    IngestResponse,
    QueryRequest,
    QueryResponse,
    SourceInfo,
    SourceTriplet,
    Triplet,
)


class TestTriplet:
    def test_valid_triplet(self):
        t = Triplet(
            subject="Python",
            subject_type="Technology",
            predicate="created_by",
            object="Guido van Rossum",
            object_type="Person",
        )
        assert t.subject == "Python"
        assert t.object == "Guido van Rossum"

    def test_default_types(self):
        t = Triplet(subject="Python", predicate="is_a", object="Language")
        assert t.subject_type == "entity"
        assert t.object_type == "entity"

    def test_from_dict_with_object_key(self):
        data = {
            "subject": "Python",
            "subject_type": "Technology",
            "predicate": "created_by",
            "object": "Guido van Rossum",
            "object_type": "Person",
        }
        t = Triplet(**data)
        assert t.subject == "Python"
        assert t.object == "Guido van Rossum"

    def test_missing_required_field(self):
        with pytest.raises(Exception):
            Triplet(subject="Python", predicate="is_a")


class TestQueryRequest:
    def test_valid_request(self):
        req = QueryRequest(question="What is Python?")
        assert req.question == "What is Python?"
        assert req.top_k == 5

    def test_custom_top_k(self):
        req = QueryRequest(question="What is Python?", top_k=10)
        assert req.top_k == 10

    def test_top_k_bounds(self):
        with pytest.raises(Exception):
            QueryRequest(question="test", top_k=0)
        with pytest.raises(Exception):
            QueryRequest(question="test", top_k=21)

    def test_empty_question(self):
        with pytest.raises(Exception):
            QueryRequest(question="")


class TestIngestResponse:
    def test_defaults(self):
        resp = IngestResponse(filename="test.txt", chunks_count=3, triplets_count=10)
        assert resp.status == "processed"
        assert isinstance(resp.document_id, UUID)


class TestQueryResponse:
    def test_defaults(self):
        resp = QueryResponse(answer="Python is a language")
        assert resp.sources == []
        assert resp.entities_found == []
        assert resp.confidence == 0.0

    def test_with_sources(self):
        resp = QueryResponse(
            answer="test",
            sources=[
                SourceInfo(
                    chunk_id="abc",
                    document="test.txt",
                    triplets=[SourceTriplet(subject="A", predicate="b", object="C")],
                )
            ],
            entities_found=["A", "C"],
            confidence=0.85,
        )
        assert len(resp.sources) == 1
        assert resp.confidence == 0.85
