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

    llm_configured = bool(settings.openrouter_api_key and settings.openrouter_api_key != "your-openrouter-api-key-here")
    gemini_configured = settings.is_gemini_configured
    adk_ok = _check_adk()

    overall = qdrant_ok and nebula_ok

    return {
        "status": "healthy" if overall else "degraded",
        "services": {
            "qdrant": "ok" if qdrant_ok else "unavailable",
            "nebulagraph": "ok" if nebula_ok else "unavailable",
            "llm": "configured" if llm_configured else "not_configured",
            "gemini": "configured" if gemini_configured else "not_configured",
            "adk": "ok" if adk_ok else "unavailable",
        },
        "config": {
            "llm_model": settings.openrouter_llm_model,
            "embedding_model": settings.openrouter_embedding_model,
            "gemini_model": settings.gemini_model,
            "qdrant_collection": settings.qdrant_collection_name,
            "nebula_space": settings.nebula_space,
        },
    }
