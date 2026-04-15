from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.core.graph import get_nebula_session
from app.core.vectorstore import get_qdrant_client
from app.models.graph_schema import SPACE_NAME
from app.models.schemas import DocumentInfo, GraphStats

router = APIRouter(prefix="/api/v1", tags=["documents"])


@router.get(
    "/documents",
    response_model=list[DocumentInfo],
    summary="List ingested documents",
    description="Returns a list of all unique documents that have been ingested, based on Qdrant payload metadata.",
)
async def list_documents():
    settings = get_settings()
    try:
        client = get_qdrant_client()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Qdrant unavailable: {e}")

    collections = client.get_collections().collections
    collection_names = [c.name for c in collections]

    if settings.qdrant_collection_name not in collection_names:
        return []

    all_points = []
    offset = None
    while True:
        results = client.scroll(
            collection_name=settings.qdrant_collection_name,
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        all_points.extend(results[0])
        if not results[1]:
            break
        offset = results[1]

    docs_by_name: dict[str, DocumentInfo] = {}
    for point in all_points:
        source = point.payload.get("source_doc", "")
        if not source:
            continue
        if source not in docs_by_name:
            docs_by_name[source] = DocumentInfo(
                id=point.id if isinstance(point.id, str) else str(point.id),
                filename=source,
                chunks_count=0,
                triplets_count=0,
            )
        docs_by_name[source].triplets_count += 1
        docs_by_name[source].chunks_count = max(
            docs_by_name[source].chunks_count,
            1,
        )

    return list(docs_by_name.values())


@router.delete(
    "/documents/{filename}",
    summary="Delete an ingested document",
    description="Removes all triplets and vectors associated with the given filename from both Qdrant and NebulaGraph.",
)
async def delete_document(filename: str):
    settings = get_settings()
    try:
        client = get_qdrant_client()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Qdrant unavailable: {e}")

    collections = client.get_collections().collections
    collection_names = [c.name for c in collections]

    if settings.qdrant_collection_name not in collection_names:
        raise HTTPException(status_code=404, detail=f"Document '{filename}' not found")

    all_points = []
    offset = None
    while True:
        results = client.scroll(
            collection_name=settings.qdrant_collection_name,
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        all_points.extend(results[0])
        if not results[1]:
            break
        offset = results[1]

    points_to_delete = [point.id for point in all_points if point.payload.get("source_doc") == filename]

    if not points_to_delete:
        raise HTTPException(status_code=404, detail=f"Document '{filename}' not found")

    entity_ids = set()
    for point in all_points:
        if point.payload.get("source_doc") == filename:
            sid = point.payload.get("subject_id", "")
            oid = point.payload.get("object_id", "")
            if sid:
                entity_ids.add(sid)
            if oid:
                entity_ids.add(oid)

    client.delete(
        collection_name=settings.qdrant_collection_name,
        points_selector=points_to_delete,
    )

    try:
        with get_nebula_session() as session:
            session.execute(f"USE {SPACE_NAME}")
            for entity_id in entity_ids:
                session.execute(f'DELETE VERTEX "{entity_id}" WITH EDGE')
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Deleted from Qdrant but failed to clean NebulaGraph: {e}",
        )

    return {
        "filename": filename,
        "vectors_deleted": len(points_to_delete),
        "entities_deleted_from_graph": len(entity_ids),
        "status": "deleted",
    }


@router.get(
    "/graph/stats",
    response_model=GraphStats,
    summary="Get knowledge graph statistics",
    description="Returns counts of entity types and edge types in NebulaGraph.",
)
async def graph_stats():
    settings = get_settings()
    try:
        with get_nebula_session() as session:
            session.execute(f"USE {SPACE_NAME}")

            count_result = session.execute("MATCH (n) RETURN count(n)")
            entity_count = 0
            if count_result.is_succeeded() and count_result.rows():
                val = count_result.rows()[0].values[0]
                entity_count = val.get_iVal() if hasattr(val, "get_iVal") else 0

            edge_count_result = session.execute("MATCH ()-[e]->() RETURN count(e)")
            relation_count = 0
            if edge_count_result.is_succeeded() and edge_count_result.rows():
                val = edge_count_result.rows()[0].values[0]
                relation_count = val.get_iVal() if hasattr(val, "get_iVal") else 0

    except Exception as e:
        raise HTTPException(status_code=503, detail=f"NebulaGraph unavailable: {e}")

    return GraphStats(
        entity_count=entity_count,
        edge_count=relation_count,
        space=settings.nebula_space,
    )
