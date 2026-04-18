"""Tests for expand_from_graph (traverse_graph) with mocked NebulaGraph."""

from unittest.mock import MagicMock, patch

from app.pipelines.query import traverse_graph


def _make_go_row(src: bytes, dst: bytes, relation: bytes) -> MagicMock:
    """Build a mock row for a GO query result (src, dst, relation)."""
    row = MagicMock()
    val0 = MagicMock()
    val0.get_sVal.return_value = src
    val1 = MagicMock()
    val1.get_sVal.return_value = dst
    val2 = MagicMock()
    val2.get_sVal.return_value = relation
    row.values = [val0, val1, val2]
    return row


def _make_go_result(rows: list[MagicMock], succeeded: bool = True) -> MagicMock:
    """Build a mock result for a GO query."""
    result = MagicMock()
    result.is_succeeded.return_value = succeeded
    result.rows.return_value = rows
    return result


def _make_vertex_tag(name: str, entity_type: str = "concept") -> MagicMock:
    """Build a mock entity tag with name and type properties."""
    tag = MagicMock()
    tag.name = b"entity"
    name_prop = MagicMock()
    name_prop.get_sVal.return_value = name.encode()
    type_prop = MagicMock()
    type_prop.get_sVal.return_value = entity_type.encode()
    tag.props = {b"name": name_prop, b"type": type_prop}
    return tag


def _make_fetch_row(vid: str, name: str, entity_type: str = "concept") -> MagicMock:
    """Build a mock row for a FETCH PROP result with a vertex."""
    tag = _make_vertex_tag(name, entity_type)
    vertex = MagicMock()
    vertex.vid.get_sVal.return_value = vid.encode()
    vertex.tags = [tag]

    v = MagicMock()
    v.get_vVal.return_value = vertex

    row = MagicMock()
    row.values = [v]
    return row


def _make_fetch_result(rows: list[MagicMock], succeeded: bool = True) -> MagicMock:
    """Build a mock result for a FETCH PROP query."""
    result = MagicMock()
    result.is_succeeded.return_value = succeeded
    result.rows.return_value = rows
    return result


def _mock_session_context(mock_session: MagicMock) -> MagicMock:
    """Configure a mock get_nebula_session return value as context manager."""
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=mock_session)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


class TestExpandFromGraphSingleHop:
    """Test single-hop traversal from entity IDs."""

    @patch("app.pipelines.query.get_nebula_session")
    def test_expand_from_graph_outgoing_edge(self, mock_get_session):
        """Single entity with one outgoing edge returns correct triplet."""
        mock_session = MagicMock()

        # 1. USE graphrag → success
        use_result = _make_go_result([], succeeded=True)

        # 2. GO FROM "Python" OVER related_to (out) → one edge
        out_row = _make_go_row(b"Python", b"Guido_van_Rossum", b"created_by")
        out_result = _make_go_result([out_row])

        # 3. GO FROM "Python" OVER related_to REVERSELY (in) → no results
        in_result = _make_go_result([], succeeded=True)

        # 4. FETCH PROP for "Python" → name "Python"
        fetch_python = _make_fetch_result([_make_fetch_row("Python", "Python")])

        # 5. FETCH PROP for "Guido_van_Rossum" is NOT called directly
        #    (traverse_graph only fetches for the input entity_ids)
        mock_session.execute.side_effect = [use_result, out_result, in_result, fetch_python]

        mock_get_session.return_value = _mock_session_context(mock_session)

        results = traverse_graph(["Python"])

        assert len(results) == 1
        t = results[0]
        assert t["subject_id"] == "Python"
        assert t["object_id"] == "Guido_van_Rossum"
        assert t["predicate"] == "created_by"
        # Name resolution: "Python" entity fetched → subject name updated
        assert t["subject"] == "Python"

    @patch("app.pipelines.query.get_nebula_session")
    def test_expand_from_graph_incoming_edge(self, mock_get_session):
        """Single entity with one incoming edge returns correct triplet."""
        mock_session = MagicMock()

        use_result = _make_go_result([], succeeded=True)

        # Out direction: no edges
        out_result = _make_go_result([], succeeded=True)

        # In direction: one edge pointing TO Python
        in_row = _make_go_row(b"Programming", b"Python", b"includes")
        in_result = _make_go_result([in_row])

        # FETCH PROP for "Python"
        fetch_python = _make_fetch_result([_make_fetch_row("Python", "Python")])

        mock_session.execute.side_effect = [use_result, out_result, in_result, fetch_python]

        mock_get_session.return_value = _mock_session_context(mock_session)

        results = traverse_graph(["Python"])

        assert len(results) == 1
        t = results[0]
        # From reverse traversal, src=Programming, dst=Python
        assert t["subject_id"] == "Programming"
        assert t["object_id"] == "Python"
        assert t["predicate"] == "includes"
        # Name resolution: "Python" object name updated
        assert t["object"] == "Python"

    @patch("app.pipelines.query.get_nebula_session")
    def test_expand_from_graph_both_directions(self, mock_get_session):
        """Entity with both outgoing and incoming edges returns all triplets."""
        mock_session = MagicMock()

        use_result = _make_go_result([], succeeded=True)

        out_row = _make_go_row(b"Python", b"Guido_van_Rossum", b"created_by")
        out_result = _make_go_result([out_row])

        in_row = _make_go_row(b"Programming", b"Python", b"includes")
        in_result = _make_go_result([in_row])

        fetch_python = _make_fetch_result([_make_fetch_row("Python", "Python")])

        mock_session.execute.side_effect = [use_result, out_result, in_result, fetch_python]

        mock_get_session.return_value = _mock_session_context(mock_session)

        results = traverse_graph(["Python"])

        assert len(results) == 2
        predicates = {t["predicate"] for t in results}
        assert predicates == {"created_by", "includes"}


class TestExpandFromGraphEntityNameResolution:
    """Test entity name resolution from vertex properties."""

    @patch("app.pipelines.query.get_nebula_session")
    def test_expand_from_graph_resolves_entity_names(self, mock_get_session):
        """Entity names are resolved from vertex properties, not raw VIDs."""
        mock_session = MagicMock()

        use_result = _make_go_result([], succeeded=True)

        out_row = _make_go_row(b"Machine_Learning", b"Neural_Networks", b"uses")
        out_result = _make_go_result([out_row])

        in_result = _make_go_result([], succeeded=True)

        # FETCH PROP returns a human-readable name for Machine_Learning
        fetch_row = _make_fetch_row("Machine_Learning", "Machine Learning")
        fetch_result = _make_fetch_result([fetch_row])

        mock_session.execute.side_effect = [use_result, out_result, in_result, fetch_result]

        mock_get_session.return_value = _mock_session_context(mock_session)

        results = traverse_graph(["Machine_Learning"])

        assert len(results) == 1
        t = results[0]
        # Before name resolution, subject would be "Machine Learning" (underscore replaced)
        # After name resolution from FETCH PROP, subject should be "Machine Learning"
        assert t["subject"] == "Machine Learning"
        # object_id did not get a FETCH PROP call → falls back to underscore replacement
        assert t["object"] == "Neural Networks"

    @patch("app.pipelines.query.get_nebula_session")
    def test_expand_from_graph_fetch_failure_keeps_underscore_names(self, mock_get_session):
        """When FETCH PROP fails, names fall back to underscore replacement."""
        mock_session = MagicMock()

        use_result = _make_go_result([], succeeded=True)

        out_row = _make_go_row(b"Machine_Learning", b"Neural_Networks", b"uses")
        out_result = _make_go_result([out_row])

        in_result = _make_go_result([], succeeded=True)

        # FETCH PROP fails
        fetch_result = _make_go_result([], succeeded=False)

        mock_session.execute.side_effect = [use_result, out_result, in_result, fetch_result]

        mock_get_session.return_value = _mock_session_context(mock_session)

        results = traverse_graph(["Machine_Learning"])

        assert len(results) == 1
        t = results[0]
        # Fallback: underscores replaced with spaces
        assert t["subject"] == "Machine Learning"
        assert t["object"] == "Neural Networks"


class TestExpandFromGraphEdgeCases:
    """Edge cases for expand_from_graph."""

    def test_expand_from_graph_empty_ids(self):
        """Empty entity_ids returns empty list without touching NebulaGraph."""
        result = traverse_graph([])
        assert result == []

    @patch("app.pipelines.query.get_nebula_session")
    def test_expand_from_graph_deduplicates_edges(self, mock_get_session):
        """Same edge found from both directions is deduplicated."""
        mock_session = MagicMock()

        use_result = _make_go_result([], succeeded=True)

        # Out: Python → Language (is_a)
        out_row = _make_go_row(b"Python", b"Language", b"is_a")
        out_result = _make_go_result([out_row])

        # In: same edge appears again (Language ← Python)
        in_row = _make_go_row(b"Python", b"Language", b"is_a")
        in_result = _make_go_result([in_row])

        fetch_python = _make_fetch_result([_make_fetch_row("Python", "Python")])

        mock_session.execute.side_effect = [use_result, out_result, in_result, fetch_python]

        mock_get_session.return_value = _mock_session_context(mock_session)

        results = traverse_graph(["Python"])

        # Deduplicated: same edge key "Python-is_a-Language"
        assert len(results) == 1
        assert results[0]["predicate"] == "is_a"

    @patch("app.pipelines.query.get_nebula_session")
    def test_expand_from_graph_failed_go_skipped(self, mock_get_session):
        """Failed GO queries are silently skipped."""
        mock_session = MagicMock()

        use_result = _make_go_result([], succeeded=True)

        # Both GO queries fail
        out_result = _make_go_result([], succeeded=False)
        in_result = _make_go_result([], succeeded=False)

        # FETCH PROP also fails
        fetch_result = _make_go_result([], succeeded=False)

        mock_session.execute.side_effect = [use_result, out_result, in_result, fetch_result]

        mock_get_session.return_value = _mock_session_context(mock_session)

        results = traverse_graph(["NonExistent"])

        assert results == []
