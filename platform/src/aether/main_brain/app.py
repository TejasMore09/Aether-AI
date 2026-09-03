"""Main brain API — the fleet console for platform staff.

A separate ASGI app on its own port, not a router bolted onto the control
plane. Staff and customers reaching the platform through the same listener
would mean one routing mistake is a cross-boundary mistake; on separate ports
the staff surface can be bound to an internal interface or put behind a VPN
without touching customer traffic, and "is this endpoint staff-only?" is
answered by which file it lives in.

Run: uvicorn aether.main_brain.app:app --port 8300
"""

import uuid
from collections.abc import Callable

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from aether import __version__
from aether.core.db import session as plain_session
from aether.core.db import tenant_session
from aether.core.models import (
    AuditLog,
    GrantScope,
    Observation,
    PendingApproval,
    PlatformAdmin,
    StaffRole,
)
from aether.core.staff import (
    GrantError,
    StaffPrincipal,
    StaffTokenError,
    active_grant,
    authenticate_staff,
    create_admin,
    end_grant,
    fleet_health,
    has_role,
    issue_staff_token,
    list_grants,
    read_staff_trail,
    record,
    verify_staff_token,
)
from aether.core.throttle import client_ip, guard, refused, succeeded

app = FastAPI(title="Aether Main Brain", version=__version__)


@app.get("/")
def root() -> dict:
    return {"service": "aether-main-brain", "version": __version__, "status": "ok"}


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


# ── Staff identity ────────────────────────────────────────────────────────────


def staff_authenticated(request: Request) -> StaffPrincipal:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    try:
        return verify_staff_token(header.removeprefix("Bearer ").strip())
    except StaffTokenError as exc:
        # A tenant user's token lands here too, and is refused for the same
        # reason as a forged one: it is not a staff token.
        raise HTTPException(status_code=401, detail=f"Invalid staff token: {exc}") from exc


def require_staff_role(minimum: StaffRole) -> Callable[..., StaffPrincipal]:
    def dependency(
        principal: StaffPrincipal = Depends(staff_authenticated),
    ) -> StaffPrincipal:
        if not has_role(principal, minimum):
            raise HTTPException(
                status_code=403, detail=f"Requires {minimum.value} staff role or higher"
            )
        return principal

    return dependency


class StaffLogin(BaseModel):
    email: EmailStr
    password: str


@app.post("/v1/staff/login")
def staff_login(body: StaffLogin, request: Request) -> dict:
    # Staff credentials are the more valuable of the two: one of these reaches
    # every tenant in the fleet, where a customer's reaches one organization.
    # Same mechanism, and no reason to make it weaker here.
    email = body.email.lower()
    who = {"email": f"staff:{email}", "ip": client_ip(request)}
    guard(who)

    admin = authenticate_staff(email, body.password)
    if admin is None:
        refused(who)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    succeeded(f"staff:{email}")
    record(admin.email, "staff.login")
    return {
        "access_token": issue_staff_token(admin),
        "token_type": "bearer",
        "email": admin.email,
        "role": admin.role.value,
    }


class StaffCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=200)
    role: StaffRole
    display_name: str = ""


@app.post("/v1/staff", status_code=201)
def add_staff(
    body: StaffCreate,
    principal: StaffPrincipal = Depends(require_staff_role(StaffRole.admin)),
) -> dict:
    with plain_session() as db:
        if db.scalar(select(PlatformAdmin).where(PlatformAdmin.email == body.email.lower())):
            raise HTTPException(status_code=409, detail="That staff email already exists")

    admin = create_admin(body.email, body.password, body.role, body.display_name)
    record(
        principal.email,
        "staff.create",
        details={"created": admin.email, "role": admin.role.value},
    )
    return {"id": str(admin.id), "email": admin.email, "role": admin.role.value}


@app.get("/v1/staff")
def list_staff(
    principal: StaffPrincipal = Depends(require_staff_role(StaffRole.admin)),
) -> list[dict]:
    with plain_session() as db:
        rows = db.scalars(select(PlatformAdmin).order_by(PlatformAdmin.email)).all()
        return [
            {
                "id": str(a.id),
                "email": a.email,
                "display_name": a.display_name,
                "role": a.role.value,
                "is_active": a.is_active,
            }
            for a in rows
        ]


# ── Fleet health (no tenant content) ──────────────────────────────────────────


@app.get("/v1/fleet")
def get_fleet(principal: StaffPrincipal = Depends(staff_authenticated)) -> list[dict]:
    """Health of every tenant agent. Counts and timestamps only.

    Not recorded in the staff trail: this reads no customer content, and an
    audit trail that fills with routine dashboard polling stops being read at
    all. What gets recorded is the moment someone crosses into a tenant.
    """
    return fleet_health()


# ── Break-glass ───────────────────────────────────────────────────────────────


class GrantRequest(BaseModel):
    tenant_id: uuid.UUID
    reason: str = Field(min_length=12, max_length=2000)
    scope: GrantScope = GrantScope.read_only
    minutes: int = Field(default=30, ge=1, le=1440)


@app.post("/v1/grants", status_code=201)
def open_break_glass(
    body: GrantRequest,
    principal: StaffPrincipal = Depends(require_staff_role(StaffRole.engineer)),
) -> dict:
    from aether.core.staff import open_grant

    try:
        grant = open_grant(principal, body.tenant_id, body.reason, body.scope, body.minutes)
    except GrantError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "id": str(grant.id),
        "tenant_id": str(grant.tenant_id),
        "scope": grant.scope.value,
        "expires_at": grant.expires_at.isoformat(),
        "note": "This organization's own audit log now shows that you opened access.",
    }


@app.get("/v1/grants")
def get_grants(
    live: bool = False,
    principal: StaffPrincipal = Depends(staff_authenticated),
) -> list[dict]:
    return list_grants(only_live=live)


@app.post("/v1/grants/{grant_id}/end")
def close_break_glass(
    grant_id: uuid.UUID,
    principal: StaffPrincipal = Depends(require_staff_role(StaffRole.engineer)),
) -> dict:
    try:
        ended = end_grant(principal, grant_id)
    except GrantError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not ended:
        raise HTTPException(status_code=404, detail="No such open grant")
    return {"id": str(grant_id), "ended": True}


# ── Tenant content, behind a grant ────────────────────────────────────────────


def _gated(principal: StaffPrincipal, tenant_id: uuid.UUID, what: str) -> None:
    """Refuse unless this staff member holds a live grant for this tenant,
    and record the read when they do."""
    grant = active_grant(principal.admin_id, tenant_id)
    if grant is None:
        raise HTTPException(
            status_code=403,
            detail=(
                "No open break-glass grant for this organization. "
                "Open one with a reason before reading its data."
            ),
        )
    record(
        principal.email,
        "break_glass.read",
        tenant_id=tenant_id,
        grant_id=grant.id,
        details={"resource": what},
    )


@app.get("/v1/tenants/{tenant_id}/audit-logs")
def tenant_audit_logs(
    tenant_id: uuid.UUID,
    limit: int = 100,
    principal: StaffPrincipal = Depends(staff_authenticated),
) -> list[dict]:
    """The tenant's own decision trail — usually enough to resolve an incident
    without ever looking at their metric values."""
    _gated(principal, tenant_id, "audit_logs")
    with tenant_session(tenant_id) as db:
        rows = db.scalars(
            select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500))
        ).all()
        return [
            {
                "id": str(r.id),
                "created_at": r.created_at.isoformat(),
                "domain": r.domain,
                "action": r.action,
                "triggered_by": r.triggered_by,
                "risk_level": r.risk_level,
                "status": r.status,
                "details": r.details,
            }
            for r in rows
        ]


@app.get("/v1/tenants/{tenant_id}/observations")
def tenant_observations(
    tenant_id: uuid.UUID,
    limit: int = 50,
    principal: StaffPrincipal = Depends(staff_authenticated),
) -> list[dict]:
    """Raw readings, including the metric values. The deepest thing staff can
    reach, and the one that most needs a reason attached to it."""
    _gated(principal, tenant_id, "observations")
    with tenant_session(tenant_id) as db:
        rows = db.scalars(
            select(Observation)
            .order_by(Observation.observed_at.desc(), Observation.seq.desc())
            .limit(min(limit, 200))
        ).all()
        return [
            {
                "id": str(r.id),
                "observed_at": r.observed_at.isoformat(),
                "domain": r.domain,
                "source": r.source,
                "status": r.status,
                "metrics": r.metrics,
                "issues": r.issues,
                "performance": r.performance,
                "drift_fraction": r.drift_fraction,
            }
            for r in rows
        ]


@app.get("/v1/tenants/{tenant_id}/approvals")
def tenant_approvals(
    tenant_id: uuid.UUID,
    principal: StaffPrincipal = Depends(staff_authenticated),
) -> list[dict]:
    _gated(principal, tenant_id, "approvals")
    with tenant_session(tenant_id) as db:
        rows = db.scalars(
            select(PendingApproval).order_by(PendingApproval.created_at.desc()).limit(100)
        ).all()
        return [
            {
                "id": str(r.id),
                "created_at": r.created_at.isoformat(),
                "domain": r.domain,
                "action": r.action,
                "status": r.status.value,
                "risk_level": r.risk_level,
                "expected_loss": r.expected_loss,
                "currency": r.currency,
                "diagnosis": r.diagnosis,
            }
            for r in rows
        ]


# ── The staff trail ───────────────────────────────────────────────────────────


@app.get("/v1/staff-trail")
def staff_trail(
    limit: int = 100,
    tenant_id: uuid.UUID | None = None,
    principal: StaffPrincipal = Depends(staff_authenticated),
) -> list[dict]:
    """Readable by every staff member, not just admins. Oversight that only
    the powerful can see is not oversight."""
    return read_staff_trail(limit=min(limit, 500), tenant_id=tenant_id)
