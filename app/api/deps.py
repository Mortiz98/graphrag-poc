from app.config import get_settings
from app.core.embeddings import get_embeddings
from app.core.graph import get_nebula_session
from app.core.llm import get_llm
from app.core.vectorstore import ensure_collection_exists, get_qdrant_client


async def get_llm_client():
    return get_llm()


async def get_embedding_client():
    return get_embeddings()


async def get_qdrant():
    settings = get_settings()
    client = get_qdrant_client()
    ensure_collection_exists(client, settings.qdrant_collection_name)
    return client


async def get_nebula():
    return get_nebula_session
