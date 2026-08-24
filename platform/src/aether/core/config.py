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

    # Temporal (durable workflow engine) — the autonomous monitor loop.
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "aether-nano"

    # LLM gateway (diagnosis layer). Model in LiteLLM notation; the matching
    # provider key comes from the provider's own env var (e.g. GEMINI_API_KEY).
    llm_model: str = "gemini/gemini-3.6-flash"  # pinned; override via AETHER_LLM_MODEL
    llm_timeout_seconds: float = 30.0
    llm_max_output_tokens: int = 700
    # Hard monthly ceiling per tenant. When reached, diagnosis falls back to
    # the deterministic generator instead of silently overspending.
    llm_monthly_budget_usd_per_tenant: float = 5.0

    # Outbound email (notification service). Unconfigured (empty host) means
    # notifications are recorded with status=skipped_unconfigured, never lost
    # silently. Any SMTP provider works: SES, Resend, Mailgun, or dev Mailpit.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "alerts@aether.local"
    smtp_starttls: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
