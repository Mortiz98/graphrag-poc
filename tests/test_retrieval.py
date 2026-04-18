"""Unit tests for retrieval module — search_by_filter."""

from unittest.mock import MagicMock

from app.core.retrieval import search_by_filter


def _make_point(point_id, payload):
    p = MagicMock()
    p.id = point_id
    p.payload = payload
    return p


class TestSearchByFilterSingleFilter:
    """Test search_by_filter with a single filter condition."""

    def test_filter_by_system(self):
        """Filter by 'system' (maps to source_doc)."""
        mock_client = MagicMock()
        p1 = _make_point("id1", {"source_doc": "report.txt", "subject": "A", "predicate": "is_a", "object": "B"})

        mock_client.scroll.side_effect = [([p1], None)]

        results = search_by_filter(mock_client, "triplets", {"system": "report.txt"})
        assert len(results) == 1
        assert results[0]["payload"]["source_doc"] == "report.txt"
        # Verify the filter was built with the mapped field name
        scroll_call = mock_client.scroll.call_args
        scroll_filter = scroll_call.kwargs["scroll_filter"]
        assert scroll_filter.must[0].key == "source_doc"
        assert scroll_filter.must[0].match.value == "report.txt"

    def test_filter_by_account_id(self):
        """Filter by 'account_id' (maps to subject_id)."""
        mock_client = MagicMock()
        p1 = _make_point("id1", {"subject_id": "acc_123", "subject": "Acme", "predicate": "owns", "object": "Widget"})

        mock_client.scroll.side_effect = [([p1], None)]

        results = search_by_filter(mock_client, "triplets", {"account_id": "acc_123"})
        assert len(results) == 1
        assert results[0]["payload"]["subject_id"] == "acc_123"
        scroll_call = mock_client.scroll.call_args
        scroll_filter = scroll_call.kwargs["scroll_filter"]
        assert scroll_filter.must[0].key == "subject_id"

    def test_filter_by_fact_type(self):
        """Filter by 'fact_type' (maps to predicate)."""
        mock_client = MagicMock()
        p1 = _make_point("id1", {"predicate": "acquired", "subject": "A", "object": "B"})

        mock_client.scroll.side_effect = [([p1], None)]

        results = search_by_filter(mock_client, "triplets", {"fact_type": "acquired"})
        assert len(results) == 1
        assert results[0]["payload"]["predicate"] == "acquired"
        scroll_call = mock_client.scroll.call_args
        scroll_filter = scroll_call.kwargs["scroll_filter"]
        assert scroll_filter.must[0].key == "predicate"

    def test_filter_by_raw_field_name(self):
        """Filter by a raw Qdrant payload field name (not a domain alias)."""
        mock_client = MagicMock()
        p1 = _make_point("id1", {"chunk_id": "c1", "subject": "A", "predicate": "is_a", "object": "B"})

        mock_client.scroll.side_effect = [([p1], None)]

        results = search_by_filter(mock_client, "triplets", {"chunk_id": "c1"})
        assert len(results) == 1
        assert results[0]["payload"]["chunk_id"] == "c1"
        scroll_call = mock_client.scroll.call_args
        scroll_filter = scroll_call.kwargs["scroll_filter"]
        assert scroll_filter.must[0].key == "chunk_id"

    def test_single_filter_no_results(self):
        """Single filter that matches nothing returns empty list."""
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)

        results = search_by_filter(mock_client, "triplets", {"system": "nonexistent.txt"})
        assert results == []


class TestSearchByFilterMultiFilter:
    """Test search_by_filter with combined (multiple) filter conditions."""

    def test_combined_system_and_fact_type(self):
        """Combine 'system' and 'fact_type' filters."""
        mock_client = MagicMock()
        p1 = _make_point(
            "id1",
            {"source_doc": "report.txt", "predicate": "acquired", "subject": "A", "object": "B"},
        )
        p2 = _make_point(
            "id2",
            {"source_doc": "report.txt", "predicate": "founded", "subject": "C", "object": "D"},
        )

        mock_client.scroll.side_effect = [([p1, p2], None)]

        results = search_by_filter(mock_client, "triplets", {"system": "report.txt", "fact_type": "acquired"})
        # Both points returned by scroll; the filter is pushed to Qdrant
        assert len(results) == 2
        scroll_call = mock_client.scroll.call_args
        scroll_filter = scroll_call.kwargs["scroll_filter"]
        must_keys = {c.key for c in scroll_filter.must}
        assert "source_doc" in must_keys
        assert "predicate" in must_keys

    def test_combined_account_id_and_system(self):
        """Combine 'account_id' and 'system' filters."""
        mock_client = MagicMock()
        p1 = _make_point(
            "id1",
            {"subject_id": "acc_123", "source_doc": "finance.txt", "subject": "A", "predicate": "is_a", "object": "B"},
        )

        mock_client.scroll.side_effect = [([p1], None)]

        results = search_by_filter(mock_client, "triplets", {"account_id": "acc_123", "system": "finance.txt"})
        assert len(results) == 1
        scroll_call = mock_client.scroll.call_args
        scroll_filter = scroll_call.kwargs["scroll_filter"]
        must_keys = {c.key for c in scroll_filter.must}
        assert "subject_id" in must_keys
        assert "source_doc" in must_keys

    def test_combined_three_filters(self):
        """Combine three filter conditions."""
        mock_client = MagicMock()
        p1 = _make_point(
            "id1",
            {"source_doc": "r.txt", "subject_id": "s1", "predicate": "is_a", "subject": "A", "object": "B"},
        )

        mock_client.scroll.side_effect = [([p1], None)]

        results = search_by_filter(
            mock_client,
            "triplets",
            {"system": "r.txt", "account_id": "s1", "fact_type": "is_a"},
        )
        assert len(results) == 1
        scroll_call = mock_client.scroll.call_args
        scroll_filter = scroll_call.kwargs["scroll_filter"]
        assert len(scroll_filter.must) == 3


class TestSearchByFilterActiveOnly:
    """Test active_only behavior for superseded point exclusion."""

    def test_active_only_true_excludes_superseded(self):
        """active_only=True adds must_not condition for status=superseded."""
        mock_client = MagicMock()
        p_active = _make_point(
            "id1",
            {"source_doc": "r.txt", "subject": "A", "predicate": "is_a", "object": "B"},
        )
        mock_client.scroll.side_effect = [([p_active], None)]

        results = search_by_filter(mock_client, "triplets", {"system": "r.txt"}, active_only=True)
        assert len(results) == 1
        scroll_call = mock_client.scroll.call_args
        scroll_filter = scroll_call.kwargs["scroll_filter"]
        assert len(scroll_filter.must_not) == 1
        assert scroll_filter.must_not[0].key == "status"
        assert scroll_filter.must_not[0].match.value == "superseded"

    def test_active_only_false_includes_all(self):
        """active_only=False does NOT add must_not for status=superseded."""
        mock_client = MagicMock()
        p_active = _make_point(
            "id1",
            {"source_doc": "r.txt", "subject": "A", "predicate": "is_a", "object": "B"},
        )
        p_superseded = _make_point(
            "id2",
            {"source_doc": "r.txt", "subject": "A", "predicate": "is_a", "object": "B", "status": "superseded"},
        )
        mock_client.scroll.side_effect = [([p_active, p_superseded], None)]

        results = search_by_filter(mock_client, "triplets", {"system": "r.txt"}, active_only=False)
        # Qdrant returns both; no client-side filtering
        assert len(results) == 2
        scroll_call = mock_client.scroll.call_args
        scroll_filter = scroll_call.kwargs["scroll_filter"]
        assert len(scroll_filter.must_not) == 0

    def test_active_only_default_is_true(self):
        """Default value of active_only is True."""
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)

        search_by_filter(mock_client, "triplets", {"system": "r.txt"})
        scroll_call = mock_client.scroll.call_args
        scroll_filter = scroll_call.kwargs["scroll_filter"]
        assert len(scroll_filter.must_not) == 1
        assert scroll_filter.must_not[0].key == "status"

    def test_active_only_with_no_filters(self):
        """active_only works even when no filter conditions are specified."""
        mock_client = MagicMock()
        p1 = _make_point("id1", {"subject": "A", "predicate": "is_a", "object": "B"})
        mock_client.scroll.side_effect = [([p1], None)]

        results = search_by_filter(mock_client, "triplets", {}, active_only=True)
        assert len(results) == 1
        scroll_call = mock_client.scroll.call_args
        scroll_filter = scroll_call.kwargs["scroll_filter"]
        assert len(scroll_filter.must) == 0
        assert len(scroll_filter.must_not) == 1


class TestSearchByFilterPagination:
    """Test that scroll pagination works correctly."""

    def test_paginated_results(self):
        """Multiple scroll pages are concatenated."""
        mock_client = MagicMock()
        p1 = _make_point("id1", {"source_doc": "r.txt"})
        p2 = _make_point("id2", {"source_doc": "r.txt"})
        p3 = _make_point("id3", {"source_doc": "r.txt"})

        mock_client.scroll.side_effect = [
            ([p1, p2], "offset1"),
            ([p3], None),
        ]

        results = search_by_filter(mock_client, "triplets", {"system": "r.txt"})
        assert len(results) == 3

    def test_empty_collection(self):
        """Empty collection returns empty list."""
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)

        results = search_by_filter(mock_client, "triplets", {"system": "r.txt"})
        assert results == []
