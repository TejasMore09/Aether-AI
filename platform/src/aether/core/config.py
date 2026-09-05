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

    jwt_secret: str = "dev-only-secret-do-not-deploy"
    # The signature's own lifetime. It is no longer what bounds a session:
    # 6.7 resolves every request against the sessions table, so a token is
    # only good while its session is. Kept generous so the signature does not
    # expire under an active user, and short of the absolute session cap so a
    # leaked token is not useful for ever if the table is ever bypassed.
    jwt_ttl_minutes: int = 60 * 24 * 30

    # How long a session survives without use, and how long it can live at
    # all. Two numbers because one is always wrong: the first stops an
    # abandoned session lingering, the second stops an active one becoming
    # permanent.
    session_idle_days: int = 14
    session_absolute_days: int = 90
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

    # Where a customer's browser reaches the web app. Password reset links are
    # built from this and deliberately *not* from the incoming request: an
    # attacker who can set the Host header would otherwise choose where a
    # reset link points, and the customer would follow it.
    web_base_url: str = "http://localhost:3000"

    # Where fault alerts go (6.3). Empty means faults are still recorded and
    # still visible on the ops endpoint, but nothing pushes them at anyone —
    # which the health snapshot reports rather than leaving to be discovered.
    alert_email: str = ""

    # Where the committed reference tables live. Empty means "work it out"
    # (see domains/reference.py); the container image sets it explicitly,
    # because an installed package has no repository around it.
    reference_dir: str = ""

    # The database owner connection, used by migrations and by backups. Both
    # need what the application role deliberately lacks: the owner can alter
    # schema, and — the part that is easy to miss — the owner is not filtered
    # by row-level security. A dump taken as the application role errors,
    # exits 0, and contains not one row belonging to any tenant (D63).
    migration_database_url: str = ""

    # Where dumps are written. A Docker volume in the deployment; anywhere
    # with room in a checkout.
    backup_dir: str = "/var/lib/aether/backups"

    # How many dumps to keep. A count rather than an age, so a backup system
    # that has been broken for a month does not quietly delete the last good
    # file it made.
    backup_keep: int = 14

    # Hours between runs. One day, with the staleness alarm at two.
    backup_interval_hours: float = 24.0

    # Temporal (durable workflow engine) — the autonomous monitor loop.
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "aether-nano"

    # LLM gateway (diagnosis layer). Model in LiteLLM notation; the matching
    # provider key comes from the provider's own env var (e.g. GEMINI_API_KEY).
    llm_model: str = "gemini/gemini-3.6-flash"  # pinned; override via AETHER_LLM_MODEL

    # The provider key, passed straight to the call rather than exported into
    # the process environment: one key per configuration, no global mutation,
    # and no surprise if two providers are ever configured at once.
    #
    # Empty falls back to LiteLLM's own lookup (GEMINI_API_KEY and friends), so
    # an existing machine-level variable keeps working. Setting it here is the
    # documented way, because the alternative was a shell variable that had to
    # be remembered separately from every other secret and whose absence failed
    # silently.
    llm_api_key: str = ""
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


# Values that ship in this file so a checkout runs without configuration.
# Every one of them is catastrophic in production, and each is a single
# forgotten environment variable away from being used there.
_DEV_DEFAULTS = {
    "jwt_secret": "dev-only-secret-do-not-deploy",
    "staff_jwt_secret": "dev-only-staff-secret-do-not-deploy",
}

# Long enough that guessing is not the attack. Below this a secret is a
# password, and this one signs every session on the platform.
_MIN_SECRET_LENGTH = 32

DEVELOPMENT_ENVIRONMENTS = ("dev", "test", "local")


def problems(settings: Settings | None = None) -> tuple[list[str], list[str]]:
    """What is wrong with this configuration. Returns (fatal, warnings).

    Split on a real distinction rather than severity theatre. **Fatal** means
    the deployment is unsafe: a forged token would be accepted, or a
    credential would cross the network in the clear. **Warning** means the
    deployment works and something will not be noticed — nobody is alerted, no
    mail can be sent.

    Warnings are deliberately not fatal, and that is a judgement rather than
    laziness. A deployment check strict enough to block a launch over an
    operational gap teaches people to set `AETHER_ENV=dev` in production,
    which disables every check including the ones that matter. The strictness
    is spent where it buys safety.
    """
    settings = settings or get_settings()
    if settings.env in DEVELOPMENT_ENVIRONMENTS:
        return [], []

    fatal: list[str] = []
    warnings: list[str] = []

    for field, shipped in _DEV_DEFAULTS.items():
        value = getattr(settings, field)
        if value == shipped:
            fatal.append(f"AETHER_{field.upper()} is still the value shipped in the repository")
        elif len(value) < _MIN_SECRET_LENGTH:
            fatal.append(
                f"AETHER_{field.upper()} is {len(value)} characters; "
                f"at least {_MIN_SECRET_LENGTH} are needed"
            )

    # Sharing one secret between the customer world and the staff world would
    # make a leaked customer token a fleet-wide credential.
    if settings.jwt_secret == settings.staff_jwt_secret:
        fatal.append("AETHER_JWT_SECRET and AETHER_STAFF_JWT_SECRET must differ")

    if "aether_app_dev_only" in settings.database_url or "aether_dev_only" in settings.database_url:
        fatal.append("AETHER_DATABASE_URL still carries the development password")

    # A reset link is a credential with a short life. Sending one over http
    # puts it in every hop between the customer and us.
    if not settings.web_base_url.startswith("https://"):
        fatal.append(f"AETHER_WEB_BASE_URL must be https in {settings.env}")

    if settings.client_ip_source not in ("none", "socket", "forwarded"):
        fatal.append(f"AETHER_CLIENT_IP_SOURCE is {settings.client_ip_source!r}")

    if not settings.alert_email:
        warnings.append("AETHER_ALERT_EMAIL is unset: faults are recorded but nobody is told")
    if not (settings.resend_api_key or settings.smtp_host):
        warnings.append("no mail transport: password reset and fault alerts both go nowhere")

    return fatal, warnings


class Misconfigured(RuntimeError):
    """The process refused to start rather than run unsafely."""


def verify_deployable() -> None:
    """Refuse to start a production process on a development configuration.

    Called at import time by every service, so the failure is a container that
    will not start rather than a platform that runs and accepts forged tokens.
    Loud is the entire point: this is the class of mistake nobody notices
    until it is being exploited.
    """
    import logging

    fatal, warnings = problems()
    for warning in warnings:
        logging.getLogger(__name__).warning("configuration: %s", warning)
    if fatal:
        raise Misconfigured(
            "refusing to start with this configuration:\n  - " + "\n  - ".join(fatal)
        )
