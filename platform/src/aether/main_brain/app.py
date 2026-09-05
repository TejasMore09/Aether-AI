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

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from aether import __version__
from aether.core import errors, health, logs, mfa
from aether.core.config import verify_deployable
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
    admin_by_id,
    authenticate_staff,
    begin_staff_session,
    create_admin,
    end_grant,
    fleet_health,
    has_role,
    issue_staff_mfa_challenge,
    issue_staff_token,
    list_grants,
    load_staff_session,
    read_staff_trail,
    record,
    revoke_staff_session,
    revoke_staff_sessions_for,
    verify_staff_mfa_challenge,
    verify_staff_token,
)
from aether.core.throttle import client_ip, guard, refused, succeeded

app = FastAPI(title="Aether Main Brain", version=__version__)

# Nothing below this line may fail silently: logging so the lines exist,
# the middleware so nothing raised goes unrecorded.
# Logging first, so the configuration check's warnings are formatted and
# attributed like everything else rather than falling out through Python's
# last-resort handler — which is what they did, visibly, in the first
# container that ran.
logs.configure("main_brain")
# Then refuse to start a production process on a development configuration.
# Better a container that will not boot than one accepting forged tokens.
verify_deployable()
errors.install(app, service="main_brain")


@app.get("/")
def root() -> dict:
    return {"service": "aether-main-brain", "version": __version__, "status": "ok"}


@app.get("/healthz")
def healthz() -> dict:
    """Liveness: is this process alive? Deliberately does not touch the
    database — a liveness probe that does is how a brief database blip becomes
    an orchestrator killing every healthy container it has."""
    return {"status": "ok"}


@app.get("/readyz")
def readyz(response: Response) -> dict:
    """Readiness: can this process actually serve? This is the one to route
    and to monitor on. `/healthz` said "ok" through a total outage."""
    ok, detail = health.database_ok()
    if not ok:
        response.status_code = 503
    return {"status": "ok" if ok else "unavailable", "database": detail or "ok"}


# ── Staff identity ────────────────────────────────────────────────────────────


def staff_authenticated(request: Request) -> StaffPrincipal:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    try:
        principal = verify_staff_token(header.removeprefix("Bearer ").strip())
        # A genuine signature is not a signed-in member of staff. Tokens minted
        # before 6.6 carry no session and are refused rather than trusted —
        # a staff credential that cannot be revoked is the thing this removed.
        if principal.session_id is None:
            raise StaffTokenError("no session")
        # Role and is_active come from the row, not the token, so demoting or
        # deactivating somebody applies to their next request. For a credential
        # that reaches every tenant, that difference is the feature.
        return load_staff_session(principal.session_id)
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

    # A correct password is not a session when there is a second factor — and
    # a staff credential reaches every tenant on the platform, so this is the
    # surface where it matters most (6.6).
    if mfa.required_for(mfa.STAFF, admin.id):
        record(admin.email, "staff.login.mfa_required")
        return {
            "mfa_required": True,
            "challenge": issue_staff_mfa_challenge(admin),
        }

    record(admin.email, "staff.login")
    session_id, expires_at = begin_staff_session(admin, created_from=client_ip(request))
    return {
        "access_token": issue_staff_token(admin, session_id=session_id, expires_at=expires_at),
        "token_type": "bearer",
        "email": admin.email,
        "role": admin.role.value,
    }


class StaffMfaVerify(BaseModel):
    challenge: str
    code: str = Field(min_length=6, max_length=40)


@app.post("/v1/staff/mfa/verify")
def staff_verify_second_factor(body: StaffMfaVerify, request: Request) -> dict:
    """Finish a staff sign-in that stopped for a second factor."""
    try:
        pending = verify_staff_mfa_challenge(body.challenge)
    except StaffTokenError as exc:
        raise HTTPException(status_code=401, detail="Start again from the sign-in page.") from exc

    who = {"email": f"staff:{pending.email}", "ip": client_ip(request)}
    guard(who)

    admin = admin_by_id(pending.admin_id)
    if admin is None or not mfa.verify(mfa.STAFF, pending.admin_id, body.code):
        refused(who)
        raise HTTPException(status_code=401, detail="That code is not right.")

    succeeded(f"staff:{pending.email}")
    record(admin.email, "staff.login")
    session_id, expires_at = begin_staff_session(admin, created_from=client_ip(request))
    return {
        "access_token": issue_staff_token(admin, session_id=session_id, expires_at=expires_at),
        "token_type": "bearer",
        "email": admin.email,
        "role": admin.role.value,
    }


@app.get("/v1/staff/mfa")
def staff_mfa_status(principal: StaffPrincipal = Depends(staff_authenticated)) -> dict:
    state = mfa.status(mfa.STAFF, principal.admin_id)
    return {
        "enrolled": state.enrolled,
        "confirmed": state.confirmed,
        "recovery_codes_left": state.recovery_codes_left,
        "available": mfa.available(),
    }


@app.post("/v1/staff/mfa/enrol")
def staff_start_enrolment(principal: StaffPrincipal = Depends(staff_authenticated)) -> dict:
    try:
        secret, uri = mfa.begin_enrolment(mfa.STAFF, principal.admin_id, principal.email)
    except mfa.MfaUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except mfa.MfaError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"secret": secret, "otpauth_uri": uri}


class StaffMfaCode(BaseModel):
    code: str = Field(min_length=6, max_length=40)


@app.post("/v1/staff/mfa/confirm")
def staff_confirm_enrolment(
    body: StaffMfaCode,
    request: Request,
    principal: StaffPrincipal = Depends(staff_authenticated),
) -> dict:
    who = {"email": f"staff:{principal.email}", "ip": client_ip(request)}
    guard(who)
    try:
        codes = mfa.confirm_enrolment(mfa.STAFF, principal.admin_id, body.code)
    except mfa.MfaError as exc:
        refused(who)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record(principal.email, "staff.mfa.enabled")
    return {"recovery_codes": codes}


@app.post("/v1/staff/mfa/disable", status_code=204)
def staff_disable_second_factor(
    body: StaffMfaCode,
    request: Request,
    principal: StaffPrincipal = Depends(staff_authenticated),
) -> Response:
    """Turn a staff second factor off, which needs a current code.

    Recorded, because weakening the authentication on a fleet-wide credential
    is exactly the sort of act the staff trail exists to make answerable.
    """
    who = {"email": f"staff:{principal.email}", "ip": client_ip(request)}
    guard(who)
    if not mfa.verify(mfa.STAFF, principal.admin_id, body.code):
        refused(who)
        raise HTTPException(status_code=401, detail="That code is not right.")

    mfa.disable(mfa.STAFF, principal.admin_id)
    record(principal.email, "staff.mfa.disabled")
    revoke_staff_sessions_for(principal.admin_id, reason="mfa_disabled", keep=principal.session_id)
    return Response(status_code=204)


@app.post("/v1/staff/logout", status_code=204)
def staff_logout(principal: StaffPrincipal = Depends(staff_authenticated)) -> Response:
    """End this staff session now.

    Before 6.6 signing out of the console dropped a cookie and left the token
    valid — a credential with reach across every tenant, still working."""
    if principal.session_id:
        revoke_staff_session(principal.session_id)
    record(principal.email, "staff.logout")
    return Response(status_code=204)


@app.post("/v1/staff/{admin_id}/sessions/revoke")
def revoke_staff_access(
    admin_id: uuid.UUID,
    principal: StaffPrincipal = Depends(require_staff_role(StaffRole.admin)),
) -> dict[str, int]:
    """End every session belonging to one member of staff.

    The capability that matters most in this file. A staff credential believed
    to be compromised reaches every tenant on the platform, and until now the
    only available answer was to wait for it to expire — or to deactivate the
    account, which is a different and more permanent thing to do to a colleague
    at two in the morning on a suspicion.

    Admin-only, and recorded: ending another person's access is exactly the
    sort of act the staff trail exists to make answerable.
    """
    ended = revoke_staff_sessions_for(admin_id, reason="revoked_by_admin")
    record(
        principal.email,
        "staff.revoke_sessions",
        details={"admin_id": str(admin_id), "ended": ended},
    )
    return {"ended": ended}


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


# ── Faults ────────────────────────────────────────────────────────────────────
#
# The one place in this console where staff see something *derived from* a
# customer's data rather than counted over it. A stack trace crosses the
# tenant boundary by its nature, and the fleet view's whole discipline is that
# it does not.
#
# So the boundary is drawn inside the payload rather than at the door (D57).
# `observer` — the role whose documented limit is "counts, timestamps, error
# rates. Never the contents of a tenant's data" — sees that something is
# broken, where in our code, how often, and how many tenants it touched.
# Reading the scrubbed message and traceback needs `engineer`, and is written
# to the staff trail like any other look at something a customer owns.


def _fault_summary(row: dict) -> dict:
    """What any member of staff may see. No text from the failure itself."""
    return {
        "fingerprint": row["fingerprint"],
        "service": row["service"],
        "exception_type": row["exception_type"],
        "location": row["location"],
        "occurrences": row["occurrences"],
        "tenants_seen": row["tenants_seen"],
        "first_seen_at": row["first_seen_at"].isoformat(),
        "last_seen_at": row["last_seen_at"].isoformat(),
        "alerted": row["alerted_at"] is not None,
        "resolved_at": row["resolved_at"].isoformat() if row["resolved_at"] else None,
        "resolved_by": row["resolved_by"],
        "reference": row["last_reference"],
    }


@app.get("/v1/ops/errors")
def list_faults(
    limit: int = 50,
    include_resolved: bool = False,
    principal: StaffPrincipal = Depends(staff_authenticated),
) -> list[dict]:
    """Open faults, newest first. Text only for engineers.

    An observer gets the shape of every fault and the words of none. That is
    enough to say "the platform is broken and here is where", which is what
    the role is for.
    """
    rows = errors.recent(limit=min(limit, 200), include_resolved=include_resolved)
    out = [_fault_summary(r) for r in rows]

    if has_role(principal, StaffRole.engineer):
        for summary, row in zip(out, rows, strict=True):
            summary["message"] = row["message"]
            summary["traceback"] = row["traceback"]
        if out:
            # Recorded because it is a read of something derived from customer
            # data, and the trail exists so that such reads are answerable.
            # Fingerprints, not content: the trail must not become the copy of
            # the thing it is auditing access to.
            record(
                principal.email,
                "faults.read",
                details={"count": len(out), "fingerprints": [r["fingerprint"][:12] for r in out]},
            )
    return out


@app.post("/v1/ops/errors/{fingerprint}/resolve")
def resolve_fault(
    fingerprint: str,
    principal: StaffPrincipal = Depends(require_staff_role(StaffRole.engineer)),
) -> dict:
    """Mark a fault handled, which re-arms its alarm.

    Not cosmetic: an unresolved fault keeps its old alert timestamp, so one
    that was fixed and comes back weeks later would be folded silently into a
    row that has already alerted and nobody would hear about it.
    """
    if not errors.resolve(fingerprint, by=principal.email):
        raise HTTPException(status_code=404, detail="No open fault with that fingerprint")
    record(principal.email, "faults.resolve", details={"fingerprint": fingerprint[:12]})
    return {"status": "resolved", "fingerprint": fingerprint}


@app.get("/v1/ops/health")
def ops_health(principal: StaffPrincipal = Depends(staff_authenticated)) -> dict:
    """Is the platform well? Counts only, so every staff role may read it.

    Includes whether alerting is configured at all, because an alerting system
    nobody set up looks exactly like an alerting system with nothing to say.
    """
    return health.snapshot("main_brain")
