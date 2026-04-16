"""Query pipeline: question -> vector search -> graph traversal -> LLM answer."""

from app.core import logger
from app.core.llm import get_llm
from app.core.retrieval import SearchResult, get_retrieval_engine
from app.models.schemas import QueryResponse, SourceInfo, SourceTriplet
from app.prompts.qa import QA_SYSTEM_PROMPT, QA_USER_PROMPT


def search_similar_triplets(
    question: str,
    top_k: int = 5,
    min_score: float = 0.0,
    filters: dict | None = None,
) -> list[SearchResult]:
    """Search for similar triplets using the retrieval engine.

    Args:
        question: The search query
        top_k: Maximum number of results
        min_score: Minimum similarity score threshold
        filters: Optional metadata filters

    Returns:
        List of SearchResult objects
    """
    engine = get_retrieval_engine()

    logger.info(
        "retrieval_started",
        question=question[:50],
        top_k=top_k,
        min_score=min_score,
        filters=filters,
    )

    results = engine.search_dense(
        query=question,
        top_k=top_k,
        min_score=min_score,
        filters=filters,
    )

    engine.log_trace(
        query=question,
        phase="vector_search",
        candidates=results,
        metadata={"top_k": top_k, "min_score": min_score, "filters": filters},
    )

    return results


def traverse_graph(entity_ids: list[str], hop_depth: int = 1) -> list[SearchResult]:
    """Traverse the knowledge graph from given entity IDs.

    Args:
        entity_ids: List of entity IDs to expand from
        hop_depth: Number of hops to traverse

    Returns:
        List of SearchResult objects from graph
    """
    engine = get_retrieval_engine()
    results = engine.expand_from_graph(entity_ids, hops=hop_depth)

    engine.log_trace(
        query="graph_expansion",
        phase="graph_traversal",
        candidates=results,
        metadata={"entity_count": len(entity_ids), "hops": hop_depth},
    )

    return results


def _fuse_context(
    vector_results: list[SearchResult],
    graph_results: list[SearchResult],
) -> tuple[str, list[SearchResult]]:
    """Fuse vector and graph results into a context string.

    Args:
        vector_results: Results from vector search
        graph_results: Results from graph expansion

    Returns:
        Tuple of (context_string, fused_results)
    """
    engine = get_retrieval_engine()
    fused, _ = engine.fuse_results(vector_results, graph_results)

    context_lines = []
    for r in fused:
        context_lines.append(f"- {r.subject} {r.predicate} {r.object}")

    context = "\n".join(context_lines)
    return context, fused


def _compute_confidence(vector_results: list[SearchResult], fused_count: int) -> float:
    """Compute confidence score based on vector similarity and coverage.

    Args:
        vector_results: Results from vector search (with scores)
        fused_count: Total number of unique fused results

    Returns:
        Confidence score between 0.0 and 1.0
    """
    if not vector_results:
        return 0.0

    avg_similarity = sum(r.score for r in vector_results) / len(vector_results)
    # Require at least 3 good results for max coverage score
    coverage_factor = min(fused_count / 3.0, 1.0)
    confidence = avg_similarity * 0.7 + coverage_factor * 0.3

    return round(min(max(confidence, 0.0), 1.0), 2)


def generate_answer(question: str, context: str) -> str:
    """Generate an answer using the LLM.

    Args:
        question: User question
        context: Context from retrieval

    Returns:
        Generated answer
    """
    if not context.strip():
        return "I could not find relevant information to answer your question."

    llm = get_llm(temperature=0.1)
    prompt = QA_USER_PROMPT.format(context=context, question=question)

    response = llm.invoke(
        [
            {"role": "system", "content": QA_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
    )

    answer = response.content.strip()
    logger.info("answer_generated", question=question[:50], answer_len=len(answer))
    return answer


def stream_answer(question: str, context: str):
    """Stream an answer using the LLM.

    Args:
        question: User question
        context: Context from retrieval

    Yields:
        Text chunks of the generated answer
    """
    if not context.strip():
        yield "I could not find relevant information to answer your question."
        return

    from langchain_core.messages import HumanMessage, SystemMessage

    llm = get_llm(temperature=0.1, streaming=True)
    prompt = QA_USER_PROMPT.format(context=context, question=question)

    messages = [
        SystemMessage(content=QA_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ]

    for chunk in llm.stream(messages):
        if chunk.content:
            yield chunk.content


def query(
    question: str,
    top_k: int = 5,
    min_score: float = 0.0,
    filters: dict | None = None,
) -> QueryResponse:
    """Execute a complete query pipeline.

    Args:
        question: User question
        top_k: Number of results to retrieve
        min_score: Minimum similarity threshold
        filters: Optional metadata filters

    Returns:
        QueryResponse with answer, sources, and metadata
    """
    logger.info(
        "query_started",
        question=question[:50],
        top_k=top_k,
        min_score=min_score,
        filters=filters,
    )

    # Step 1: Vector search
    vector_results = search_similar_triplets(
        question,
        top_k=top_k,
        min_score=min_score,
        filters=filters,
    )

    # Step 2: Extract entity IDs for graph expansion
    entity_ids = list(
        {r.subject_id for r in vector_results if r.subject_id} | {r.object_id for r in vector_results if r.object_id}
    )

    # Step 3: Graph traversal
    graph_results = traverse_graph(entity_ids, hop_depth=1)

    # Step 4: Fuse results
    context, fused_results = _fuse_context(vector_results, graph_results)

    # Step 5: Extract entities found
    entities_found = list(
        {r.subject for r in fused_results if r.subject} | {r.object for r in fused_results if r.object}
    )

    # Step 6: Compute confidence
    confidence = _compute_confidence(vector_results, len(fused_results))

    # Step 7: Generate answer
    answer = generate_answer(question, context)

    # Step 8: Build sources from vector results (they have source info)
    sources_by_chunk: dict[str, SourceInfo] = {}
    for r in vector_results:
        chunk_id = r.chunk_id or "unknown"
        if chunk_id not in sources_by_chunk:
            sources_by_chunk[chunk_id] = SourceInfo(
                chunk_id=chunk_id,
                document=r.source_doc,
                triplets=[],
            )
        sources_by_chunk[chunk_id].triplets.append(
            SourceTriplet(subject=r.subject, predicate=r.predicate, object=r.object)
        )

    logger.info(
        "query_completed",
        answer_len=len(answer),
        sources=len(sources_by_chunk),
        entities=len(entities_found),
        confidence=confidence,
        vector_results=len(vector_results),
        graph_results=len(graph_results),
    )

    return QueryResponse(
        answer=answer,
        sources=list(sources_by_chunk.values()),
        entities_found=entities_found,
        confidence=confidence,
    )
