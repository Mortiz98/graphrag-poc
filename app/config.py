from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_llm_model: str = "openai/gpt-4o-mini"
    openrouter_embedding_model: str = "openai/text-embedding-3-small"

    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_grpc_port: int = 6334
    qdrant_collection_name: str = "triplets"

    nebula_host: str = "localhost"
    nebula_port: int = 9669
    nebula_user: str = "root"
    nebula_password: str = "nebula"
    nebula_space: str = "graphrag"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def is_gemini_configured(self) -> bool:
        """Check if Gemini API key is configured."""
        return bool(self.gemini_api_key)

    @property
    def is_llm_configured(self) -> bool:
        """Check if the API key is properly configured."""
        return bool(self.openrouter_api_key and self.openrouter_api_key != "your-openrouter-api-key-here")

    def validate_api_key(self) -> None:
        """Validate API key configuration and raise clear error if missing."""
        if not self.is_llm_configured:
            raise ValueError(
                "OPENROUTER_API_KEY not configured. "
                "Add your API key to the .env file. "
                "Get one at https://openrouter.ai/keys"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
