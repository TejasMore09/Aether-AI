"""The main brain's staff layer: fleet visibility, and break-glass access.

The product promises tenants that their data is theirs. Operating a fleet
means that promise has to survive contact with an on-call engineer at 3am who
needs to explain why one customer's agent stopped deciding. This module is the
shape of that compromise:

  - Staff see fleet *health* freely -- counts, timestamps, error rates, spend.
    That is metadata about the platform's own operation, and reading it needs
    no ceremony.

  - Staff see the *contents* of a tenant only under a break-glass grant: a
    named person, one named organization, a written reason, a hard expiry, and
    an entry in that organization's own audit log so the customer can see it
    happened without asking.

  - Every staff action, reads included, lands in an append-only trail the
    application cannot rewrite.

Staff identity is deliberately a different token type from a tenant user's,
signed with a different key and carrying a different issuer, so neither can be
presented where the other is expected -- see verify_staff_token.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass

import bcrypt
import jwt
from sqlalchemy import desc, select, text

from aether.core.config import get_settings
from aether.core.db import session as plain_session
from aether.core.db import tenant_session
from aether.core.models import (
    AuditLog,
    BreakGlassGrant,
    GrantScope,
    PlatformAdmin,
    StaffAuditLog,
    StaffRole,
    Tenant,
)

STAFF_ISSUER = "aether-main-brain"

_ROLE_ORDER = {StaffRole.observer: 0, StaffRole.engineer: 1, StaffRole.admin: 2}


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


# ── Identity ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class StaffPrincipal:
    admin_id: uuid.UUID
    email: str
    role: StaffRole


class StaffTokenError(Exception):
    pass


def issue_staff_token(admin: PlatformAdmin) -> str:
    s = get_settings()
    now = utcnow()
    payload = {
        "sub": str(admin.id),
        "email": admin.email,
        "role": admin.role.value,
        "iat": now,
        "exp": now + datetime.timedelta(minutes=s.staff_jwt_ttl_minutes),
        "iss": STAFF_ISSUER,
    }
    return jwt.encode(payload, s.staff_jwt_secret, algorithm=s.jwt_algorithm)


def verify_staff_token(token: str) -> StaffPrincipal:
    """Verify a staff token.

    Both the key and the issuer differ from the tenant-facing token, so a
    customer's JWT cannot be replayed here and a staff JWT cannot be replayed
    at a tenant endpoint. Two independent mismatches rather than one, because
    this is the boundary where a single mistake would be worst.
    """
    s = get_settings()
    try:
        payload = jwt.decode(
            token,
            s.staff_jwt_secret,
            algorithms=[s.jwt_algorithm],
            issuer=STAFF_ISSUER,
        )
    except jwt.PyJWTError as exc:
        raise StaffTokenError(str(exc)) from exc
    try:
        return StaffPrincipal(
            admin_id=uuid.UUID(payload["sub"]),
            email=payload["email"],
            role=StaffRole(payload["role"]),
        )
    except (KeyError, ValueError) as exc:
        raise StaffTokenError(f"malformed claims: {exc}") from exc


def authenticate_staff(email: str, password: str) -> PlatformAdmin | None:
    with plain_session() as db:
        admin = db.scalar(
            select(PlatformAdmin).where(
                PlatformAdmin.email == email.lower(), PlatformAdmin.is_active
            )
        )
        if admin is None:
            # Hash anyway so a missing account and a wrong password take the
            # same time. Otherwise this endpoint enumerates staff emails.
            bcrypt.checkpw(password.encode(), bcrypt.gensalt())
            return None
        if not bcrypt.checkpw(password.encode(), admin.password_hash.encode()):
            return None
        db.expunge(admin)
        return admin


def has_role(principal: StaffPrincipal, minimum: StaffRole) -> bool:
    return _ROLE_ORDER[principal.role] >= _ROLE_ORDER[minimum]


def create_admin(
    email: str, password: str, role: StaffRole, display_name: str = ""
) -> PlatformAdmin:
    with plain_session() as db:
        admin = PlatformAdmin(
            email=email.lower(),
            password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
            display_name=display_name,
            role=role,
        )
        db.add(admin)
        db.flush()
        db.expunge(admin)
        return admin


# ── The staff trail ───────────────────────────────────────────────────────────


def record(
    admin_email: str,
    action: str,
    *,
    tenant_id: uuid.UUID | None = None,
    grant_id: uuid.UUID | None = None,
    details: dict | None = None,
) -> None:
    """Append to the staff trail. Never raises for the caller's benefit --
    if this fails the action should fail too, which is why it is not wrapped."""
    with plain_session() as db:
        db.add(
            StaffAuditLog(
                admin_email=admin_email,
                action=action,
                tenant_id=tenant_id,
                grant_id=grant_id,
                details=details or {},
            )
        )


def read_staff_trail(limit: int = 100, tenant_id: uuid.UUID | None = None) -> list[dict]:
    with plain_session() as db:
        q = select(StaffAuditLog).order_by(desc(StaffAuditLog.created_at)).limit(limit)
        if tenant_id is not None:
            q = q.where(StaffAuditLog.tenant_id == tenant_id)
        return [
            {
                "id": str(r.id),
                "created_at": r.created_at.isoformat(),
                "admin_email": r.admin_email,
                "action": r.action,
                "tenant_id": str(r.tenant_id) if r.tenant_id else None,
                "grant_id": str(r.grant_id) if r.grant_id else None,
                "details": r.details,
            }
            for r in db.scalars(q)
        ]


# ── Fleet health ──────────────────────────────────────────────────────────────

_FLEET_COLUMNS = (
    "tenant_id, name, slug, is_active, created_at, active_agents, observation_count, "
    "quarantined_count, last_observation_at, pending_approvals, configured_domains, "
    "active_keys, month_spend_usd, failed_notifications, "
    "knowledge_chunks, last_knowledge_at, unindexed_decisions"
)


def fleet_health() -> list[dict]:
    """Aggregate health for every tenant.

    Reads the fleet_health view, which exposes counts and timestamps and no
    tenant content whatsoever. The restriction is the view's, not this
    function's: there is no argument to this call that would return a metric
    value, because the view does not select one.

    That holds for what an agent remembers too. Staff see how many memories a
    knowledge base holds, when it last gained one, and how many resolved
    decisions were never indexed — enough to spot a broken pipeline that would
    otherwise show up only as explanations quietly ceasing to mention the
    past. Reading a memory is a break-glass matter, like every other piece of
    a customer's data.
    """
    with plain_session() as db:
        rows = db.execute(
            text(f"SELECT {_FLEET_COLUMNS} FROM fleet_health ORDER BY name")
        ).mappings()
        return [
            {
                "tenant_id": str(r["tenant_id"]),
                "name": r["name"],
                "slug": r["slug"],
                "is_active": r["is_active"],
                "created_at": r["created_at"].isoformat(),
                "active_agents": int(r["active_agents"]),
                "observation_count": int(r["observation_count"]),
                "quarantined_count": int(r["quarantined_count"]),
                "last_observation_at": (
                    r["last_observation_at"].isoformat() if r["last_observation_at"] else None
                ),
                "pending_approvals": int(r["pending_approvals"]),
                "configured_domains": int(r["configured_domains"]),
                "active_keys": int(r["active_keys"]),
                "month_spend_usd": float(r["month_spend_usd"]),
                "failed_notifications": int(r["failed_notifications"]),
                "knowledge_chunks": int(r["knowledge_chunks"]),
                "last_knowledge_at": (
                    r["last_knowledge_at"].isoformat() if r["last_knowledge_at"] else None
                ),
                "unindexed_decisions": int(r["unindexed_decisions"]),
            }
            for r in rows
        ]


# ── Break-glass ───────────────────────────────────────────────────────────────

MIN_REASON_LENGTH = 12


class GrantError(Exception):
    pass


def open_grant(
    principal: StaffPrincipal,
    tenant_id: uuid.UUID,
    reason: str,
    scope: GrantScope,
    minutes: int,
) -> BreakGlassGrant:
    """Open a break-glass grant, and tell the customer it happened.

    The write into the tenant's own audit log is the part that matters. A
    staff-only trail asks the customer to trust that we police ourselves; an
    entry in the log they already read means staff access shows up beside
    their agent's own decisions, unprompted.
    """
    settings = get_settings()
    reason = reason.strip()
    if len(reason) < MIN_REASON_LENGTH:
        raise GrantError(
            f"Give a real reason ({MIN_REASON_LENGTH} characters or more) — "
            "the customer will read it."
        )
    if minutes < 1 or minutes > settings.break_glass_max_minutes:
        raise GrantError(f"Duration must be 1–{settings.break_glass_max_minutes} minutes.")
    if not has_role(principal, StaffRole.engineer):
        raise GrantError("Your staff role cannot open a break-glass grant.")

    with plain_session() as db:
        tenant = db.get(Tenant, tenant_id)
        if tenant is None:
            raise GrantError("No such organization.")
        grant = BreakGlassGrant(
            admin_id=principal.admin_id,
            tenant_id=tenant_id,
            reason=reason,
            scope=scope,
            expires_at=utcnow() + datetime.timedelta(minutes=minutes),
        )
        db.add(grant)
        db.flush()
        db.expunge(grant)

    record(
        principal.email,
        "break_glass.open",
        tenant_id=tenant_id,
        grant_id=grant.id,
        details={"reason": reason, "scope": scope.value, "minutes": minutes},
    )

    with tenant_session(tenant_id) as db:
        db.add(
            AuditLog(
                tenant_id=tenant_id,
                domain="platform",
                action="support_access_opened",
                triggered_by=f"staff:{principal.email}",
                risk_level="HIGH",
                status="completed",
                details={
                    # Carried so the customer's own view can pair this with the
                    # matching close, and show a finished visit as finished
                    # rather than leaving it reading "open" until it expires.
                    "grant_id": str(grant.id),
                    "reason": reason,
                    "scope": scope.value,
                    "expires_at": grant.expires_at.isoformat(),
                    "note": (
                        "A member of Aether platform staff opened time-limited access "
                        "to your organization. It ends automatically at the time above."
                    ),
                },
            )
        )
    return grant


def active_grant(admin_id: uuid.UUID, tenant_id: uuid.UUID) -> BreakGlassGrant | None:
    """The caller's live grant for this tenant, if any.

    Expiry is checked here rather than by a sweeper, so a grant stops working
    the moment it lapses even if nothing has run to tidy it up.
    """
    with plain_session() as db:
        grant = db.scalar(
            select(BreakGlassGrant)
            .where(
                BreakGlassGrant.admin_id == admin_id,
                BreakGlassGrant.tenant_id == tenant_id,
                BreakGlassGrant.ended_at.is_(None),
                BreakGlassGrant.expires_at > utcnow(),
            )
            .order_by(desc(BreakGlassGrant.granted_at))
        )
        if grant is not None:
            db.expunge(grant)
        return grant


def end_grant(principal: StaffPrincipal, grant_id: uuid.UUID) -> bool:
    """End a grant early. An admin may end anyone's; others only their own."""
    with plain_session() as db:
        grant = db.get(BreakGlassGrant, grant_id)
        if grant is None or grant.ended_at is not None:
            return False
        if grant.admin_id != principal.admin_id and not has_role(principal, StaffRole.admin):
            raise GrantError("Only an admin can end someone else's grant.")
        grant.ended_at = utcnow()
        grant.ended_by = principal.email
        tenant_id = grant.tenant_id

    record(principal.email, "break_glass.close", tenant_id=tenant_id, grant_id=grant_id)

    with tenant_session(tenant_id) as db:
        db.add(
            AuditLog(
                tenant_id=tenant_id,
                domain="platform",
                action="support_access_closed",
                triggered_by=f"staff:{principal.email}",
                risk_level="LOW",
                status="completed",
                details={"grant_id": str(grant_id)},
            )
        )
    return True


def list_grants(limit: int = 50, only_live: bool = False) -> list[dict]:
    with plain_session() as db:
        q = (
            select(BreakGlassGrant, PlatformAdmin.email, Tenant.name, Tenant.slug)
            .join(PlatformAdmin, BreakGlassGrant.admin_id == PlatformAdmin.id)
            .join(Tenant, BreakGlassGrant.tenant_id == Tenant.id)
            .order_by(desc(BreakGlassGrant.granted_at))
            .limit(limit)
        )
        if only_live:
            q = q.where(BreakGlassGrant.ended_at.is_(None), BreakGlassGrant.expires_at > utcnow())
        now = utcnow()
        return [
            {
                "id": str(g.id),
                "admin_email": email,
                "tenant_id": str(g.tenant_id),
                "tenant_name": name,
                "tenant_slug": slug,
                "reason": g.reason,
                "scope": g.scope.value,
                "granted_at": g.granted_at.isoformat(),
                "expires_at": g.expires_at.isoformat(),
                "ended_at": g.ended_at.isoformat() if g.ended_at else None,
                "ended_by": g.ended_by,
                "live": g.ended_at is None and g.expires_at > now,
            }
            for g, email, name, slug in db.execute(q).all()
        ]
