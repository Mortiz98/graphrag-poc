from fastapi import APIRouter

from app.config import get_settings
from app.core.graph import check_nebula_health
from app.core.vectorstore import check_qdrant_health

router = APIRouter(prefix="/api/v1", tags=["health"])


def _check_adk() -> bool:
    try:
        from google.adk.agents import LlmAgent  # noqa: F401

        return True
    except ImportError:
        return False


@router.get("/health")
async def health_check():
    settings = get_settings()
    qdrant_ok = await check_qdrant_health()
    nebula_ok = await check_nebula_health()

    gemini_configured = settings.is_gemini_configured
    adk_ok = _check_adk()

    overall = qdrant_ok and nebula_ok

    return {
        "status": "healthy" if overall else "degraded",
        "services": {
            "qdrant": "ok" if qdrant_ok else "unavailable",
            "nebulagraph": "ok" if nebula_ok else "unavailable",
            "llm": "configured" if gemini_configured else "not_configured",
            "adk": "ok" if adk_ok else "unavailable",
        },
        "config": {
            "llm_model": settings.gemini_model,
            "embedding_model": settings.gemini_embedding_model,
            "embedding_dimensions": settings.embedding_dimensions,
            "qdrant_collection": settings.qdrant_collection_name,
            "nebula_space": settings.nebula_space,
        },
    }
