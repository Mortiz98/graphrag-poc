from app.core.retrieval import get_retrieval_engine


def _trace(tool_name: str, query: str, results, **meta):
    engine = get_retrieval_engine()
    engine.log_trace(
        query=query,
        phase=f"tool:{tool_name}",
        candidates=results,
        metadata=meta,
    )


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
    _trace("search_knowledge_base", query, results, top_k=top_k, scope=scope or None)
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
    _trace("search_by_metadata", query, results, filters=filters or None, scope=scope or None)
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
    _trace("traverse_issue_graph", entity_name, results, entity_id=entity_id, hops=hops)
    if not results:
        return "No graph connections found."
    lines = []
    for r in results:
        source = r.source_doc if r.source_doc else "grafo"
        lines.append(f"- {r.subject} {r.predicate} {r.object} [fuente: {source}]")
    return "\n".join(lines)


def search_by_product(product: str, version: str | None = None, top_k: int = 10) -> str:
    """Search the knowledge base for facts about a specific product.

    Uses structured filtering to find all active triplets matching the product
    name, optionally filtered by version. Searches within the support namespace.

    Args:
        product: Product name to filter by (e.g. "Qdrant", "NebulaGraph").
        version: Optional version filter (e.g. "1.17").
        top_k: Maximum number of results to return.
    """
    filters: dict = {"product": product}
    if version:
        filters["version"] = version
    results = get_retrieval_engine().search_by_filter(
        top_k=top_k,
        filters=filters,
        scope={"system": "support"},
        active_only=True,
    )
    _trace("search_by_product", product, results, filters=filters)
    if not results:
        return f"No results found for product '{product}'."
    lines = []
    for r in results:
        lines.append(f"- {r.subject} {r.predicate} {r.object} [fuente: {r.source_doc}]")
    return "\n".join(lines)


def get_resolution_history(issue_description: str, top_k: int = 5) -> str:
    """Find resolution history for an issue description.

    Searches for similar issues via dense retrieval, then expands the graph
    to find resolved_by and caused_by edges pointing to fixes and root causes.

    Args:
        issue_description: Description of the issue to find resolutions for.
        top_k: Maximum number of initial dense results to use as seeds.
    """
    engine = get_retrieval_engine()
    dense_results = engine.search_dense(
        query=issue_description,
        top_k=top_k,
        scope={"system": "support"},
        active_only=True,
    )
    _trace("get_resolution_history:dense", issue_description, dense_results)

    if not dense_results:
        return "No issues found matching the description."

    lines = ["Issues encontrados:"]
    for r in dense_results:
        lines.append(f"- {r.subject} {r.predicate} {r.object} (score={r.score:.2f}) [fuente: {r.source_doc}]")

    entity_ids = list(
        {r.subject_id for r in dense_results if r.subject_id} | {r.object_id for r in dense_results if r.object_id}
    )
    if entity_ids:
        graph_results = engine.expand_from_graph(
            entity_ids=entity_ids,
            hops=1,
            relation_types=["resolved_by", "caused_by"],
        )
        _trace(
            "get_resolution_history:graph",
            issue_description,
            graph_results,
            relation_types=["resolved_by", "caused_by"],
        )
        if graph_results:
            lines.append("\nCadena de resolución:")
            for gr in graph_results:
                lines.append(f"  - {gr.subject} --{gr.predicate}--> {gr.object} [fuente: grafo]")
        else:
            lines.append("\nNo se encontraron cadenas de resolución en el grafo.")
    else:
        lines.append("\nNo se pudieron expandir los resultados (sin entity IDs).")

    return "\n".join(lines)


def escalation_path(issue_description: str, top_k: int = 5) -> str:
    """Find escalation paths and governing policies for an issue.

    Searches for similar issues via dense retrieval, then expands the graph
    to find escalated_to and governed_by edges pointing to teams and policies.

    Args:
        issue_description: Description of the issue to find escalation paths for.
        top_k: Maximum number of initial dense results to use as seeds.
    """
    engine = get_retrieval_engine()
    dense_results = engine.search_dense(
        query=issue_description,
        top_k=top_k,
        scope={"system": "support"},
        active_only=True,
    )
    _trace("escalation_path:dense", issue_description, dense_results)

    if not dense_results:
        return "No issues found matching the description."

    lines = ["Issues encontrados:"]
    for r in dense_results:
        lines.append(f"- {r.subject} {r.predicate} {r.object} (score={r.score:.2f}) [fuente: {r.source_doc}]")

    entity_ids = list(
        {r.subject_id for r in dense_results if r.subject_id} | {r.object_id for r in dense_results if r.object_id}
    )
    if entity_ids:
        graph_results = engine.expand_from_graph(
            entity_ids=entity_ids,
            hops=1,
            relation_types=["escalated_to", "governed_by"],
        )
        _trace(
            "escalation_path:graph",
            issue_description,
            graph_results,
            relation_types=["escalated_to", "governed_by"],
        )
        if graph_results:
            lines.append("\nRutas de escalación:")
            for gr in graph_results:
                lines.append(f"  - {gr.subject} --{gr.predicate}--> {gr.object} [fuente: grafo]")
        else:
            lines.append("\nNo se encontraron rutas de escalación en el grafo.")
    else:
        lines.append("\nNo se pudieron expandir los resultados (sin entity IDs).")

    return "\n".join(lines)
