"""All settings come from environment variables / the .env file."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://buildscope:buildscope@localhost:5432/buildscope"

    # TinyFish
    tinyfish_api_key: str = ""
    tinyfish_search_url: str = "https://api.search.tinyfish.ai"
    tinyfish_fetch_url: str = "https://api.fetch.tinyfish.ai"

    # LLM (OpenAI-compatible)
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    # Free-tier friendliness: minimum gap between LLM/embedding calls, and retries on 429/5xx
    llm_min_interval_seconds: float = 4.0
    llm_max_attempts: int = 5

    # Embeddings (fall back to the LLM key/base when blank)
    embedding_api_key: str = ""
    embedding_base_url: str = ""
    embedding_model: str = "text-embedding-3-small"

    # Limits and thresholds
    max_sources_per_run: int = 12
    max_queries_per_run: int = 5
    max_page_chars_for_llm: int = 12000
    fetch_cache_days: int = 7
    comparison_top_k: int = 5
    strong_support_min_domains: int = 3
    need_cluster_threshold: float = 0.80
    dispute_attach_threshold: float = 0.60
    link_threshold: float = 0.55
    max_stakeholder_groups: int = 4
    queries_per_group: int = 3

    prompt_version: str = "v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
