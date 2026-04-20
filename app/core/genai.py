"""Google GenAI client wrapper — single stack for LLM and embeddings."""

import os
import threading
import time
from collections.abc import Iterator

from google import genai
from google.genai import types

from app.config import get_settings

_client: genai.Client | None = None
_client_lock = threading.Lock()

EMBED_RETRY_ATTEMPTS = 5
EMBED_RETRY_BASE_DELAY = 10


def _retry_embed(func, *args, **kwargs):
    for attempt in range(EMBED_RETRY_ATTEMPTS):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if "429" in str(e) and attempt < EMBED_RETRY_ATTEMPTS - 1:
                delay = EMBED_RETRY_BASE_DELAY * (2**attempt)
                time.sleep(delay)
            else:
                raise


def get_genai_client() -> genai.Client:
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client
        settings = get_settings()
        if settings.gemini_api_key:
            os.environ.setdefault("GOOGLE_API_KEY", settings.gemini_api_key)
        _client = genai.Client()
        return _client


def generate(
    prompt: str,
    system: str = "",
    temperature: float = 0.0,
    model: str | None = None,
) -> str:
    client = get_genai_client()
    settings = get_settings()
    config = types.GenerateContentConfig(
        temperature=temperature,
    )
    if system:
        config.system_instruction = system
    response = client.models.generate_content(
        model=model or settings.gemini_model,
        contents=prompt,
        config=config,
    )
    return response.text or ""


def generate_stream(
    prompt: str,
    system: str = "",
    temperature: float = 0.0,
    model: str | None = None,
) -> Iterator[str]:
    client = get_genai_client()
    settings = get_settings()
    config = types.GenerateContentConfig(
        temperature=temperature,
    )
    if system:
        config.system_instruction = system
    for chunk in client.models.generate_content_stream(
        model=model or settings.gemini_model,
        contents=prompt,
        config=config,
    ):
        if chunk.text:
            yield chunk.text


def embed_query(
    text: str,
    model: str | None = None,
) -> list[float]:
    client = get_genai_client()
    settings = get_settings()
    response = _retry_embed(
        client.models.embed_content,
        model=model or settings.gemini_embedding_model,
        contents=[text],
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=settings.embedding_dimensions,
        ),
    )
    return response.embeddings[0].values or []


def embed_documents(
    texts: list[str],
    model: str | None = None,
) -> list[list[float]]:
    client = get_genai_client()
    settings = get_settings()
    batch_size = 20
    all_vectors: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = _retry_embed(
            client.models.embed_content,
            model=model or settings.gemini_embedding_model,
            contents=batch,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=settings.embedding_dimensions,
            ),
        )
        for emb in response.embeddings:
            all_vectors.append(emb.values or [])
    return all_vectors


def reset_genai_client() -> None:
    global _client
    with _client_lock:
        _client = None
