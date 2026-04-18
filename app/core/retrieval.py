"""Structured filter-based retrieval over Qdrant triplets."""

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.core import logger

# Mapping from domain filter names to Qdrant payload field names.
FILTER_FIELD_MAP = {
    "system": "source_doc",
    "account_id": "subject_id",
    "fact_type": "predicate",
}


def search_by_filter(
    client: QdrantClient,
    collection_name: str,
    filters: dict[str, str],
    active_only: bool = True,
    batch_size: int = 100,
) -> list[dict]:
    """Scroll Qdrant points matching structured filters.

    Args:
        client: QdrantClient instance.
        collection_name: Name of the Qdrant collection.
        filters: Dict mapping filter names to values. Accepted keys are
            domain names ("system", "account_id", "fact_type") or raw
            Qdrant payload field names ("source_doc", "subject_id",
            "object_id", "predicate", "chunk_id").
        active_only: When True, exclude points whose ``status`` payload
            field equals ``"superseded"``. When False, return all matches.
        batch_size: Scroll page size.

    Returns:
        List of dicts with ``id`` and ``payload`` for each matched point.
    """
    must_conditions = []
    for key, value in filters.items():
        field = FILTER_FIELD_MAP.get(key, key)
        must_conditions.append(FieldCondition(key=field, match=MatchValue(value=value)))

    must_not_conditions = []
    if active_only:
        must_not_conditions.append(FieldCondition(key="status", match=MatchValue(value="superseded")))

    scroll_filter = Filter(must=must_conditions, must_not=must_not_conditions)

    all_points: list[dict] = []
    offset = None
    while True:
        results = client.scroll(
            collection_name=collection_name,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
            scroll_filter=scroll_filter,
        )
        for point in results[0]:
            all_points.append(
                {
                    "id": point.id if isinstance(point.id, str) else str(point.id),
                    "payload": point.payload,
                }
            )
        if not results[1]:
            break
        offset = results[1]

    logger.info(
        "search_by_filter_completed",
        filters=filters,
        active_only=active_only,
        results=len(all_points),
    )
    return all_points
