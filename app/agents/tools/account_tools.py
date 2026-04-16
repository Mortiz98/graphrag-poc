from app.core.retrieval import get_retrieval_engine


def search_episodes(query: str, account_id: str, top_k: int = 5) -> str:
    results = get_retrieval_engine().search_dense(
        query=query,
        top_k=top_k,
        scope={"system": "am", "account_id": account_id},
    )
    if not results:
        return "No episodes found for this account."
    lines = []
    for r in results:
        lines.append(f"- {r.subject} {r.predicate} {r.object} (score={r.score:.2f})")
    return "\n".join(lines)


def get_account_state(account_id: str) -> str:
    results = get_retrieval_engine().search_dense(
        query="account state facts commitments stakeholders",
        top_k=20,
        scope={"system": "am", "account_id": account_id},
        filters={"fact_type": "fact"},
    )
    if not results:
        return f"No state found for account {account_id}."
    lines = [f"Account: {account_id}"]
    facts = [r for r in results if r.metadata.get("fact_type") == "fact"]
    for r in facts:
        valid = r.metadata.get("valid_to", "present")
        lines.append(f"  FACT: {r.subject} {r.predicate} {r.object} (valid until: {valid})")
    return "\n".join(lines)


def get_commitments(account_id: str) -> str:
    results = get_retrieval_engine().search_dense(
        query="commitments promises deliverables",
        top_k=10,
        scope={"system": "am", "account_id": account_id},
        filters={"fact_type": "commitment"},
    )
    if not results:
        return f"No commitments found for account {account_id}."
    lines = [f"Commitments for {account_id}:"]
    for r in results:
        due = r.metadata.get("valid_to", "no due date")
        lines.append(f"  - {r.subject} {r.predicate} {r.object} (due: {due})")
    return "\n".join(lines)


def get_stakeholder_map(account_id: str) -> str:
    results = get_retrieval_engine().search_dense(
        query="stakeholders contacts roles",
        top_k=10,
        scope={"system": "am", "account_id": account_id},
        filters={"fact_type": "stakeholder"},
    )
    if not results:
        return f"No stakeholders found for account {account_id}."
    lines = [f"Stakeholders for {account_id}:"]
    for r in results:
        lines.append(f"  - {r.subject} {r.predicate} {r.object}")
    return "\n".join(lines)
