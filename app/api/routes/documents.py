from fastapi import APIRouter

from app.core.vectorstore import get_qdrant_client

router = APIRouter(prefix="/api/v1", tags=["documents"])


@router.get("/documents")
async def list_documents():
    client = get_qdrant_client()
    from app.config import get_settings

    settings = get_settings()
    collections = client.get_collections().collections
    collection_names = [c.name for c in collections]

    if settings.qdrant_collection_name not in collection_names:
        return {"documents": []}

    scroll_result = client.scroll(
        collection_name=settings.qdrant_collection_name,
        limit=0,
    )
    return {"documents": [], "total_points": scroll_result[1].count if hasattr(scroll_result[1], "count") else 0}


@router.get("/graph/stats")
async def graph_stats():
    from app.config import get_settings
    from app.core.graph import get_nebula_session
    from app.models.graph_schema import SPACE_NAME

    settings = get_settings()

    with get_nebula_session() as session:
        session.execute(f"USE {SPACE_NAME}")
        tags_result = session.execute("SHOW TAGS")
        edges_result = session.execute("SHOW EDGES")

        tag_count = len(tags_result.rows()) if tags_result.is_succeeded() else 0
        edge_count = len(edges_result.rows()) if edges_result.is_succeeded() else 0

    return {
        "space": settings.nebula_space,
        "tag_types": tag_count,
        "edge_types": edge_count,
    }
