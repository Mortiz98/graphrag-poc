"""Account state aggregation from Qdrant facts.

Loads triplets from Qdrant for a given account, classifies them by predicate
category (objectives, risks, blockers, products), and produces structured
text output.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.core import logger

# ---------------------------------------------------------------------------
# Predicate classification keywords
# ---------------------------------------------------------------------------

_OBJECTIVE_KEYWORDS = {"has_objective", "objective", "goal", "target"}
_RISK_KEYWORDS = {"has_risk", "risk", "threat", "vulnerability"}
_BLOCKER_KEYWORDS = {"has_blocker", "blocker", "impediment", "obstacle"}
_PRODUCT_KEYWORDS = {"has_product", "product", "service", "offering"}
_COMMITMENT_KEYWORDS = {"has_commitment", "commitment", "committed_to", "pledged"}
_STAKEHOLDER_TYPES = {"Person", "Organization", "Stakeholder"}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Fact:
    """A single fact (triplet) extracted from Qdrant."""

    subject: str
    predicate: str
    object: str
    subject_type: str = ""
    object_type: str = ""
    source_doc: str = ""

    def text(self) -> str:
        return f"{self.subject} {self.predicate} {self.object}"


@dataclass
class AccountState:
    """Aggregated state of an account built from Qdrant facts."""

    account_name: str
    objectives: list[Fact] = field(default_factory=list)
    risks: list[Fact] = field(default_factory=list)
    blockers: list[Fact] = field(default_factory=list)
    products: list[Fact] = field(default_factory=list)
    commitments: list[Fact] = field(default_factory=list)
    stakeholders: list[str] = field(default_factory=list)
    raw_facts: list[Fact] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------


def _predicate_matches(predicate: str, keywords: set[str]) -> bool:
    """Return True if *predicate* (lowercased) matches any keyword."""
    pred_lower = predicate.lower().replace(" ", "_")
    return pred_lower in keywords


def classify_fact(fact: Fact) -> dict[str, bool]:
    """Return a mapping of category → whether *fact* belongs to it."""
    return {
        "objectives": _predicate_matches(fact.predicate, _OBJECTIVE_KEYWORDS),
        "risks": _predicate_matches(fact.predicate, _RISK_KEYWORDS),
        "blockers": _predicate_matches(fact.predicate, _BLOCKER_KEYWORDS),
        "products": _predicate_matches(fact.predicate, _PRODUCT_KEYWORDS),
        "commitments": _predicate_matches(fact.predicate, _COMMITMENT_KEYWORDS),
    }


def _is_stakeholder(fact: Fact) -> bool:
    """Return True if either entity in *fact* is a stakeholder type."""
    return fact.subject_type in _STAKEHOLDER_TYPES or fact.object_type in _STAKEHOLDER_TYPES


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def _scroll_account_facts(
    client: QdrantClient,
    collection_name: str,
    account_name: str,
    batch_size: int = 100,
) -> list[dict]:
    """Scroll all Qdrant points whose subject or object matches *account_name*."""
    all_points: list[dict] = []

    for field_name in ("subject", "object"):
        offset = None
        while True:
            results = client.scroll(
                collection_name=collection_name,
                limit=batch_size,
                offset=offset,
                with_payload=True,
                with_vectors=False,
                scroll_filter=Filter(
                    must=[FieldCondition(key=field_name, match=MatchValue(value=account_name))],
                ),
            )
            points, next_offset = results
            for p in points:
                all_points.append(p.payload)
            if next_offset is None:
                break
            offset = next_offset

    # Deduplicate by subject|predicate|object key
    seen: set[str] = set()
    unique: list[dict] = []
    for p in all_points:
        key = f"{p.get('subject', '')}|{p.get('predicate', '')}|{p.get('object', '')}"
        if key not in seen:
            seen.add(key)
            unique.append(p)

    return unique


def load_account_state(
    client: QdrantClient,
    collection_name: str,
    account_name: str,
) -> AccountState:
    """Aggregate facts for *account_name* from Qdrant and classify them."""
    raw_payloads = _scroll_account_facts(client, collection_name, account_name)

    state = AccountState(account_name=account_name)

    for payload in raw_payloads:
        fact = Fact(
            subject=payload.get("subject", ""),
            predicate=payload.get("predicate", ""),
            object=payload.get("object", ""),
            subject_type=payload.get("subject_type", ""),
            object_type=payload.get("object_type", ""),
            source_doc=payload.get("source_doc", ""),
        )
        state.raw_facts.append(fact)

        categories = classify_fact(fact)
        if categories["objectives"]:
            state.objectives.append(fact)
        if categories["risks"]:
            state.risks.append(fact)
        if categories["blockers"]:
            state.blockers.append(fact)
        if categories["products"]:
            state.products.append(fact)
        if categories["commitments"]:
            state.commitments.append(fact)

        if _is_stakeholder(fact):
            for name, etype in ((fact.subject, fact.subject_type), (fact.object, fact.object_type)):
                if etype in _STAKEHOLDER_TYPES and name not in state.stakeholders:
                    state.stakeholders.append(name)

    logger.info(
        "account_state_loaded",
        account=account_name,
        total_facts=len(state.raw_facts),
        objectives=len(state.objectives),
        risks=len(state.risks),
        blockers=len(state.blockers),
        products=len(state.products),
        stakeholders=len(state.stakeholders),
    )
    return state


def format_account_state(state: AccountState) -> str:
    """Render *state* as a human-readable structured text block."""
    lines: list[str] = [f"# Account: {state.account_name}"]

    def _section(title: str, facts: list[Fact]) -> None:
        if not facts:
            return
        lines.append("")
        lines.append(f"## {title}")
        for f in facts:
            lines.append(f"- {f.text()}")

    _section("Objectives", state.objectives)
    _section("Risks", state.risks)
    _section("Blockers", state.blockers)
    _section("Products", state.products)
    _section("Commitments", state.commitments)

    if state.stakeholders:
        lines.append("")
        lines.append("## Stakeholders")
        for name in state.stakeholders:
            lines.append(f"- {name}")

    lines.append("")
    lines.append(f"Total facts: {len(state.raw_facts)}")
    return "\n".join(lines)
