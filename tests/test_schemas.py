"""Unit tests for Pydantic schemas."""

from uuid import UUID

import pytest

from app.models.graph_schema import escape_ngql
from app.models.schemas import (
    CaseMetadata,
    FactMetadata,
    IngestRequest,
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


class TestEscapeNgql:
    def test_plain_string_unchanged(self):
        assert escape_ngql("Python") == "Python"

    def test_double_quotes_escaped(self):
        assert escape_ngql('He said "hello"') == 'He said \\"hello\\"'

    def test_single_quotes_escaped(self):
        assert escape_ngql("it's") == "it\\'s"

    def test_backslash_escaped(self):
        assert escape_ngql("path\\to\\file") == "path\\\\to\\\\file"

    def test_newline_escaped(self):
        assert escape_ngql("line1\nline2") == "line1\\nline2"

    def test_carriage_return_escaped(self):
        assert escape_ngql("line1\rline2") == "line1\\rline2"

    def test_tab_escaped(self):
        assert escape_ngql("col1\tcol2") == "col1\\tcol2"

    def test_combined_special_chars(self):
        result = escape_ngql('He said "it\'s"\n\\done')
        assert result == 'He said \\"it\\\'s\\"\\n\\\\done'

    def test_empty_string(self):
        assert escape_ngql("") == ""

    def test_injection_attempt(self):
        malicious = '"; DROP VERTEX *; --'
        result = escape_ngql(malicious)
        assert result == '\\"; DROP VERTEX *; --'

    def test_backslash_double_quote_injection(self):
        malicious = '\\"; DROP VERTEX *; --'
        result = escape_ngql(malicious)
        assert result == '\\\\\\"; DROP VERTEX *; --'


class TestCaseMetadata:
    def test_all_none_defaults(self):
        m = CaseMetadata()
        assert m.case_id is None
        assert m.product is None

    def test_with_values(self):
        m = CaseMetadata(case_id="CASE-1", product="API", severity="high")
        assert m.case_id == "CASE-1"
        assert m.severity == "high"

    def test_serialization_excludes_none(self):
        m = CaseMetadata(case_id="CASE-1")
        d = m.model_dump(exclude_none=True)
        assert "case_id" in d
        assert "product" not in d


class TestFactMetadata:
    def test_all_none_defaults(self):
        m = FactMetadata()
        assert m.account_id is None
        assert m.fact_type is None

    def test_with_values(self):
        m = FactMetadata(account_id="ACC-1", fact_type="episode", confidence=0.9)
        assert m.account_id == "ACC-1"
        assert m.confidence == 0.9

    def test_serialization_excludes_none(self):
        m = FactMetadata(account_id="ACC-1")
        d = m.model_dump(exclude_none=True)
        assert "account_id" in d
        assert "fact_type" not in d


class TestIngestRequest:
    def test_defaults(self):
        req = IngestRequest(filename="test.txt")
        assert req.system == "support"
        assert req.case_metadata is None
        assert req.fact_metadata is None

    def test_with_system_am(self):
        req = IngestRequest(filename="notes.txt", system="am")
        assert req.system == "am"

    def test_with_case_metadata(self):
        req = IngestRequest(
            filename="ticket.txt",
            system="support",
            case_metadata=CaseMetadata(case_id="C-1", product="API"),
        )
        assert req.case_metadata.case_id == "C-1"

    def test_with_fact_metadata(self):
        req = IngestRequest(
            filename="meeting.txt",
            system="am",
            fact_metadata=FactMetadata(account_id="ACC-1", fact_type="episode"),
        )
        assert req.fact_metadata.account_id == "ACC-1"


class TestQueryRequestExtended:
    def test_scope_field(self):
        req = QueryRequest(question="test", scope={"system": "support"})
        assert req.scope == {"system": "support"}

    def test_account_id_field(self):
        req = QueryRequest(question="test", account_id="ACC-1")
        assert req.account_id == "ACC-1"

    def test_both_scope_and_account(self):
        req = QueryRequest(
            question="test",
            scope={"system": "am"},
            account_id="ACC-1",
        )
        assert req.scope["system"] == "am"
        assert req.account_id == "ACC-1"
