"""Tests for fuse_results (a.k.a. _fuse_context) dedup + ordering."""

from app.pipelines.query import _fuse_context


class TestFuseResults:
    """Verify deduplication by (subject, predicate, object) and correct ordering."""

    def test_fuse_results_dedup_identical_triplets(self):
        """Duplicate triple appearing in both vector and graph is kept only once."""
        vector_triplets = [
            {"subject": "Python", "predicate": "is_a", "object": "Language"},
        ]
        graph_triplets = [
            {"subject": "Python", "predicate": "is_a", "object": "Language"},
        ]
        _, fused = _fuse_context(vector_triplets, graph_triplets)
        assert len(fused) == 1

    def test_fuse_results_dedup_multiple_duplicates(self):
        """Multiple duplicates across vector and graph are all deduplicated."""
        vector_triplets = [
            {"subject": "Python", "predicate": "is_a", "object": "Language"},
            {"subject": "Python", "predicate": "created_by", "object": "Guido"},
        ]
        graph_triplets = [
            {"subject": "Python", "predicate": "is_a", "object": "Language"},
            {"subject": "Python", "predicate": "created_by", "object": "Guido"},
            {"subject": "Guido", "predicate": "is_a", "object": "Person"},
        ]
        _, fused = _fuse_context(vector_triplets, graph_triplets)
        assert len(fused) == 3
        keys = [f"{t['subject']}|{t['predicate']}|{t['object']}" for t in fused]
        assert len(set(keys)) == 3  # no duplicate keys

    def test_fuse_results_vector_before_graph_ordering(self):
        """Vector results appear before graph results in the fused output."""
        vector_triplets = [
            {"subject": "V1", "predicate": "pv1", "object": "VV1"},
            {"subject": "V2", "predicate": "pv2", "object": "VV2"},
        ]
        graph_triplets = [
            {"subject": "G1", "predicate": "pg1", "object": "GG1"},
        ]
        _, fused = _fuse_context(vector_triplets, graph_triplets)
        assert len(fused) == 3
        assert fused[0]["subject"] == "V1"
        assert fused[1]["subject"] == "V2"
        assert fused[2]["subject"] == "G1"

    def test_fuse_results_overlapping_dedup_preserves_vector_first(self):
        """When vector and graph share a triple, the vector version is kept."""
        vector_triplets = [
            {"subject": "X", "predicate": "rel", "object": "Y", "score": 0.9},
        ]
        graph_triplets = [
            {"subject": "X", "predicate": "rel", "object": "Y"},
        ]
        _, fused = _fuse_context(vector_triplets, graph_triplets)
        assert len(fused) == 1
        assert fused[0].get("score") == 0.9  # vector version preserved

    def test_fuse_results_empty_inputs(self):
        """Empty both lists returns empty context and empty fused list."""
        context, fused = _fuse_context([], [])
        assert context == ""
        assert fused == []

    def test_fuse_results_empty_vector_only(self):
        """Empty vector with non-empty graph still produces results."""
        graph_triplets = [
            {"subject": "G", "predicate": "pg", "object": "GG"},
        ]
        context, fused = _fuse_context([], graph_triplets)
        assert len(fused) == 1
        assert "G pg GG" in context

    def test_fuse_results_empty_graph_only(self):
        """Empty graph with non-empty vector still produces results."""
        vector_triplets = [
            {"subject": "V", "predicate": "pv", "object": "VV"},
        ]
        context, fused = _fuse_context(vector_triplets, [])
        assert len(fused) == 1
        assert "V pv VV" in context

    def test_fuse_results_context_format(self):
        """Context string uses dash-prefixed 'subject predicate object' lines."""
        triplets = [
            {"subject": "A", "predicate": "b", "object": "C"},
            {"subject": "D", "predicate": "e", "object": "F"},
        ]
        context, fused = _fuse_context(triplets, [])
        assert context == "- A b C\n- D e F"
