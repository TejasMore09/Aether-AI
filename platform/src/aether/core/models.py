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
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
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


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


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
    expected_loss_usd: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, name="approval_status"), default=ApprovalStatus.pending
    )
    resolved_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    resolved_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


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


# Tables that get an RLS policy in the initial migration:
RLS_TABLES = [
    "agent_instances",
    "policy_configs",
    "audit_logs",
    "pending_approvals",
    "alert_rules",
]
