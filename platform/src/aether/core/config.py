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

    # Staff tokens are signed with their own key, not jwt_secret. If the
    # customer-facing signing key ever leaks, the blast radius is one
    # organization's sessions -- not the ability to mint a main-brain
    # identity with reach across the whole fleet. Sharing one secret would
    # make those two failures the same failure.
    staff_jwt_secret: str = "dev-only-staff-secret-do-not-deploy"
    staff_jwt_ttl_minutes: int = 30  # shorter: staff sessions are for incidents

    # Ceiling on how long one break-glass grant can last. Not a default --
    # the requester picks a duration and this caps it. An incident that
    # outlives this needs a fresh decision, with its own written reason.
    break_glass_max_minutes: int = 240

    env: str = "dev"

    # How the platform learns a caller's address, for per-address throttling.
    #
    #   none       cannot be established; per-address throttling is off
    #   socket     the TCP peer, correct when clients reach the API directly
    #   forwarded  X-Forwarded-For, correct behind a proxy that overwrites it
    #
    # "none" is the default because it is the truth for this deployment: both
    # front ends are back-ends-for-front-ends, so every customer's login
    # arrives from one Next.js server. Believing that address would collapse
    # the whole customer base into a single bucket, where twenty bad guesses
    # by anyone locks out everyone -- an outage wearing the costume of a
    # security control. And "forwarded" must not be set without a proxy that
    # overwrites the header, or every attacker gets a fresh identity per
    # request. Both wrong settings fail worse than off.
    client_ip_source: str = "none"

    # Transactional email, for password reset (6.5) and alert delivery.
    # Empty means unconfigured, and callers must degrade rather than raise —
    # an unsendable email is not a reason to fail the request that triggered it.
    resend_api_key: str = ""
    email_from: str = ""

    # Temporal (durable workflow engine) — the autonomous monitor loop.
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "aether-nano"

    # LLM gateway (diagnosis layer). Model in LiteLLM notation; the matching
    # provider key comes from the provider's own env var (e.g. GEMINI_API_KEY).
    llm_model: str = "gemini/gemini-3.6-flash"  # pinned; override via AETHER_LLM_MODEL
    llm_timeout_seconds: float = 30.0
    # Must cover the model's internal reasoning as well as the words a person
    # reads, and on a reasoning model the first dwarfs the second. Measured on
    # gemini-3.6-flash against the real diagnosis prompt:
    #
    #   temp  cap   finish   thinking  visible chars
    #   0.2   2000  length       1920            233   <- the old settings
    #   0.2   4000  stop         2774           1519
    #   1.0   2000  length       1664           1129
    #   1.0   4000  stop         1982           1373   <- these settings
    #
    # The old cap of 700 was set for a non-reasoning model and silently
    # destroyed every explanation: nothing raised, the text was not empty, and
    # a customer read two sentences that stopped mid-number.
    llm_max_output_tokens: int = 4000

    # 1.0, which looks wrong for a factual explanation and is not. Gemini 3
    # degrades below it: the provider warns of loops and weaker reasoning, and
    # the table above measures the cost — 0.2 spends 40% more tokens thinking
    # to reach the same answer, and at a tight cap never finishes. Determinism
    # would be worth having, but it is not on offer here, and the numbers in
    # an explanation come from the prompt rather than from sampling.
    llm_temperature: float = 1.0
    # Hard monthly ceiling per tenant. When reached, diagnosis falls back to
    # the deterministic generator instead of silently overspending.
    llm_monthly_budget_usd_per_tenant: float = 5.0

    # Knowledge base embeddings. Local by design rather than by thrift: this
    # product's promise is that one business's data is unreachable from
    # another's, and routing every decision and outcome through an external
    # embedding service would put all of it through a third party. See
    # knowledge/embedding.py.
    embedding_enabled: bool = True
    embedding_model: str = "BAAI/bge-small-en-v1.5"  # 384 dimensions, matches the column

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
