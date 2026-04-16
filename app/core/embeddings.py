from langchain_openai import OpenAIEmbeddings

from app.config import get_settings


def get_embeddings() -> OpenAIEmbeddings:
    settings = get_settings()
    settings.validate_api_key()
    return OpenAIEmbeddings(
        model=settings.openrouter_embedding_model,
        openai_api_key=settings.openrouter_api_key,
        openai_api_base=settings.openrouter_base_url,
    )
