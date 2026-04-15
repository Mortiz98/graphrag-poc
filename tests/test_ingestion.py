"""Unit tests for ingestion helpers."""

from app.pipelines.ingestion import _sanitize_vertex_id


class TestSanitizeVertexId:
    def test_simple_string(self):
        assert _sanitize_vertex_id("Python") == "Python"

    def test_spaces_replaced(self):
        assert _sanitize_vertex_id("Guido van Rossum") == "Guido_van_Rossum"

    def test_special_chars_replaced(self):
        assert _sanitize_vertex_id("Qdrant, Inc.") == "Qdrant__Inc"

    def test_empty_string_returns_entity_prefix(self):
        result = _sanitize_vertex_id("")
        assert result.startswith("entity_")

    def test_long_string_truncated(self):
        result = _sanitize_vertex_id("A" * 300)
        assert len(result) <= 256

    def test_unicode_converted(self):
        result = _sanitize_vertex_id("café")
        assert "caf" in result
