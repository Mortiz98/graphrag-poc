from langchain_openai import ChatOpenAI

from app.config import get_settings


def get_llm(temperature: float = 0.0, streaming: bool = False) -> ChatOpenAI:
    settings = get_settings()
    settings.validate_api_key()
    return ChatOpenAI(
        model=settings.openrouter_llm_model,
        openai_api_key=settings.openrouter_api_key,
        openai_api_base=settings.openrouter_base_url,
        temperature=temperature,
        streaming=streaming,
    )
