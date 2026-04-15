"""Unit tests for query pipeline helpers."""

from app.pipelines.query import _fuse_context


class TestFuseContext:
    def test_deduplication(self):
        vector_triplets = [
            {"subject": "Python", "predicate": "is_a", "object": "Language"},
        ]
        graph_triplets = [
            {"subject": "Python", "predicate": "is_a", "object": "Language"},
        ]
        context, fused = _fuse_context(vector_triplets, graph_triplets)
        assert len(fused) == 1

    def test_different_triplets_combined(self):
        vector_triplets = [
            {"subject": "Python", "predicate": "created_by", "object": "Guido"},
        ]
        graph_triplets = [
            {"subject": "Python", "predicate": "is_a", "object": "Language"},
        ]
        context, fused = _fuse_context(vector_triplets, graph_triplets)
        assert len(fused) == 2
        assert "Python created_by Guido" in context
        assert "Python is_a Language" in context

    def test_empty_inputs(self):
        context, fused = _fuse_context([], [])
        assert context == ""
        assert len(fused) == 0

    def test_context_format(self):
        triplets = [
            {"subject": "A", "predicate": "b", "object": "C"},
            {"subject": "D", "predicate": "e", "object": "F"},
        ]
        context, fused = _fuse_context(triplets, [])
        assert "- A b C" in context
        assert "- D e F" in context
