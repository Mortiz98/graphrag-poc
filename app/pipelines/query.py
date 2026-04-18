"""Query pipeline: question -> query expansion -> vector search -> graph traversal -> LLM answer."""

from app.config import get_settings
from app.core import logger
from app.core.embeddings import get_embeddings
from app.core.genai import generate as gemini_generate
from app.core.graph import get_nebula_session
from app.core.llm import get_llm
from app.core.vectorstore import ensure_collection_exists, get_qdrant_client
from app.models.graph_schema import EDGE_RELATED_TO, SPACE_NAME, escape_ngql
from app.models.schemas import QueryResponse, SourceInfo, SourceTriplet
from app.prompts.qa import QA_SYSTEM_PROMPT, QA_USER_PROMPT, QUERY_EXPANSION_PROMPT


def expand_query(question: str) -> list[str]:
    """Expand a query into 2-3 variations using Gemini.

    Falls back to the existing LangChain LLM when Gemini is not configured.

    Args:
        question: The original user query.

    Returns:
        A list of expanded query variations (excluding the original).
    """
    prompt = QUERY_EXPANSION_PROMPT.format(query=question)
    settings = get_settings()

    try:
        if settings.is_gemini_configured:
            raw_text = gemini_generate(prompt)
        else:
            llm = get_llm(temperature=0.3)
            response = llm.invoke([{"role": "user", "content": prompt}])
            raw_text = response.content.strip()
    except Exception as exc:
        logger.warning("query_expansion_failed", error=str(exc))
        return []

    variations = [line.strip() for line in raw_text.splitlines() if line.strip()]
    logger.info("query_expansion_completed", original=question[:50], variations=len(variations))
    return variations


def search_similar_triplets(question: str, top_k: int = 5) -> list[dict]:
    settings = get_settings()
    client = get_qdrant_client()
    ensure_collection_exists(client, settings.qdrant_collection_name)
    embeddings = get_embeddings()

    query_vector = embeddings.embed_query(question)

    results = client.query_points(
        collection_name=settings.qdrant_collection_name,
        query=query_vector,
        limit=top_k,
        with_payload=True,
    )

    triplets = []
    for point in results.points:
        triplets.append(
            {
                "subject": point.payload.get("subject", ""),
                "predicate": point.payload.get("predicate", ""),
                "object": point.payload.get("object", ""),
                "subject_id": point.payload.get("subject_id", ""),
                "object_id": point.payload.get("object_id", ""),
                "chunk_id": point.payload.get("chunk_id", ""),
                "source_doc": point.payload.get("source_doc", ""),
                "score": point.score,
            }
        )

    logger.info("vector_search_completed", question=question[:50], results=len(triplets))
    return triplets


def traverse_graph(entity_ids: list[str], hop_depth: int = 1) -> list[dict]:
    if not entity_ids:
        return []

    graph_triplets = []
    seen_edges = set()

    with get_nebula_session() as session:
        session.execute(f"USE {SPACE_NAME}")

        for entity_id in entity_ids:
            safe_id = escape_ngql(entity_id)
            for direction in ["out", "in"]:
                if direction == "out":
                    query = (
                        f'GO FROM "{safe_id}" OVER {EDGE_RELATED_TO} '
                        f"YIELD {EDGE_RELATED_TO}._src AS src, "
                        f"{EDGE_RELATED_TO}._dst AS dst, "
                        f"{EDGE_RELATED_TO}.relation AS relation"
                    )
                else:
                    query = (
                        f'GO FROM "{safe_id}" OVER {EDGE_RELATED_TO} REVERSELY '
                        f"YIELD {EDGE_RELATED_TO}._src AS src, "
                        f"{EDGE_RELATED_TO}._dst AS dst, "
                        f"{EDGE_RELATED_TO}.relation AS relation"
                    )

                result = session.execute(query)
                if not result.is_succeeded():
                    continue

                for row in result.rows():
                    try:
                        src_id_bytes = row.values[0].get_sVal()
                        dst_id_bytes = row.values[1].get_sVal()
                        rel_bytes = row.values[2].get_sVal()

                        src_id = src_id_bytes.decode() if isinstance(src_id_bytes, bytes) else str(src_id_bytes)
                        dst_id = dst_id_bytes.decode() if isinstance(dst_id_bytes, bytes) else str(dst_id_bytes)
                        relation = rel_bytes.decode() if isinstance(rel_bytes, bytes) else str(rel_bytes)

                        edge_key = f"{src_id}-{relation}-{dst_id}"
                        if edge_key in seen_edges:
                            continue
                        seen_edges.add(edge_key)

                        graph_triplets.append(
                            {
                                "subject": src_id.replace("_", " "),
                                "predicate": relation,
                                "object": dst_id.replace("_", " "),
                                "subject_id": src_id,
                                "object_id": dst_id,
                            }
                        )
                    except Exception:
                        continue

            entity_names_query = f'FETCH PROP ON * "{safe_id}" YIELD vertex AS v'
            result = session.execute(entity_names_query)
            if not result.is_succeeded():
                continue

            for row in result.rows():
                try:
                    v = row.values[0]
                    vertex = v.get_vVal()
                    vid_bytes = vertex.vid.get_sVal()
                    vid_str = vid_bytes.decode() if isinstance(vid_bytes, bytes) else str(vid_bytes)
                    for tag in vertex.tags:
                        if tag.name == b"entity":
                            name = tag.props.get(b"name")
                            if name and name.get_sVal():
                                name_str = name.get_sVal().decode()
                                for gt in graph_triplets:
                                    if gt["subject_id"] == vid_str:
                                        gt["subject"] = name_str
                                    if gt["object_id"] == vid_str:
                                        gt["object"] = name_str
                except Exception:
                    continue

    logger.info(
        "graph_traversal_completed",
        entities=len(entity_ids),
        triplets=len(graph_triplets),
    )
    return graph_triplets


def _fuse_context(
    vector_triplets: list[dict],
    graph_triplets: list[dict],
) -> tuple[str, list[dict]]:
    seen_keys = set()
    fused = []
    all_triplets = vector_triplets + graph_triplets

    for t in all_triplets:
        key = f"{t.get('subject', '')}|{t.get('predicate', '')}|{t.get('object', '')}"
        if key not in seen_keys:
            seen_keys.add(key)
            fused.append(t)

    context_lines = []
    for t in fused:
        context_lines.append(f"- {t['subject']} {t['predicate']} {t['object']}")

    context = "\n".join(context_lines)
    return context, fused


def _compute_confidence(vector_triplets: list[dict], fused_count: int) -> float:
    if not vector_triplets:
        return 0.0

    avg_similarity = sum(t.get("score", 0.0) for t in vector_triplets) / len(vector_triplets)
    coverage_factor = min(fused_count / 3.0, 1.0)
    confidence = avg_similarity * 0.7 + coverage_factor * 0.3

    return round(min(max(confidence, 0.0), 1.0), 2)


def generate_answer(question: str, context: str) -> str:
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
    logger.info("answer_generated", question=question[:50])
    return answer


def stream_answer(question: str, context: str):
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


def _fuse_expansion_results(all_result_sets: list[list[dict]]) -> list[dict]:
    """Deduplicate triplets collected from multiple query variations.

    Keeps the highest-scoring duplicate when the same triplet key appears
    across different expansion results.

    Args:
        all_result_sets: List of triplet lists, one per query variation.

    Returns:
        Deduplicated list of triplets sorted by score descending.
    """
    best: dict[str, dict] = {}
    for result_set in all_result_sets:
        for t in result_set:
            key = f"{t.get('subject', '')}|{t.get('predicate', '')}|{t.get('object', '')}"
            existing = best.get(key)
            if existing is None or t.get("score", 0.0) > existing.get("score", 0.0):
                best[key] = t

    fused = sorted(best.values(), key=lambda t: t.get("score", 0.0), reverse=True)
    logger.info("expansion_fusion_completed", input_sets=len(all_result_sets), output=len(fused))
    return fused


def search_with_expansion(question: str, top_k: int = 5) -> list[dict]:
    """Search with the original query and its expanded variations.

    Expands the query into variations, searches with each, and fuses
    the results. Falls back to a single search when expansion fails
    or returns no variations.

    Args:
        question: The original user query.
        top_k: Number of results per search.

    Returns:
        Deduplicated list of triplets from all searches.
    """
    variations = expand_query(question)

    queries = [question] + variations
    all_result_sets: list[list[dict]] = []

    for q in queries:
        results = search_similar_triplets(q, top_k)
        all_result_sets.append(results)

    fused = _fuse_expansion_results(all_result_sets)
    logger.info(
        "search_with_expansion_completed",
        original=question[:50],
        variations=len(variations),
        total_results=sum(len(r) for r in all_result_sets),
        fused=len(fused),
    )
    return fused


def query(question: str, top_k: int = 5, expand: bool = False) -> QueryResponse:
    """Run the full query pipeline.

    Args:
        question: The user's question.
        top_k: Number of triplets to retrieve per search.
        expand: If True, expand the query into variations and search
                with each, then fuse results. If False, use only the
                original query.

    Returns:
        QueryResponse with answer, sources, entities, and confidence.
    """
    logger.info("query_started", question=question[:50], top_k=top_k, expand=expand)

    if expand:
        vector_triplets = search_with_expansion(question, top_k)
    else:
        vector_triplets = search_similar_triplets(question, top_k)

    entity_ids = list(
        {t["subject_id"] for t in vector_triplets if t.get("subject_id")}
        | {t["object_id"] for t in vector_triplets if t.get("object_id")}
    )

    graph_triplets = traverse_graph(entity_ids, hop_depth=1)

    context, all_triplets = _fuse_context(vector_triplets, graph_triplets)

    entities_found = list(
        {t["subject"] for t in all_triplets if t.get("subject")}
        | {t["object"] for t in all_triplets if t.get("object")}
    )

    confidence = _compute_confidence(vector_triplets, len(all_triplets))
    answer = generate_answer(question, context)

    sources_by_chunk: dict[str, SourceInfo] = {}
    for t in vector_triplets:
        chunk_id = t.get("chunk_id", "unknown")
        if chunk_id not in sources_by_chunk:
            sources_by_chunk[chunk_id] = SourceInfo(
                chunk_id=chunk_id,
                document=t.get("source_doc", ""),
                triplets=[],
            )
        sources_by_chunk[chunk_id].triplets.append(
            SourceTriplet(subject=t["subject"], predicate=t["predicate"], object=t["object"])
        )

    logger.info("query_completed", answer_len=len(answer), sources=len(sources_by_chunk), confidence=confidence)
    return QueryResponse(
        answer=answer,
        sources=list(sources_by_chunk.values()),
        entities_found=entities_found,
        confidence=confidence,
    )
