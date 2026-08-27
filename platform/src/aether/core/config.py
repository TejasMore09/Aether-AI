from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Values come from environment variables
    prefixed AETHER_ (or a local .env file in development)."""

    model_config = SettingsConfigDict(env_prefix="AETHER_", env_file=".env", extra="ignore")

    # The app connects as aether_app, a NON-owner role — table owners bypass
    # Row-Level Security, so connecting as the owner would silently disable
    # tenant isolation. Migrations use the owner URL (see migrations/env.py).
    database_url: str = "postgresql+psycopg://aether_app:aether_app_dev_only@localhost:5433/aether"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "dev-only-secret-do-not-deploy"
    jwt_ttl_minutes: int = 60
    jwt_algorithm: str = "HS256"

    env: str = "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()
