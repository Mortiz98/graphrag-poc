from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.core import logger as app_logger
from app.core.graph import get_nebula_session
from app.core.vectorstore import (
    get_qdrant_client,
    get_unique_source_docs,
    scroll_by_source_doc,
)
from app.models.graph_schema import SPACE_NAME, escape_ngql
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

    docs_by_name = get_unique_source_docs(client, settings.qdrant_collection_name)

    return [
        DocumentInfo(
            id=info["id"],
            filename=info["filename"],
            chunks_count=len(info["chunk_ids"]),
            triplets_count=info["triplets_count"],
        )
        for info in docs_by_name.values()
    ]


@router.delete(
    "/documents/{filename}",
    summary="Delete an ingested document",
    description="Removes all triplets and vectors associated with the given filename from both Qdrant and NebulaGraph. "
    "Entities referenced by other documents are preserved.",
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

    points_to_delete = scroll_by_source_doc(client, settings.qdrant_collection_name, filename)

    if not points_to_delete:
        raise HTTPException(status_code=404, detail=f"Document '{filename}' not found")

    # Collect entity IDs from points being deleted
    entity_ids_from_doc = set()
    for point in points_to_delete:
        sid = point.payload.get("subject_id", "")
        oid = point.payload.get("object_id", "")
        if sid:
            entity_ids_from_doc.add(sid)
        if oid:
            entity_ids_from_doc.add(oid)

    # Check reference counts for each entity
    # An entity should only be deleted if ALL its references are from this document
    entities_to_delete = set()
    entities_preserved = set()

    try:
        # Paginated scroll to count references across all documents
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

        # Build reference count per entity
        entity_ref_counts = {}
        entity_ref_docs = {}

        for point in all_points:
            sid = point.payload.get("subject_id", "")
            oid = point.payload.get("object_id", "")
            source_doc = point.payload.get("source_doc", "")

            for eid in [sid, oid]:
                if eid:
                    if eid not in entity_ref_counts:
                        entity_ref_counts[eid] = 0
                        entity_ref_docs[eid] = set()
                    entity_ref_counts[eid] += 1
                    entity_ref_docs[eid].add(source_doc)

        # Determine which entities can be safely deleted
        for eid in entity_ids_from_doc:
            docs_referencing = entity_ref_docs.get(eid, set())
            # Only delete if this entity is ONLY referenced by the document being deleted
            if docs_referencing == {filename}:
                entities_to_delete.add(eid)
            else:
                entities_preserved.add(eid)

    except Exception as e:
        # If reference counting fails, fall back to safe mode (don't delete entities)
        app_logger.warning("reference_counting_failed", error=str(e), filename=filename)
        entities_to_delete = set()
        entities_preserved = entity_ids_from_doc

    # Delete vectors from Qdrant
    point_ids = [point.id for point in points_to_delete]
    client.delete(
        collection_name=settings.qdrant_collection_name,
        points_selector=point_ids,
    )

    # Delete only unreferenced entities from NebulaGraph
    deleted_entities = 0
    preserved_entities = 0

    try:
        with get_nebula_session() as session:
            session.execute(f"USE {SPACE_NAME}")
            for entity_id in entities_to_delete:
                session.execute(f'DELETE VERTEX "{escape_ngql(entity_id)}" WITH EDGE')
                deleted_entities += 1
            preserved_entities = len(entities_preserved)
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Deleted from Qdrant but failed to clean NebulaGraph: {e}",
        )

    return {
        "filename": filename,
        "vectors_deleted": len(point_ids),
        "entities_deleted_from_graph": deleted_entities,
        "entities_preserved": preserved_entities,
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
