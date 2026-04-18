from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 768

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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def is_llm_configured(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def is_gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)

    def validate_api_key(self) -> None:
        if not self.is_llm_configured:
            raise ValueError("No API key configured. Add GEMINI_API_KEY to the .env file.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
