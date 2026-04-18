"""Tests for app.core.account_store — load_account_state and format_account_state."""

from unittest.mock import MagicMock

from app.core.account_store import (
    AccountState,
    Fact,
    _is_stakeholder,
    _predicate_matches,
    classify_fact,
    format_account_state,
    load_account_state,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_point(subject: str, predicate: str, object: str, **extra) -> MagicMock:
    """Create a mock Qdrant point with the given payload fields."""
    payload = {"subject": subject, "predicate": predicate, "object": object, **extra}
    p = MagicMock()
    p.payload = payload
    return p


def _mock_scroll_side_effect(points_by_field: dict[str, list]) -> MagicMock:
    """Return a mock client whose scroll() returns *points_by_field* per field.

    *points_by_field* maps the filter field name (``"subject"`` or ``"object"``)
    to a list of payloads that should be returned for that filter.
    """
    client = MagicMock()

    def _scroll(collection_name, limit, offset, with_payload, with_vectors, scroll_filter):
        field = scroll_filter.must[0].key
        value = scroll_filter.must[0].match.value
        payloads = points_by_field.get(f"{field}:{value}", [])
        # Simulate single-page scroll: return all points + no next_offset
        mock_points = []
        for pl in payloads:
            mp = MagicMock()
            mp.payload = pl
            mock_points.append(mp)
        if offset is None:
            return (mock_points, None)
        return ([], None)

    client.scroll.side_effect = _scroll
    return client


# ---------------------------------------------------------------------------
# classify_fact / _predicate_matches
# ---------------------------------------------------------------------------


class TestPredicateMatches:
    def test_exact_keyword(self):
        assert _predicate_matches("has_objective", {"has_objective"}) is True

    def test_case_insensitive(self):
        assert _predicate_matches("Has_Risk", {"has_risk"}) is True

    def test_space_to_underscore(self):
        assert _predicate_matches("has blocker", {"has_blocker"}) is True

    def test_no_match(self):
        assert _predicate_matches("unrelated", {"has_objective"}) is False


class TestClassifyFact:
    def test_classifies_objective(self):
        fact = Fact(subject="Acme", predicate="has_objective", object="growth")
        cats = classify_fact(fact)
        assert cats["objectives"] is True
        assert cats["risks"] is False

    def test_classifies_risk(self):
        fact = Fact(subject="Acme", predicate="risk", object="churn")
        cats = classify_fact(fact)
        assert cats["risks"] is True
        assert cats["objectives"] is False

    def test_classifies_blocker(self):
        fact = Fact(subject="Acme", predicate="blocker", object="budget")
        cats = classify_fact(fact)
        assert cats["blockers"] is True

    def test_classifies_product(self):
        fact = Fact(subject="Acme", predicate="has_product", object="Widget")
        cats = classify_fact(fact)
        assert cats["products"] is True

    def test_classifies_commitment(self):
        fact = Fact(subject="Acme", predicate="commitment", object="SLA")
        cats = classify_fact(fact)
        assert cats["commitments"] is True

    def test_unclassified_fact(self):
        fact = Fact(subject="Acme", predicate="employs", object="Jane")
        cats = classify_fact(fact)
        assert all(not v for v in cats.values())


class TestIsStakeholder:
    def test_subject_is_person(self):
        fact = Fact(subject="Jane", predicate="works_at", object="Acme", subject_type="Person")
        assert _is_stakeholder(fact) is True

    def test_object_is_organization(self):
        fact = Fact(subject="Acme", predicate="partner_of", object="BetaCorp", object_type="Organization")
        assert _is_stakeholder(fact) is True

    def test_neither_is_stakeholder(self):
        fact = Fact(
            subject="Acme",
            predicate="has_product",
            object="Widget",
            subject_type="Company",
            object_type="Product",
        )
        assert _is_stakeholder(fact) is False


# ---------------------------------------------------------------------------
# load_account_state
# ---------------------------------------------------------------------------


class TestLoadAccountState:
    def test_aggregates_facts_from_subject_and_object(self):
        """Facts where account is subject OR object are both included."""
        points_by_field = {
            "subject:Acme": [
                {"subject": "Acme", "predicate": "has_objective", "object": "growth", "source_doc": "doc1"},
                {"subject": "Acme", "predicate": "has_product", "object": "Widget", "source_doc": "doc1"},
            ],
            "object:Acme": [
                {
                    "subject": "Jane",
                    "predicate": "works_at",
                    "object": "Acme",
                    "subject_type": "Person",
                    "source_doc": "doc2",
                },
            ],
        }
        client = _mock_scroll_side_effect(points_by_field)
        state = load_account_state(client, "triplets", "Acme")

        assert len(state.raw_facts) == 3
        assert state.account_name == "Acme"

    def test_classifies_facts_by_predicate(self):
        """Objectives, products, risks are classified correctly."""
        points_by_field = {
            "subject:Acme": [
                {"subject": "Acme", "predicate": "has_objective", "object": "growth"},
                {"subject": "Acme", "predicate": "risk", "object": "churn"},
                {"subject": "Acme", "predicate": "has_product", "object": "Widget"},
                {"subject": "Acme", "predicate": "blocker", "object": "budget"},
            ],
        }
        client = _mock_scroll_side_effect(points_by_field)
        state = load_account_state(client, "triplets", "Acme")

        assert len(state.objectives) == 1
        assert state.objectives[0].object == "growth"
        assert len(state.risks) == 1
        assert state.risks[0].object == "churn"
        assert len(state.products) == 1
        assert state.products[0].object == "Widget"
        assert len(state.blockers) == 1
        assert state.blockers[0].object == "budget"

    def test_aggregates_stakeholders(self):
        """Entities with Person/Organization type are collected."""
        points_by_field = {
            "subject:Acme": [
                {"subject": "Acme", "predicate": "has_contact", "object": "Jane", "object_type": "Person"},
                {"subject": "Acme", "predicate": "partner_of", "object": "BetaCorp", "object_type": "Organization"},
            ],
        }
        client = _mock_scroll_side_effect(points_by_field)
        state = load_account_state(client, "triplets", "Acme")

        assert "Jane" in state.stakeholders
        assert "BetaCorp" in state.stakeholders

    def test_deduplicates_facts(self):
        """Same fact found via subject and object filter is not duplicated."""
        shared = {"subject": "Acme", "predicate": "has_objective", "object": "growth"}
        points_by_field = {
            "subject:Acme": [shared],
            "object:Acme": [shared],  # same triplet appears in both scroll passes
        }
        client = _mock_scroll_side_effect(points_by_field)
        state = load_account_state(client, "triplets", "Acme")

        assert len(state.raw_facts) == 1

    def test_aggregates_commitments(self):
        """Facts with commitment predicates are collected."""
        points_by_field = {
            "subject:Acme": [
                {"subject": "Acme", "predicate": "commitment", "object": "SLA 99.9%"},
            ],
        }
        client = _mock_scroll_side_effect(points_by_field)
        state = load_account_state(client, "triplets", "Acme")

        assert len(state.commitments) == 1
        assert state.commitments[0].object == "SLA 99.9%"

    def test_empty_account(self):
        """Account with no facts returns empty state."""
        client = _mock_scroll_side_effect({})
        state = load_account_state(client, "triplets", "Unknown")

        assert state.account_name == "Unknown"
        assert len(state.raw_facts) == 0
        assert len(state.objectives) == 0
        assert len(state.stakeholders) == 0


# ---------------------------------------------------------------------------
# format_account_state
# ---------------------------------------------------------------------------


class TestFormatAccountState:
    def test_produces_structured_text(self):
        state = AccountState(
            account_name="Acme",
            objectives=[Fact(subject="Acme", predicate="has_objective", object="growth")],
            risks=[Fact(subject="Acme", predicate="risk", object="churn")],
            blockers=[],
            products=[Fact(subject="Acme", predicate="has_product", object="Widget")],
            commitments=[],
            stakeholders=["Jane"],
            raw_facts=[
                Fact(subject="Acme", predicate="has_objective", object="growth"),
                Fact(subject="Acme", predicate="risk", object="churn"),
                Fact(subject="Acme", predicate="has_product", object="Widget"),
            ],
        )
        text = format_account_state(state)

        assert "# Account: Acme" in text
        assert "## Objectives" in text
        assert "- Acme has_objective growth" in text
        assert "## Risks" in text
        assert "- Acme risk churn" in text
        assert "## Products" in text
        assert "- Acme has_product Widget" in text
        assert "## Stakeholders" in text
        assert "- Jane" in text
        assert "Total facts: 3" in text

    def test_omits_empty_sections(self):
        state = AccountState(
            account_name="EmptyCorp",
            objectives=[],
            risks=[],
            blockers=[],
            products=[],
            commitments=[],
            stakeholders=[],
            raw_facts=[],
        )
        text = format_account_state(state)

        assert "# Account: EmptyCorp" in text
        assert "## Objectives" not in text
        assert "## Risks" not in text
        assert "## Stakeholders" not in text
        assert "Total facts: 0" in text

    def test_includes_commitments_section(self):
        state = AccountState(
            account_name="Acme",
            commitments=[Fact(subject="Acme", predicate="commitment", object="SLA")],
            stakeholders=[],
            raw_facts=[Fact(subject="Acme", predicate="commitment", object="SLA")],
        )
        text = format_account_state(state)

        assert "## Commitments" in text
        assert "- Acme commitment SLA" in text

    def test_includes_blockers_section(self):
        state = AccountState(
            account_name="Acme",
            blockers=[Fact(subject="Acme", predicate="blocker", object="budget")],
            stakeholders=[],
            raw_facts=[Fact(subject="Acme", predicate="blocker", object="budget")],
        )
        text = format_account_state(state)

        assert "## Blockers" in text
        assert "- Acme blocker budget" in text
