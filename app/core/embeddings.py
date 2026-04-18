"""Embeddings adapter — replaces langchain_openai.OpenAIEmbeddings with Google GenAI."""

from __future__ import annotations

from app.core.genai import embed_documents, embed_query


class Embeddings:
    def embed_query(self, text: str) -> list[float]:
        return embed_query(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return embed_documents(texts)


def get_embeddings() -> Embeddings:
    from app.config import get_settings

    settings = get_settings()
    settings.validate_api_key()
    return Embeddings()
