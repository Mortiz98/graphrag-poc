import threading

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    VectorParams,
)

from app.config import get_settings
from app.core import logger

_qdrant_client: QdrantClient | None = None
_client_lock = threading.Lock()


def get_qdrant_client() -> QdrantClient:
    global _qdrant_client
    if _qdrant_client is not None:
        return _qdrant_client
    with _client_lock:
        if _qdrant_client is not None:
            return _qdrant_client
        settings = get_settings()
        _qdrant_client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            grpc_port=settings.qdrant_grpc_port,
            prefer_grpc=True,
        )
        return _qdrant_client


def reset_qdrant_client() -> None:
    global _qdrant_client
    with _client_lock:
        _qdrant_client = None


def ensure_collection_exists(client: QdrantClient, collection_name: str, vector_size: int = 768) -> None:
    collections = client.get_collections().collections
    names = [c.name for c in collections]
    if collection_name not in names:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE,
            ),
        )
        logger.info("collection_created", collection=collection_name)
    _ensure_payload_indexes(client, collection_name)


def _ensure_payload_indexes(client: QdrantClient, collection_name: str) -> None:
    index_fields = [
        "source_doc",
        "chunk_id",
        "subject_id",
        "object_id",
        "system",
        "account_id",
        "tenant_id",
        "user_id",
        "is_active",
        "fact_type",
        "memory_type",
        "product",
        "version",
        "severity",
        "channel",
    ]
    for field in index_fields:
        try:
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
            )
        except Exception as e:
            logger.warning("payload_index_create_failed", field=field, error=str(e))


def scroll_by_source_doc(
    client: QdrantClient,
    collection_name: str,
    source_doc: str,
    batch_size: int = 100,
) -> list:
    all_points = []
    offset = None
    while True:
        results = client.scroll(
            collection_name=collection_name,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
            scroll_filter=Filter(must=[FieldCondition(key="source_doc", match=MatchValue(value=source_doc))]),
        )
        all_points.extend(results[0])
        if not results[1]:
            break
        offset = results[1]
    return all_points


def get_unique_source_docs(
    client: QdrantClient,
    collection_name: str,
    batch_size: int = 100,
) -> dict[str, dict]:
    docs_by_name: dict[str, dict] = {}
    offset = None
    while True:
        results = client.scroll(
            collection_name=collection_name,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        # Process batch immediately to avoid accumulating all points in memory
        for point in results[0]:
            source = point.payload.get("source_doc", "")
            if not source:
                continue
            if source not in docs_by_name:
                docs_by_name[source] = {
                    "id": point.id if isinstance(point.id, str) else str(point.id),
                    "filename": source,
                    "triplets_count": 0,
                    "chunk_ids": set(),
                }
            docs_by_name[source]["triplets_count"] += 1
            chunk_id = point.payload.get("chunk_id", "")
            if chunk_id:
                docs_by_name[source]["chunk_ids"].add(chunk_id)

        if not results[1]:
            break
        offset = results[1]

    return docs_by_name


def check_qdrant_health() -> bool:
    try:
        client = get_qdrant_client()
        client.get_collections()
        return True
    except Exception as e:
        logger.error("qdrant_health_check_failed", error=str(e))
        return False
