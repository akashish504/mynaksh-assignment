"""All settings and feature flags, read from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# The .env file sits at the repository root (next to .env.example).
# Inside Docker there is no such file; values come from the container environment.
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    # --- Postgres ---
    # database_url: what the running app connects with (Neon's pooled string in production).
    # database_url_direct: what Alembic migrates with (Neon's direct string in production).
    database_url: str
    database_url_direct: str | None = None

    # --- Neo4j ---
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str

    # --- HTTP ---
    # Comma-separated list of allowed browser origins.
    cors_origins: str = ""

    # --- Feature flags ---
    clarify_enabled: bool = False
    use_embeddings: bool = False  # reserved, not implemented
    classifier: str = "jev"  # "jev" or "llm"
    memory_gate_enabled: bool = True

    # --- Tuning ---
    history_window: int = 6
    top_k_memories: int = 5
    router_min_confidence: float = 0.7
    area_threshold: float = 0.5
    memory_gate_threshold: float = 0.5
    recency_half_life_days: int = 90

    # --- Models ---
    primary_model: str = ""
    fallback_model: str = ""
    jev_model: str = "jev-1.13.0"

    @property
    def migration_database_url(self) -> str:
        return self.database_url_direct or self.database_url

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
