from app.core.retrieval import get_retrieval_engine


def search_knowledge_base(query: str, top_k: int = 5, system: str = "support", tenant_id: str | None = None) -> str:
    scope = {"system": system}
    if tenant_id:
        scope["tenant_id"] = tenant_id
    results = get_retrieval_engine().search_dense(
        query=query,
        top_k=top_k,
        scope=scope,
    )
    if not results:
        return "No results found."
    lines = []
    for r in results:
        lines.append(f"- {r.subject} {r.predicate} {r.object} (score={r.score:.2f}, source={r.source_doc})")
    return "\n".join(lines)


def search_by_metadata(
    query: str,
    top_k: int = 5,
    system: str = "support",
    tenant_id: str | None = None,
    product: str | None = None,
    version: str | None = None,
    severity: str | None = None,
    account_id: str | None = None,
) -> str:
    filters = {}
    if product:
        filters["product"] = product
    if version:
        filters["version"] = version
    if severity:
        filters["severity"] = severity
    scope = {"system": system}
    if tenant_id:
        scope["tenant_id"] = tenant_id
    if account_id:
        scope["account_id"] = account_id
    results = get_retrieval_engine().search_dense(
        query=query,
        top_k=top_k,
        filters=filters or None,
        scope=scope,
    )
    if not results:
        return "No results found."
    lines = []
    for r in results:
        lines.append(f"- {r.subject} {r.predicate} {r.object} (score={r.score:.2f}, source={r.source_doc})")
    return "\n".join(lines)


def traverse_issue_graph(entity_name: str, hops: int = 1, tenant_id: str | None = None) -> str:
    from app.pipelines.ingestion import _sanitize_vertex_id

    entity_id = _sanitize_vertex_id(entity_name)
    results = get_retrieval_engine().expand_from_graph(
        entity_ids=[entity_id],
        hops=hops,
    )
    if not results:
        return "No graph connections found."
    lines = []
    for r in results:
        lines.append(f"- {r.subject} {r.predicate} {r.object}")
    return "\n".join(lines)
