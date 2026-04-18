from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    Modifier,
    PayloadSchemaType,
    SparseVectorParams,
    VectorParams,
)

from app.config import get_settings
from app.core import logger

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"


def get_qdrant_client() -> QdrantClient:
    settings = get_settings()
    return QdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        grpc_port=settings.qdrant_grpc_port,
        prefer_grpc=True,
    )


def _collection_has_sparse_vectors(client: QdrantClient, collection_name: str) -> bool:
    """Check if a collection already has sparse vectors configured."""
    try:
        info = client.get_collection(collection_name)
        return info.config.params.sparse_vectors is not None and len(info.config.params.sparse_vectors) > 0
    except Exception:
        return False


def _migrate_collection_to_sparse(client: QdrantClient, collection_name: str, vector_size: int) -> None:
    """Migrate a collection to support sparse vectors by recreating it.

    This deletes the existing collection and recreates it with both
    dense and sparse named vectors. Existing data is lost.
    """
    logger.warning("migrating_collection_to_sparse", collection=collection_name)
    client.delete_collection(collection_name)
    _create_collection_with_sparse(client, collection_name, vector_size)
    logger.info("collection_migrated", collection=collection_name)


def _create_collection_with_sparse(client: QdrantClient, collection_name: str, vector_size: int) -> None:
    """Create a new collection with both dense and sparse named vectors."""
    client.create_collection(
        collection_name=collection_name,
        vectors_config={
            DENSE_VECTOR_NAME: VectorParams(
                size=vector_size,
                distance=Distance.COSINE,
            ),
        },
        sparse_vectors_config={
            SPARSE_VECTOR_NAME: SparseVectorParams(
                modifier=Modifier.IDF,
            ),
        },
    )
    logger.info("collection_created_with_sparse", collection=collection_name)


def ensure_collection_exists(client: QdrantClient, collection_name: str, vector_size: int = 1536) -> None:
    collections = client.get_collections().collections
    names = [c.name for c in collections]
    if collection_name not in names:
        _create_collection_with_sparse(client, collection_name, vector_size)
    elif not _collection_has_sparse_vectors(client, collection_name):
        _migrate_collection_to_sparse(client, collection_name, vector_size)
    _ensure_payload_indexes(client, collection_name)


def _ensure_payload_indexes(client: QdrantClient, collection_name: str) -> None:
    index_fields = ["source_doc", "chunk_id", "subject_id", "object_id"]
    for field in index_fields:
        try:
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
            )
        except Exception:
            pass


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


async def check_qdrant_health() -> bool:
    try:
        client = get_qdrant_client()
        client.get_collections()
        return True
    except Exception as e:
        logger.error("qdrant_health_check_failed", error=str(e))
        return False
