"""Tests for consolidation pipeline — real logic, Qdrant mocked."""

from datetime import datetime, timezone

from app.pipelines.consolidation import Fact, apply_supersession


class TestApplySupersession:
    """Exercise apply_supersession() with real consolidation logic.

    Only the Qdrant client would need mocking for persist_facts(); the
    supersession logic itself is exercised directly.
    """

    def test_old_fact_marked_superseded(self):
        old = Fact(subject="Python", predicate="is_a", object="Language")
        new = Fact(subject="Python", predicate="is_a", object="Programming Language")

        now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        old_updated, new_updated = apply_supersession(old, new, now=now)

        # Old fact: retired
        assert old_updated.valid_to == now
        assert old_updated.is_active is False
        assert old_updated.superseded_by == new.id

    def test_new_fact_activated(self):
        old = Fact(subject="Python", predicate="is_a", object="Language")
        new = Fact(subject="Python", predicate="is_a", object="Programming Language")

        now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        old_updated, new_updated = apply_supersession(old, new, now=now)

        # New fact: active
        assert new_updated.valid_from == now
        assert new_updated.is_active is True

    def test_superseded_by_references_new_fact_id(self):
        old = Fact(subject="X", predicate="rel", object="Y")
        new = Fact(subject="X", predicate="rel", object="Z")
        new_id = new.id

        old_updated, _ = apply_supersession(old, new)

        assert old_updated.superseded_by == new_id

    def test_timestamps_default_to_utc_now(self):
        old = Fact(subject="A", predicate="b", object="C")
        new = Fact(subject="A", predicate="b", object="D")

        before = datetime.now(timezone.utc)
        old_updated, new_updated = apply_supersession(old, new)
        after = datetime.now(timezone.utc)

        assert before <= old_updated.valid_to <= after
        assert before <= new_updated.valid_from <= after

    def test_same_timestamp_on_both_facts(self):
        old = Fact(subject="A", predicate="b", object="C")
        new = Fact(subject="A", predicate="b", object="D")

        now = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
        old_updated, new_updated = apply_supersession(old, new, now=now)

        # Both facts share the same transition timestamp
        assert old_updated.valid_to == new_updated.valid_from

    def test_preserves_other_fact_fields(self):
        old = Fact(
            subject="Python",
            predicate="is_a",
            object="Language",
            source_doc="doc1.txt",
            chunk_id="chunk-abc",
        )
        new = Fact(
            subject="Python",
            predicate="is_a",
            object="Programming Language",
            source_doc="doc2.txt",
            chunk_id="chunk-def",
        )

        old_updated, new_updated = apply_supersession(old, new)

        # Non-temporal fields are preserved
        assert old_updated.subject == "Python"
        assert old_updated.source_doc == "doc1.txt"
        assert old_updated.chunk_id == "chunk-abc"
        assert new_updated.object == "Programming Language"
        assert new_updated.source_doc == "doc2.txt"
