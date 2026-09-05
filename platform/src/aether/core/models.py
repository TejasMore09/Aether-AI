"""Platform data model.

Two families of tables:

- Control plane (no tenant_id, no RLS): Tenant, User, Membership.
  The "main brain" owns these; they describe who exists and what they run.

- Tenant-scoped (tenant_id + RLS policy): AgentInstance, PolicyConfig,
  AuditLog, PendingApproval, AlertRule. These are the per-business agent's
  world. AuditLog and PendingApproval are direct ports of the governance
  design from the original prototype — that pattern (immutable audit trail +
  human approval gates on high-risk actions) is the Nano/Mega tier mechanism.
"""

import datetime
import enum
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


class Base(DeclarativeBase):
    pass


# ── Control plane ─────────────────────────────────────────────────────────────


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # ISO 4217. One currency per business, and the platform never converts —
    # see core/money.py for why an FX rate is a liability rather than a
    # feature here.
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    # A key from domains/sectors.yaml. Text rather than an enum so adding a
    # sector is a pull request against a readable file, not a migration every
    # deployment must apply in lockstep.
    sector: Mapped[str] = mapped_column(String(40), default="other")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PasswordReset(Base):
    """One issued reset token, stored as a hash.

    Not tenant-scoped: a person resetting a password has not signed in, so
    there is no tenant context to scope by. See migration 0015.
    """

    __tablename__ = "password_resets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    # SHA-256 of the token. The plaintext lives in the email and nowhere else.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    # Consumed rather than deleted: "already used" and "never existed" deserve
    # different handling, and a burst of resets is a signal worth keeping.
    used_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    requested_from: Mapped[str] = mapped_column(String(64), default="")


class ErrorEvent(Base):
    """One distinct fault, however many times it has happened.

    Keyed by fingerprint rather than by occurrence: an outage produces
    thousands of identical errors, and a row each would make the incident's
    first casualty the table meant to explain it. See migration 0016.

    Not tenant-scoped, and deliberately so — a fault spans tenants by nature.
    What protects a customer is that bodies are never captured, text is
    scrubbed, and reading it needs the engineer role (D57).
    """

    __tablename__ = "error_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    service: Mapped[str] = mapped_column(String(40))
    exception_type: Mapped[str] = mapped_column(String(200))
    # Scrubbed. core/scrub.py says what that does and does not promise.
    message: Mapped[str] = mapped_column(Text, default="")
    traceback: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(300), default="")
    occurrences: Mapped[int] = mapped_column(Integer, default=1)
    first_seen_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    last_seen_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    last_tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), default=None, nullable=True
    )
    tenants_seen: Mapped[int] = mapped_column(Integer, default=0)
    last_reference: Mapped[str] = mapped_column(String(32), default="")
    alerted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, nullable=True
    )
    # Resolving arms the alarm again: without it a fault that was fixed keeps
    # its old alert timestamp and a recurrence is folded in silently.
    resolved_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, nullable=True
    )
    resolved_by: Mapped[str] = mapped_column(String(320), default="")


class BackupRun(Base):
    """One backup attempt, and whether anyone proved it could be restored.

    `verified` is separate from `status` deliberately: producing a file and
    being able to recover from it are different claims, and folding them
    together is how "we have backups" comes to mean nothing. See migration
    0018 and D63.
    """

    __tablename__ = "backup_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, nullable=True
    )
    status: Mapped[str] = mapped_column(String(20))
    path: Mapped[str] = mapped_column(Text, default="")
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    checks: Mapped[dict] = mapped_column(JSONB, default=dict)
    detail: Mapped[str] = mapped_column(Text, default="")


class Role(enum.StrEnum):
    owner = "owner"
    operator = "operator"
    viewer = "viewer"


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "tenant_id", name="uq_membership"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    role: Mapped[Role] = mapped_column(Enum(Role, name="role"), default=Role.viewer)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ── Tenant-scoped (RLS-protected) ─────────────────────────────────────────────


class TenantScoped:
    """Mixin: every RLS-protected table carries tenant_id."""

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)


class AgentKind(enum.StrEnum):
    nano = "nano"  # monitor + diagnose + report
    mega = "mega"  # nano + approval-gated actions


class AgentInstance(Base, TenantScoped):
    __tablename__ = "agent_instances"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[AgentKind] = mapped_column(Enum(AgentKind, name="agent_kind"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PolicyConfig(Base, TenantScoped):
    """Per-tenant decision policy. Replaces the constants that were hardcoded
    in the prototype's DecisionEngine (retrain cost, impact multipliers,
    thresholds). One row per (tenant, domain)."""

    __tablename__ = "policy_configs"
    __table_args__ = (UniqueConstraint("tenant_id", "domain", name="uq_policy_domain"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain: Mapped[str] = mapped_column(String(100))
    params: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AuditLog(Base, TenantScoped):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_tenant_ts", "tenant_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    domain: Mapped[str] = mapped_column(String(100), index=True)
    action: Mapped[str] = mapped_column(String(60))
    triggered_by: Mapped[str] = mapped_column(String(320))  # user email or "agent:<id>"
    risk_level: Mapped[str] = mapped_column(String(10))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="completed")


class ApprovalStatus(enum.StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class PendingApproval(Base, TenantScoped):
    __tablename__ = "pending_approvals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    domain: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(60))
    reason: Mapped[str] = mapped_column(Text, default="")
    risk_level: Mapped[str] = mapped_column(String(10))
    expected_loss: Mapped[float] = mapped_column(Float, default=0.0)
    # Copied from the tenant rather than joined, so a decision recorded last
    # March keeps meaning what it meant last March even if the business later
    # changes currency. Same reasoning as storing the band on the observation.
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, name="approval_status"), default=ApprovalStatus.pending
    )
    resolved_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    resolved_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Grounded explanation attached by the diagnosis layer so the human
    # deciding sees *why*, not just numbers. diagnosis_source: llm | fallback.
    diagnosis: Mapped[str | None] = mapped_column(Text, nullable=True)
    diagnosis_source: Mapped[str | None] = mapped_column(String(20), nullable=True)


class Observation(Base, TenantScoped):
    """A point-in-time reading of one domain's health, pushed by a connector,
    a metrics job, or the customer's own systems. The autonomous monitor loop
    evaluates the latest observation against the tenant's policy."""

    __tablename__ = "observations"
    __table_args__ = (Index("ix_obs_tenant_domain_ts", "tenant_id", "domain", "observed_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    observed_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Insertion order, assigned by the database. observed_at is the customer's
    # fact about when a reading refers to; this is ours about when we were
    # told, and it is what settles "which of these is current" when two
    # readings claim the same moment. See migration 0014.
    seq: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    domain: Mapped[str] = mapped_column(String(100), index=True)
    drift_fraction: Mapped[float] = mapped_column(Float)
    performance: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(120), default="api")
    details: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Domain-native metric values as reported (e.g. dso_days, overdue_ratio).
    # drift_fraction and performance above are derived from these by the
    # domain pack; keeping the raw values makes every decision re-explainable.
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict)
    # accepted readings drive decisions; quarantined ones are kept visible
    # with their reasons rather than silently dropped.
    status: Mapped[str] = mapped_column(String(20), default="accepted", index=True)
    issues: Mapped[dict] = mapped_column(JSONB, default=dict)


class AlertRule(Base, TenantScoped):
    __tablename__ = "alert_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    domain: Mapped[str] = mapped_column(String(100))
    metric: Mapped[str] = mapped_column(String(60))
    threshold: Mapped[float] = mapped_column(Float)
    channel: Mapped[str] = mapped_column(String(30), default="email")
    severity: Mapped[str] = mapped_column(String(10), default="HIGH")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class LLMUsage(Base, TenantScoped):
    """Every LLM call, metered per tenant: the basis for budget enforcement
    now and usage-based pricing later."""

    __tablename__ = "llm_usage"
    __table_args__ = (Index("ix_llm_usage_tenant_ts", "tenant_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    purpose: Mapped[str] = mapped_column(String(60))  # e.g. "diagnosis"
    model: Mapped[str] = mapped_column(String(120))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)


class ApiKey(Base, TenantScoped):
    """A credential an unattended system uses to push readings.

    Only a hash is stored — the key itself is shown once at creation and is
    unrecoverable afterwards, so a database disclosure does not hand an
    attacker working credentials.

    Deliberately ingest-scoped: a leaked key can submit readings but cannot
    approve a decision, read the audit trail, or see a diagnosis. The blast
    radius of a credential that lives in someone else's cron job should be as
    small as the job's actual job.
    """

    __tablename__ = "api_keys"
    __table_args__ = (Index("ix_apikey_hash", "key_hash"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    name: Mapped[str] = mapped_column(String(120))
    # Lookup is by hash, so it is unique across the whole table rather than
    # per tenant — two tenants must never be able to hold the same secret.
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # First few characters, kept in clear so a person can tell their keys apart.
    key_prefix: Mapped[str] = mapped_column(String(20))
    created_by: Mapped[str] = mapped_column(String(320))
    last_used_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Notification(Base, TenantScoped):
    """Every outbound notification, recorded whether or not delivery worked —
    the audit trail for 'was the human told?'"""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notif_tenant_ts", "tenant_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    kind: Mapped[str] = mapped_column(String(60))  # e.g. "approval_created"
    channel: Mapped[str] = mapped_column(String(30), default="email")
    recipient: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(30))  # sent | failed | skipped_unconfigured
    detail: Mapped[str] = mapped_column(Text, default="")
    ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


# Tables protected by an RLS policy (see migrations):
class KnowledgeChunk(Base, TenantScoped):
    """One remembered thing, belonging to exactly one business.

    Every other tenant table holds numbers. This holds sentences — what the
    agent decided, what the owner did about it, how it turned out — which
    makes a cross-tenant read here a disclosure rather than a statistic. It
    carries the same RLS policy as everything else and a dedicated isolation
    test, because this is the table where a mistake would matter most.

    The embedding column is `vector(384)` and deliberately absent from this
    mapping: SQLAlchemy has no vector type, and nothing in the ORM layer needs
    one. Similarity search goes through explicit SQL, which is also where the
    tenant scoping is easiest to read.
    """

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        Index("ix_knowledge_tenant_time", "tenant_id", "occurred_at"),
        Index("ix_knowledge_source", "tenant_id", "kind", "source_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # When the thing happened, not when it was indexed. Backfilling a year of
    # history in one afternoon must not make every memory look like today.
    occurred_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    kind: Mapped[str] = mapped_column(String(40))
    domain: Mapped[str | None] = mapped_column(String(100), default=None)
    # The record this was derived from, so re-indexing updates rather than
    # accumulates. Null for chunks with no single source.
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)
    body: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)


# ── Main brain: staff, and the terms on which they may look ───────────────────
#
# Operating a fleet means someone eventually has to debug a customer's agent.
# The question is not whether staff can reach tenant data -- somebody always
# can, at the database if nowhere else -- but whether reaching it is
# deliberate, bounded, and visible to the customer afterwards. These three
# tables exist to make the honest answer "yes" rather than "trust us".


class StaffRole(enum.StrEnum):
    """What a member of staff may do. Deliberately coarse.

    observer  fleet health only -- counts, timestamps, error rates. Never the
              contents of a tenant's data.
    engineer  may additionally open a break-glass grant against one tenant,
              with a written reason.
    admin     may additionally manage staff and end anyone's grant.
    """

    observer = "observer"
    engineer = "engineer"
    admin = "admin"


class PlatformAdmin(Base):
    """A member of platform staff.

    A separate table from User, not a flag on it. A boolean would mean one
    errant UPDATE stands between a customer account and the whole fleet; a
    separate table means staff access requires a row that customer-facing code
    never writes.
    """

    __tablename__ = "platform_admins"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str] = mapped_column(String(200), default="")
    role: Mapped[StaffRole] = mapped_column(Enum(StaffRole, name="staff_role"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class GrantScope(enum.StrEnum):
    """How far a break-glass grant reaches.

    read_only is the default and covers almost every real incident: seeing
    what the agent saw is usually enough to explain what it did. operate is
    the rarer case where staff must change a policy or retire a stuck
    schedule on the customer's behalf.
    """

    read_only = "read_only"
    operate = "operate"


class BreakGlassGrant(Base):
    """Time-boxed, reason-bearing permission for one staff member to look
    inside one tenant.

    Expiry is stored rather than computed at use, so an abandoned session
    closes itself. There is no "extend" -- a longer look is a new grant with
    its own reason, which keeps the audit trail a list of decisions instead of
    one indefinite session.
    """

    __tablename__ = "break_glass_grants"
    __table_args__ = (Index("ix_grant_admin_active", "admin_id", "expires_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_admins.id", ondelete="CASCADE"), index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    # Free text, required, and shown to the customer. A reason nobody reads is
    # theatre; a reason the customer can read is a deterrent.
    reason: Mapped[str] = mapped_column(Text)
    scope: Mapped[GrantScope] = mapped_column(Enum(GrantScope, name="grant_scope"))
    granted_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    ended_by: Mapped[str] = mapped_column(String(320), default="")


class StaffAuditLog(Base):
    """Every staff action, including reads.

    Separate from the tenant audit log and never exposed to tenant APIs: it
    spans tenants, so putting it behind RLS would either leak across
    organizations or be unreadable. Reads are recorded as well as writes,
    because for a platform holding other companies' operating data, looking is
    the action that needs explaining.
    """

    __tablename__ = "staff_audit_logs"
    __table_args__ = (Index("ix_staff_audit_ts", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    admin_email: Mapped[str] = mapped_column(String(320), index=True)
    action: Mapped[str] = mapped_column(String(60))
    # Null for fleet-wide actions that name no single organization.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), default=None, index=True
    )
    grant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)


RLS_TABLES = [
    "agent_instances",
    "policy_configs",
    "audit_logs",
    "pending_approvals",
    "alert_rules",
    "observations",
    "llm_usage",
    "notifications",
    "api_keys",
    "knowledge_chunks",
]
