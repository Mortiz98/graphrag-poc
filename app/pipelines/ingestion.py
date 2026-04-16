"""Ingestion pipeline: document → chunks → triplets → graph + vectors."""

import json
import re
from pathlib import Path
from uuid import uuid4

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client.models import PointStruct

from app.core import logger
from app.core.embeddings import get_embeddings
from app.core.graph import get_nebula_session
from app.core.llm import get_llm
from app.core.vectorstore import ensure_collection_exists, get_qdrant_client
from app.models.graph_schema import (
    EDGE_RELATED_TO,
    SPACE_NAME,
    TAG_ENTITY,
    escape_ngql,
)
from app.models.schemas import Triplet
from app.pipelines.loaders import load_document
from app.prompts.extraction import EXTRACTION_SYSTEM_PROMPT, EXTRACTION_USER_PROMPT

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
EMBEDDING_BATCH_SIZE = 20


def chunk_documents(documents: list[Document], source_file: str) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_documents(documents)
    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk_id"] = str(uuid4())
        chunk.metadata["chunk_index"] = i
        chunk.metadata["source_file"] = source_file
    logger.info("document_chunked", source=source_file, chunks=len(chunks))
    return chunks


def extract_triplets_from_chunk(chunk: Document) -> list[Triplet]:
    llm = get_llm(temperature=0.0)
    text = chunk.page_content
    prompt = EXTRACTION_USER_PROMPT.format(text=text)
    response = llm.invoke(
        [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
    )
    content = response.content.strip()
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


def extract_triplets(chunks: list[Document]) -> list[tuple[Document, list[Triplet]]]:
    all_results = []
    for chunk in chunks:
        triplets = extract_triplets_from_chunk(chunk)
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
    return sanitized[:256]


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
                rel_escaped = escape_ngql(t.predicate)

                session.execute(
                    f"INSERT VERTEX {TAG_ENTITY} (name, type, description) VALUES "
                    f'"{sub_vid}":("{sub_name_escaped}","{sub_type_escaped}","")'
                )
                session.execute(
                    f"INSERT VERTEX {TAG_ENTITY} (name, type, description) VALUES "
                    f'"{obj_vid}":("{obj_name_escaped}","{obj_type_escaped}","")'
                )
                session.execute(
                    f"INSERT EDGE {EDGE_RELATED_TO} (relation, weight) VALUES "
                    f'"{sub_vid}"->"{obj_vid}":("{rel_escaped}",1.0)'
                )

    logger.info("triplets_stored_in_graph", count=len(vertex_id_map))
    return vertex_id_map


def store_in_vectorstore(
    triplets_by_chunk: list[tuple[Document, list[Triplet]]],
    vertex_id_map: dict[str, str],
    source_file: str,
) -> int:
    from app.config import get_settings

    settings = get_settings()
    client = get_qdrant_client()
    ensure_collection_exists(client, settings.qdrant_collection_name)
    embeddings = get_embeddings()

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
            all_payloads.append(
                {
                    "subject": t.subject,
                    "predicate": t.predicate,
                    "object": t.object,
                    "subject_id": sub_vid,
                    "object_id": obj_vid,
                    "chunk_id": chunk.metadata.get("chunk_id", ""),
                    "source_doc": source_file,
                }
            )

    if not all_texts:
        logger.warning("no_triplets_to_embed", source=source_file)
        return 0

    batch_size = EMBEDDING_BATCH_SIZE
    total_stored = 0
    for i in range(0, len(all_texts), batch_size):
        batch_texts = all_texts[i : i + batch_size]
        batch_ids = all_ids[i : i + batch_size]
        batch_payloads = all_payloads[i : i + batch_size]

        vectors = embeddings.embed_documents(batch_texts)

        points = [
            PointStruct(id=bid, vector=vec, payload=payload)
            for bid, vec, payload in zip(batch_ids, vectors, batch_payloads)
        ]
        client.upsert(collection_name=settings.qdrant_collection_name, points=points)
        total_stored += len(points)

    logger.info("triplets_stored_in_vectorstore", count=total_stored)
    return total_stored


def ingest_document(file_path: Path) -> dict:
    source_file = file_path.name
    logger.info("ingestion_started", file=source_file)

    documents = load_document(file_path)
    chunks = chunk_documents(documents, source_file)
    triplets_by_chunk = extract_triplets(chunks)

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

    vertex_id_map = store_in_graph(triplets_by_chunk, source_file)
    vector_count = store_in_vectorstore(triplets_by_chunk, vertex_id_map, source_file)

    logger.info(
        "ingestion_completed",
        file=source_file,
        chunks=len(chunks),
        triplets=total_triplets,
        vectors=vector_count,
    )
    return {
        "filename": source_file,
        "chunks_count": len(chunks),
        "triplets_count": total_triplets,
        "status": "processed",
    }
