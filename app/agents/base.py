import os

from app.config import get_settings


def get_adk_model() -> str:
    settings = get_settings()
    if settings.gemini_api_key:
        os.environ.setdefault("GOOGLE_API_KEY", settings.gemini_api_key)
    return settings.gemini_model


def get_adk_embedding_model() -> str:
    settings = get_settings()
    if settings.gemini_api_key:
        os.environ.setdefault("GOOGLE_API_KEY", settings.gemini_api_key)
    return settings.gemini_embedding_model
