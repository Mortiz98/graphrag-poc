from app.core.account_store import format_account_state, load_account_state
from app.core.retrieval import get_retrieval_engine
from app.pipelines.memory_writer import record_fact, supersede_fact


def search_episodes(query: str, account_id: str, top_k: int = 5) -> str:
    """Search episodic memory for a specific account.

    Finds relevant past interactions and events for an account using dense
    vector search. Only returns currently active (non-superseded) facts.

    Args:
        query: The question or topic to search for.
        account_id: The account identifier to scope the search.
        top_k: Maximum number of results to return.
    """
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
    """Get the full structured state of an account.

    Loads all active facts, stakeholders, commitments, risks, and blockers
    for the given account. Use this first when starting a conversation to
    understand the current account context.

    Args:
        account_id: The account identifier.
    """
    state = load_account_state(account_id)
    return format_account_state(state)


def get_commitments(account_id: str) -> str:
    """List all open commitments for an account.

    Returns commitment records with due dates and owners. Useful for
    reviewing what the account has promised or needs to deliver.

    Args:
        account_id: The account identifier.
    """
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
    """List all stakeholders for an account.

    Returns the people and their roles associated with the account.

    Args:
        account_id: The account identifier.
    """
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
    """Record a new fact about an account.

    Creates a new fact in the knowledge base. Use this when the user
    mentions information not yet tracked. Do NOT use for commitments
    or stakeholders — use write_commitment/write_stakeholder instead.

    Args:
        subject: The entity the fact is about.
        predicate: The relationship (e.g. "has_tier", "uses_product").
        object_: The value or related entity.
        account_id: The account this fact belongs to.
        fact_type: Type of fact (default "fact").
        confidence: Optional confidence score (0.0-1.0).
    """
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
    """Update an existing fact by superseding it with a new one.

    Marks the old fact as inactive and creates a new fact in its place.
    Use this when a fact has changed (e.g., tier upgrade, contact change).
    Do NOT use for new information — use write_fact instead.

    Args:
        old_fact_id: The ID of the fact to supersede.
        new_subject: Updated subject.
        new_predicate: Updated predicate.
        new_object: Updated object/value.
        account_id: The account this fact belongs to.
        reason: Optional reason for the update.
    """
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
    """Record a new commitment for an account.

    Creates a commitment record with optional due date and owner.
    Use this when the account makes a promise or agrees to a deliverable.

    Args:
        subject: The entity the commitment is about.
        predicate: The commitment type (e.g. "will_deliver", "agrees_to").
        object_: What is committed.
        account_id: The account this commitment belongs to.
        due_date: Optional due date (ISO format).
        owner: Optional person responsible.
    """
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
    """Record a stakeholder for an account.

    Creates a stakeholder record linking a person to their role.
    Use this when a new contact is mentioned for the account.

    Args:
        subject: The person or entity name.
        predicate: The role relationship (e.g. "is_decision_maker", "manages").
        object_: The role or responsibility.
        account_id: The account this stakeholder belongs to.
    """
    fact_id = record_fact(
        subject=subject,
        predicate=predicate,
        object_=object_,
        system="am",
        account_id=account_id,
        fact_type="stakeholder",
    )
    return f"Recorded stakeholder with id {fact_id}: {subject} {predicate} {object_}"
