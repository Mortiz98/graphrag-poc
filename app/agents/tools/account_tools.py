from app.core.account_store import format_account_state, load_account_state
from app.core.retrieval import get_retrieval_engine
from app.pipelines.memory_writer import record_fact, supersede_fact


def search_episodes(query: str, account_id: str, top_k: int = 5) -> str:
    results = get_retrieval_engine().search_dense(
        query=query,
        top_k=top_k,
        scope={"system": "am", "account_id": account_id},
        active_only=True,
    )
    if not results:
        return "No episodes found for this account."
    lines = []
    for r in results:
        lines.append(f"- {r.subject} {r.predicate} {r.object} (score={r.score:.2f})")
    return "\n".join(lines)


def get_account_state(account_id: str) -> str:
    state = load_account_state(account_id)
    return format_account_state(state)


def get_commitments(account_id: str) -> str:
    results = get_retrieval_engine().search_by_filter(
        top_k=30,
        scope={"system": "am", "account_id": account_id},
        filters={"fact_type": "commitment"},
        active_only=True,
    )
    if not results:
        return f"No commitments found for account {account_id}."
    lines = [f"Commitments for {account_id}:"]
    for r in results:
        due = r.metadata.get("valid_to", "no due date")
        owner = r.metadata.get("stakeholder", "unassigned")
        lines.append(f"  - {r.subject} {r.predicate} {r.object} (due: {due}, owner: {owner})")
    return "\n".join(lines)


def get_stakeholder_map(account_id: str) -> str:
    results = get_retrieval_engine().search_by_filter(
        top_k=30,
        scope={"system": "am", "account_id": account_id},
        filters={"fact_type": "stakeholder"},
        active_only=True,
    )
    if not results:
        return f"No stakeholders found for account {account_id}."
    lines = [f"Stakeholders for {account_id}:"]
    for r in results:
        lines.append(f"  - {r.subject} {r.predicate} {r.object}")
    return "\n".join(lines)


def write_fact(
    subject: str,
    predicate: str,
    object_: str,
    account_id: str,
    fact_type: str = "fact",
    confidence: float | None = None,
) -> str:
    fact_id = record_fact(
        subject=subject,
        predicate=predicate,
        object_=object_,
        system="am",
        account_id=account_id,
        fact_type=fact_type,
        confidence=confidence,
    )
    return f"Recorded {fact_type} with id {fact_id}: {subject} {predicate} {object_}"


def update_fact(
    old_fact_id: str,
    new_subject: str,
    new_predicate: str,
    new_object: str,
    account_id: str,
    reason: str = "",
) -> str:
    new_id = supersede_fact(
        old_fact_id=old_fact_id,
        new_subject=new_subject,
        new_predicate=new_predicate,
        new_object=new_object,
        system="am",
        account_id=account_id,
        reason=reason,
    )
    return f"Superseded {old_fact_id} with {new_id}: {new_subject} {new_predicate} {new_object}"


def write_commitment(
    subject: str,
    predicate: str,
    object_: str,
    account_id: str,
    due_date: str | None = None,
    owner: str | None = None,
) -> str:
    fact_id = record_fact(
        subject=subject,
        predicate=predicate,
        object_=object_,
        system="am",
        account_id=account_id,
        fact_type="commitment",
        valid_to=due_date,
        stakeholder=owner,
    )
    return f"Recorded commitment with id {fact_id}: {subject} {predicate} {object_} (due: {due_date}, owner: {owner})"


def write_stakeholder(
    subject: str,
    predicate: str,
    object_: str,
    account_id: str,
) -> str:
    fact_id = record_fact(
        subject=subject,
        predicate=predicate,
        object_=object_,
        system="am",
        account_id=account_id,
        fact_type="stakeholder",
    )
    return f"Recorded stakeholder with id {fact_id}: {subject} {predicate} {object_}"
