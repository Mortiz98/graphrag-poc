from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_llm_model: str = "openai/gpt-4o-mini"
    openrouter_embedding_model: str = "openai/text-embedding-3-small"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "gemini-embedding-exp-03-07"

    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_grpc_port: int = 6334
    qdrant_collection_name: str = "triplets"

    nebula_host: str = "localhost"
    nebula_port: int = 9669
    nebula_user: str = "root"
    nebula_password: str = "nebula"
    nebula_space: str = "graphrag"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def is_llm_configured(self) -> bool:
        return bool(
            (self.openrouter_api_key and self.openrouter_api_key != "your-openrouter-api-key-here")
            or self.gemini_api_key
        )

    @property
    def is_gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)

    def validate_api_key(self) -> None:
        if not self.is_llm_configured:
            raise ValueError("No API key configured. Add OPENROUTER_API_KEY or GEMINI_API_KEY to the .env file.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
