"""AccountStore: authoritative structured state per account.

Provides a typed, queryable object that aggregates facts, commitments,
stakeholders and risks from Qdrant into a single AccountState model.
This is the source of truth the AM agent reads before responding.
"""

from datetime import datetime, timezone

from app.core import logger
from app.core.retrieval import get_retrieval_engine
from app.models.schemas import AccountState, CommitmentEntry, StakeholderEntry


def load_account_state(account_id: str, tenant_id: str | None = None) -> AccountState:
    engine = get_retrieval_engine()
    scope = {"system": "am", "account_id": account_id}
    if tenant_id:
        scope["tenant_id"] = tenant_id

    facts = engine.search_by_filter(
        top_k=50,
        scope=scope,
        filters={"fact_type": "fact"},
        active_only=True,
    )

    stakeholders = engine.search_by_filter(
        top_k=30,
        scope=scope,
        filters={"fact_type": "stakeholder"},
        active_only=True,
    )

    commitments = engine.search_by_filter(
        top_k=30,
        scope=scope,
        filters={"fact_type": "commitment"},
        active_only=True,
    )

    stakeholder_entries = []
    for r in stakeholders:
        stakeholder_entries.append(
            StakeholderEntry(
                name=r.subject,
                role=r.object,
                last_seen=r.metadata.get("valid_from", ""),
            )
        )

    commitment_entries = []
    for r in commitments:
        commitment_entries.append(
            CommitmentEntry(
                description=f"{r.subject} {r.predicate} {r.object}",
                owner=r.metadata.get("stakeholder", ""),
                due_date=r.metadata.get("valid_to", ""),
                status="open",
                fact_id=r.metadata.get("id", ""),
            )
        )

    objectives = []
    risks = []
    blockers = []
    products_of_interest = []
    for r in facts:
        pred = r.predicate.lower()
        if pred in ("has_objective", "objective_is", "targets"):
            objectives.append(f"{r.subject} {r.predicate} {r.object}")
        elif pred in ("has_risk", "risk_is", "at_risk"):
            risks.append(f"{r.subject} {r.predicate} {r.object}")
        elif pred in ("blocked_by", "has_blocker", "blocker"):
            blockers.append(f"{r.subject} {r.predicate} {r.object}")
        elif pred in ("interested_in", "uses_product", "evaluates"):
            products_of_interest.append(r.object)

    last_interaction = ""
    for r in facts:
        vf = r.metadata.get("valid_from", "")
        if vf and (not last_interaction or vf > last_interaction):
            last_interaction = vf

    state = AccountState(
        account_id=account_id,
        tenant_id=tenant_id,
        stakeholders=stakeholder_entries,
        objectives=objectives,
        products_of_interest=products_of_interest,
        risks=risks,
        commitments=commitment_entries,
        blockers=blockers,
        last_interaction=last_interaction,
        last_updated=datetime.now(timezone.utc).isoformat(),
    )

    logger.info(
        "account_state_loaded",
        account_id=account_id,
        stakeholders=len(stakeholder_entries),
        commitments=len(commitment_entries),
        facts=len(facts),
    )
    return state


def format_account_state(state: AccountState) -> str:
    lines = [f"=== Account State: {state.account_id} ==="]

    if state.stakeholders:
        lines.append("\nStakeholders:")
        for s in state.stakeholders:
            lines.append(f"  - {s.name}: {s.role}")

    if state.objectives:
        lines.append("\nObjectives:")
        for o in state.objectives:
            lines.append(f"  - {o}")

    if state.products_of_interest:
        lines.append("\nProducts of Interest:")
        for p in state.products_of_interest:
            lines.append(f"  - {p}")

    if state.commitments:
        lines.append("\nOpen Commitments:")
        for c in state.commitments:
            lines.append(f"  - {c.description} (owner: {c.owner}, due: {c.due_date})")

    if state.risks:
        lines.append("\nRisks:")
        for r in state.risks:
            lines.append(f"  - {r}")

    if state.blockers:
        lines.append("\nBlockers:")
        for b in state.blockers:
            lines.append(f"  - {b}")

    if state.last_interaction:
        lines.append(f"\nLast interaction: {state.last_interaction}")

    return "\n".join(lines)
