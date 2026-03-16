from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    anthropic_api_key: str
    openai_api_key: str
    database_url: str

    agent_model: str = "claude-sonnet-4-6"
    guardrail_model: str = "claude-haiku-4-5-20251001"
    embedding_model: str = "text-embedding-3-small"
    embedding_dims: int = 1536

    semantic_search_limit: int = 8
    sql_result_limit: int = 20
    sql_timeout_seconds: int = 5

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
