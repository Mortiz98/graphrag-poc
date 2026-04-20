from app.core.retrieval import get_retrieval_engine


def search_knowledge_base(
    query: str,
    top_k: int = 5,
    system: str | None = None,
    tenant_id: str | None = None,
) -> str:
    """Search the knowledge base using dense vector retrieval.

    Finds the most relevant triplets for a given query by embedding the question
    and searching Qdrant. Only returns currently active (non-superseded) facts.

    Args:
        query: The question or search text.
        top_k: Maximum number of results to return.
        system: Namespace to search in (e.g. "support", "am"). If None, searches all.
        tenant_id: Optional tenant scope filter.
    """
    scope: dict = {}
    if system:
        scope["system"] = system
    if tenant_id:
        scope["tenant_id"] = tenant_id
    results = get_retrieval_engine().search_dense(
        query=query,
        top_k=top_k,
        scope=scope or None,
        active_only=True,
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
    system: str | None = None,
    tenant_id: str | None = None,
    product: str | None = None,
    version: str | None = None,
    severity: str | None = None,
    account_id: str | None = None,
) -> str:
    """Search the knowledge base using dense retrieval with metadata filters.

    Similar to search_knowledge_base but allows filtering by product, version,
    severity, and account_id. Only returns currently active (non-superseded) facts.

    Args:
        query: The question or search text.
        top_k: Maximum number of results to return.
        system: Namespace to search in (e.g. "support", "am"). If None, searches all.
        tenant_id: Optional tenant scope filter.
        product: Filter by product name (support domain).
        version: Filter by version (support domain).
        severity: Filter by severity level (support domain).
        account_id: Filter by account (AM domain).
    """
    filters = {}
    if product:
        filters["product"] = product
    if version:
        filters["version"] = version
    if severity:
        filters["severity"] = severity
    scope: dict = {}
    if system:
        scope["system"] = system
    if tenant_id:
        scope["tenant_id"] = tenant_id
    if account_id:
        scope["account_id"] = account_id
    results = get_retrieval_engine().search_dense(
        query=query,
        top_k=top_k,
        filters=filters or None,
        scope=scope or None,
        active_only=True,
    )
    if not results:
        return "No results found."
    lines = []
    for r in results:
        lines.append(f"- {r.subject} {r.predicate} {r.object} (score={r.score:.2f}, source={r.source_doc})")
    return "\n".join(lines)


def traverse_issue_graph(entity_name: str, hops: int = 1) -> str:
    """Traverse the knowledge graph from a given entity.

    Follows edges in NebulaGraph starting from the named entity to discover
    related entities and relationships (e.g., Issue → caused_by → RootCause).

    Args:
        entity_name: The name of the entity to start traversal from.
        hops: Number of hops to traverse (default 1).
    """
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
