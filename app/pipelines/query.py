"""Query pipeline: question -> vector search -> graph traversal -> LLM answer."""

from app.core import logger
from app.core.genai import generate, generate_stream
from app.core.retrieval import SearchResult, get_retrieval_engine
from app.models.schemas import QueryResponse, SourceInfo, SourceTriplet
from app.prompts.qa import QA_SYSTEM_PROMPT, QA_USER_PROMPT


def search_similar_triplets(
    question: str,
    top_k: int = 5,
    min_score: float = 0.0,
    filters: dict | None = None,
    scope: dict | None = None,
    active_only: bool = True,
) -> list[SearchResult]:
    engine = get_retrieval_engine()

    logger.info(
        "retrieval_started",
        question=question[:50],
        top_k=top_k,
        min_score=min_score,
        filters=filters,
        scope=scope,
        active_only=active_only,
    )

    results = engine.search_dense(
        query=question,
        top_k=top_k,
        min_score=min_score,
        filters=filters,
        scope=scope,
        active_only=active_only,
    )

    engine.log_trace(
        query=question,
        phase="vector_search",
        candidates=results,
        metadata={"top_k": top_k, "min_score": min_score, "filters": filters, "scope": scope},
    )

    return results


def traverse_graph(entity_ids: list[str], hop_depth: int = 1) -> list[SearchResult]:
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
    engine = get_retrieval_engine()
    fused, _ = engine.fuse_results(vector_results, graph_results)

    context_lines = []
    for r in fused:
        context_lines.append(f"- {r.subject} {r.predicate} {r.object}")

    context = "\n".join(context_lines)
    return context, fused


def _compute_confidence(vector_results: list[SearchResult], fused_count: int) -> float:
    if not vector_results:
        return 0.0

    avg_similarity = sum(r.score for r in vector_results) / len(vector_results)
    coverage_factor = min(fused_count / 3.0, 1.0)
    confidence = avg_similarity * 0.7 + coverage_factor * 0.3

    return round(min(max(confidence, 0.0), 1.0), 2)


def generate_answer(question: str, context: str) -> str:
    if not context.strip():
        return "I could not find relevant information to answer your question."

    prompt = QA_USER_PROMPT.format(context=context, question=question)
    answer = generate(prompt=prompt, system=QA_SYSTEM_PROMPT, temperature=0.1).strip()
    logger.info("answer_generated", question=question[:50], answer_len=len(answer))
    return answer


def stream_answer(question: str, context: str):
    if not context.strip():
        yield "I could not find relevant information to answer your question."
        return

    prompt = QA_USER_PROMPT.format(context=context, question=question)

    yield from generate_stream(prompt=prompt, system=QA_SYSTEM_PROMPT, temperature=0.1)


def query(
    question: str,
    top_k: int = 5,
    min_score: float = 0.0,
    filters: dict | None = None,
    scope: dict | None = None,
    active_only: bool = True,
) -> QueryResponse:
    logger.info(
        "query_started",
        question=question[:50],
        top_k=top_k,
        min_score=min_score,
        filters=filters,
        scope=scope,
        active_only=active_only,
    )

    vector_results = search_similar_triplets(
        question,
        top_k=top_k,
        min_score=min_score,
        filters=filters,
        scope=scope,
        active_only=active_only,
    )

    entity_ids = list(
        {r.subject_id for r in vector_results if r.subject_id} | {r.object_id for r in vector_results if r.object_id}
    )

    graph_results = traverse_graph(entity_ids, hop_depth=1)

    context, fused_results = _fuse_context(vector_results, graph_results)

    entities_found = list(
        {r.subject for r in fused_results if r.subject} | {r.object for r in fused_results if r.object}
    )

    confidence = _compute_confidence(vector_results, len(fused_results))

    answer = generate_answer(question, context)
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
