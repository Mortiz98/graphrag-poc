"""Ingestion pipeline: document → chunks → triplets → graph + vectors."""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from qdrant_client.models import PointStruct

from app.core import logger
from app.core.genai import embed_documents, generate
from app.core.graph import get_nebula_session
from app.core.vectorstore import ensure_collection_exists, get_qdrant_client
from app.models.documents import Document
from app.models.graph_schema import (
    EDGE_DEFAULT_PROPS,
    EDGE_RELATED_TO,
    ENTITY_TYPE_TO_TAG,
    PREDICATE_TO_EDGE,
    SPACE_NAME,
    TAG_COMMITMENT,
    TAG_ENTITY,
    TAG_INSERT_PROPS,
    TAG_ISSUE,
    TAG_STAKEHOLDER,
    escape_ngql,
)
from app.models.schemas import CaseMetadata, FactMetadata, Triplet
from app.pipelines.consolidation import classify_memory, run_consolidation_pipeline
from app.pipelines.loaders import load_document
from app.pipelines.text_splitter import split_documents
from app.prompts.extraction import (
    EXTRACTION_SYSTEM_PROMPT,
    EXTRACTION_USER_PROMPT,
    SUPPORT_EXTRACTION_SYSTEM_PROMPT,
    SUPPORT_EXTRACTION_USER_PROMPT,
)

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
EMBEDDING_BATCH_SIZE = 20


def chunk_documents(documents: list[Document], source_file: str) -> list[Document]:
    chunks = split_documents(documents, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk_id"] = str(uuid4())
        chunk.metadata["chunk_index"] = i
        chunk.metadata["source_file"] = source_file
    logger.info("document_chunked", source=source_file, chunks=len(chunks))
    return chunks


def extract_triplets_from_chunk(
    chunk: Document,
    system: str = "support",
) -> list[Triplet]:
    text = chunk.page_content
    if system == "support":
        system_prompt = SUPPORT_EXTRACTION_SYSTEM_PROMPT
        user_prompt = SUPPORT_EXTRACTION_USER_PROMPT.format(text=text)
    else:
        system_prompt = EXTRACTION_SYSTEM_PROMPT
        user_prompt = EXTRACTION_USER_PROMPT.format(text=text)
    content = generate(prompt=user_prompt, system=system_prompt, temperature=0.0).strip()
    json_match = re.search(r"\[.*\]", content, re.DOTALL)
    if not json_match:
        logger.warning("no_json_array_found_in_llm_response", chunk_id=chunk.metadata.get("chunk_id"))
        return []
    try:
        raw = json.loads(json_match.group())
        triplets = []
        for item in raw:
            try:
                triplets.append(Triplet(**item))
            except Exception:
                logger.warning("invalid_triplet_skipped", item=item)
                continue
        return triplets
    except json.JSONDecodeError:
        logger.warning("json_decode_error_in_extraction", chunk_id=chunk.metadata.get("chunk_id"))
        return []


def extract_triplets(chunks: list[Document], system: str = "support") -> list[tuple[Document, list[Triplet]]]:
    all_results = []
    for chunk in chunks:
        triplets = extract_triplets_from_chunk(chunk, system=system)
        all_results.append((chunk, triplets))
        logger.info(
            "chunk_extracted",
            chunk_id=chunk.metadata.get("chunk_id"),
            triplets=len(triplets),
        )
    return all_results


def _sanitize_vertex_id(name: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", name.strip())
    sanitized = sanitized.strip("_")
    if not sanitized or sanitized.isspace():
        return f"entity_{uuid4().hex[:8]}"
    suffix = hashlib.md5(name.encode()).hexdigest()[:8]
    return f"{sanitized[:247]}_{suffix}"


def _build_vertex_insert(vid: str, tag: str, name: str, entity_type: str) -> str:
    props = TAG_INSERT_PROPS.get(tag, TAG_INSERT_PROPS[TAG_ENTITY])
    if tag == TAG_ISSUE:
        vals = ',"'.join([name, "", "", "", "", "", ""])
        return f'INSERT VERTEX {tag} ({",".join(props)}) VALUES "{vid}":("{vals}")'
    if tag == TAG_STAKEHOLDER:
        vals = '","'.join([name, "", "", "", ""])
        return f'INSERT VERTEX {tag} ({",".join(props)}) VALUES "{vid}":("{vals}")'
    if tag == TAG_COMMITMENT:
        vals = '","'.join([name, "", "", "", ""])
        return f'INSERT VERTEX {tag} ({",".join(props)}) VALUES "{vid}":("{vals}")'
    vals = '","'.join([name, entity_type, ""])
    return f'INSERT VERTEX {tag} ({",".join(props)}) VALUES "{vid}":("{vals}")'


def _build_edge_insert(src_vid: str, dst_vid: str, edge_name: str, predicate: str) -> str:
    if edge_name == EDGE_RELATED_TO:
        rel_escaped = escape_ngql(predicate)
        return f'INSERT EDGE {edge_name} (relation, weight) VALUES "{src_vid}"->"{dst_vid}":("{rel_escaped}",1.0)'
    prop_names = EDGE_DEFAULT_PROPS.get(edge_name)
    if not prop_names:
        return (
            f"INSERT EDGE {EDGE_RELATED_TO} (relation, weight) VALUES "
            f'"{src_vid}"->"{dst_vid}":("{escape_ngql(predicate)}",1.0)'
        )
    placeholders = ",".join(['""' for _ in prop_names])
    return f'INSERT EDGE {edge_name} ({",".join(prop_names)}) VALUES "{src_vid}"->"{dst_vid}":({placeholders})'


def store_in_graph(
    triplets_by_chunk: list[tuple[Document, list[Triplet]]],
    source_file: str,
) -> dict[str, str]:
    vertex_id_map: dict[str, str] = {}

    with get_nebula_session() as session:
        session.execute(f"USE {SPACE_NAME}")

        for chunk, triplets in triplets_by_chunk:
            for t in triplets:
                sub_vid = _sanitize_vertex_id(t.subject)
                obj_vid = _sanitize_vertex_id(t.object)

                vertex_id_map[t.subject] = sub_vid
                vertex_id_map[t.object] = obj_vid

                sub_name_escaped = escape_ngql(t.subject)
                obj_name_escaped = escape_ngql(t.object)
                sub_type_escaped = escape_ngql(t.subject_type)
                obj_type_escaped = escape_ngql(t.object_type)

                sub_tag = ENTITY_TYPE_TO_TAG.get(t.subject_type, TAG_ENTITY)
                obj_tag = ENTITY_TYPE_TO_TAG.get(t.object_type, TAG_ENTITY)

                sub_stmt = _build_vertex_insert(sub_vid, sub_tag, sub_name_escaped, sub_type_escaped)
                result = session.execute(sub_stmt)
                if not result.is_succeeded() and sub_tag != TAG_ENTITY:
                    fallback = _build_vertex_insert(sub_vid, TAG_ENTITY, sub_name_escaped, sub_type_escaped)
                    session.execute(fallback)

                obj_stmt = _build_vertex_insert(obj_vid, obj_tag, obj_name_escaped, obj_type_escaped)
                result = session.execute(obj_stmt)
                if not result.is_succeeded() and obj_tag != TAG_ENTITY:
                    fallback = _build_vertex_insert(obj_vid, TAG_ENTITY, obj_name_escaped, obj_type_escaped)
                    session.execute(fallback)

                edge_name = PREDICATE_TO_EDGE.get(t.predicate, EDGE_RELATED_TO)
                edge_stmt = _build_edge_insert(sub_vid, obj_vid, edge_name, t.predicate)
                result = session.execute(edge_stmt)
                if not result.is_succeeded() and edge_name != EDGE_RELATED_TO:
                    fallback = _build_edge_insert(sub_vid, obj_vid, EDGE_RELATED_TO, t.predicate)
                    session.execute(fallback)

    logger.info("triplets_stored_in_graph", count=len(vertex_id_map))
    return vertex_id_map


def store_in_vectorstore(
    triplets_by_chunk: list[tuple[Document, list[Triplet]]],
    vertex_id_map: dict[str, str],
    source_file: str,
    system: str = "support",
    case_metadata: CaseMetadata | None = None,
    fact_metadata: FactMetadata | None = None,
) -> int:
    from app.config import get_settings

    settings = get_settings()
    client = get_qdrant_client()
    ensure_collection_exists(client, settings.qdrant_collection_name)

    batch_timestamp = datetime.now(timezone.utc).isoformat()
    ingestion_batch_id = str(uuid4())[:8]

    case_meta_dict = case_metadata.model_dump(exclude_none=True) if case_metadata else {}
    fact_meta_dict = fact_metadata.model_dump(exclude_none=True) if fact_metadata else {}

    all_texts = []
    all_payloads = []
    all_ids = []

    for chunk, triplets in triplets_by_chunk:
        for t in triplets:
            triplet_text = f"{t.subject} {t.predicate} {t.object}"
            sub_vid = vertex_id_map.get(t.subject, _sanitize_vertex_id(t.subject))
            obj_vid = vertex_id_map.get(t.object, _sanitize_vertex_id(t.object))

            point_id = str(uuid4())
            all_ids.append(point_id)
            all_texts.append(triplet_text)
            payload = {
                "subject": t.subject,
                "predicate": t.predicate,
                "object": t.object,
                "subject_id": sub_vid,
                "object_id": obj_vid,
                "subject_type": t.subject_type,
                "object_type": t.object_type,
                "chunk_id": chunk.metadata.get("chunk_id", ""),
                "chunk_index": chunk.metadata.get("chunk_index", 0),
                "source_doc": source_file,
                "created_at": batch_timestamp,
                "ingestion_batch": ingestion_batch_id,
                "system": system,
                "is_active": True,
                "memory_type": classify_memory(fact_meta_dict.get("fact_type"), system),
            }
            if fact_meta_dict.get("account_id"):
                payload["account_id"] = fact_meta_dict["account_id"]
            if fact_meta_dict.get("tenant_id"):
                payload["tenant_id"] = fact_meta_dict["tenant_id"]
            if fact_meta_dict.get("user_id"):
                payload["user_id"] = fact_meta_dict["user_id"]
            payload.update(case_meta_dict)
            payload.update(fact_meta_dict)
            all_payloads.append(payload)

    if not all_texts:
        logger.warning("no_triplets_to_embed", source=source_file)
        return 0

    batch_size = EMBEDDING_BATCH_SIZE
    total_stored = 0
    for i in range(0, len(all_texts), batch_size):
        batch_texts = all_texts[i : i + batch_size]
        batch_ids = all_ids[i : i + batch_size]
        batch_payloads = all_payloads[i : i + batch_size]

        vectors = embed_documents(batch_texts)

        points = [
            PointStruct(id=bid, vector=vec, payload=payload)
            for bid, vec, payload in zip(batch_ids, vectors, batch_payloads)
        ]
        client.upsert(collection_name=settings.qdrant_collection_name, points=points)
        total_stored += len(points)

    logger.info("triplets_stored_in_vectorstore", count=total_stored)
    return total_stored


def ingest_document(
    file_path: Path,
    system: str = "support",
    case_metadata: CaseMetadata | None = None,
    fact_metadata: FactMetadata | None = None,
) -> dict:
    source_file = file_path.name
    logger.info("ingestion_started", file=source_file, system=system)

    documents = load_document(file_path)
    chunks = chunk_documents(documents, source_file)
    triplets_by_chunk = extract_triplets(chunks, system=system)

    total_triplets = sum(len(t) for _, t in triplets_by_chunk)
    logger.info("triplets_extracted", total=total_triplets)

    if total_triplets == 0:
        logger.warning("no_triplets_extracted", file=source_file)
        return {
            "filename": source_file,
            "chunks_count": len(chunks),
            "triplets_count": 0,
            "status": "no_triplets",
        }

    consolidated = run_consolidation_pipeline(
        [
            {"subject": t.subject, "predicate": t.predicate, "object": t.object}
            for _, ts in triplets_by_chunk
            for t in ts
        ],
        system=system,
        source_doc=source_file,
        case_metadata=case_metadata,
        fact_metadata=fact_metadata,
    )
    logger.info("consolidation_applied", input=total_triplets, output=len(consolidated))

    surviving_keys = {
        f"{c.get('subject', '')}|{c.get('predicate', '')}|{c.get('object', '')}".lower() for c in consolidated
    }
    consolidated_triplets_by_chunk = []
    for chunk, triplets in triplets_by_chunk:
        filtered = [t for t in triplets if f"{t.subject}|{t.predicate}|{t.object}".lower() in surviving_keys]
        if filtered:
            consolidated_triplets_by_chunk.append((chunk, filtered))

    deduped_count = sum(len(ts) for _, ts in consolidated_triplets_by_chunk)
    logger.info("dedup_applied", original=total_triplets, deduped=deduped_count)

    vertex_id_map = store_in_graph(consolidated_triplets_by_chunk, source_file)
    vector_count = store_in_vectorstore(
        consolidated_triplets_by_chunk,
        vertex_id_map,
        source_file,
        system=system,
        case_metadata=case_metadata,
        fact_metadata=fact_metadata,
    )

    logger.info(
        "ingestion_completed",
        file=source_file,
        chunks=len(chunks),
        triplets=total_triplets,
        vectors=vector_count,
        system=system,
    )
    return {
        "filename": source_file,
        "chunks_count": len(chunks),
        "triplets_count": total_triplets,
        "status": "processed",
    }
