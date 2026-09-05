"""Control plane ("main brain") API.

Owns identity, tenants, and the agent fleet registry. Holds no tenant business
data — that lives with each agent runtime.

Run: uvicorn aether.control_plane.app:app --port 8100
"""

import uuid

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select

from aether import __version__
from aether.core import errors, health, logs, money, recovery, sessions
from aether.core.config import get_settings, verify_deployable
from aether.core.db import session, tenant_session
from aether.core.models import (
    AgentInstance,
    AgentKind,
    AuditLog,
    Membership,
    Role,
    Tenant,
    User,
)
from aether.core.security import (
    Principal,
    hash_password,
    issue_token,
    verify_password,
)
from aether.core.tenancy import authenticated, require_role
from aether.core.throttle import (
    SCOPE_RESET_EMAIL,
    SCOPE_RESET_IP,
    client_ip,
    counted,
    guard,
    refused,
    succeeded,
)
from aether.domains import preview
from aether.domains import sector as sector_taxonomy
from aether.knowledge import sector_corpus

app = FastAPI(title="Aether Control Plane", version=__version__)

# Nothing below this line may fail silently: logging so the lines exist,
# the middleware so nothing raised goes unrecorded.
# Logging first, so the configuration check's warnings are formatted and
# attributed like everything else rather than falling out through Python's
# last-resort handler — which is what they did, visibly, in the first
# container that ran.
logs.configure("control_plane")
# Then refuse to start a production process on a development configuration.
# Better a container that will not boot than one accepting forged tokens.
verify_deployable()
errors.install(app, service="control_plane")

# A real bcrypt hash of a value nothing can supply, so an unknown email costs
# the same verification as a known one. Computed once: generating it per
# request would be its own timing signal.
_DUMMY_HASH = hash_password(uuid.uuid4().hex)


@app.get("/")
def root() -> dict:
    return {"service": "aether-control-plane", "version": __version__, "status": "ok"}


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


# ── Signup / login ────────────────────────────────────────────────────────────


class SignupRequest(BaseModel):
    org_name: str = Field(min_length=2, max_length=200)
    org_slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)
    display_name: str = ""
    # The business's own currency. Validated against what the platform can
    # actually render rather than accepted as any three letters, because an
    # unrenderable code would surface much later as a failed explanation.
    currency: str = money.DEFAULT

    # What kind of business this is. Optional, because a business that has not
    # decided must still be able to sign up — 3.3 lets them set it later, and
    # "other" behaves exactly as never having been asked.
    sector: str = sector_taxonomy.UNSPECIFIED

    @field_validator("currency")
    @classmethod
    def _known_currency(cls, value: str) -> str:
        try:
            return money.currency(value).code
        except money.UnsupportedCurrency as exc:
            raise ValueError(str(exc)) from None

    @field_validator("sector")
    @classmethod
    def _known_sector(cls, value: str) -> str:
        if not sector_taxonomy.is_known(value):
            raise ValueError(
                f"{value!r} is not a known sector. "
                f"GET /v1/sectors lists them, with what each one can and cannot be "
                f"given a reference band for."
            )
        return value


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tenant_id: uuid.UUID
    role: Role


@app.post("/v1/auth/signup", response_model=TokenResponse, status_code=201)
def signup(body: SignupRequest) -> TokenResponse:
    """Create an organization (tenant) with its first owner user."""
    with session() as db:
        if db.scalar(select(Tenant).where(Tenant.slug == body.org_slug)):
            raise HTTPException(status_code=409, detail="Organization slug already taken")
        if db.scalar(select(User).where(User.email == body.email.lower())):
            raise HTTPException(status_code=409, detail="Email already registered")

        tenant = Tenant(
            name=body.org_name,
            slug=body.org_slug,
            currency=body.currency,
            sector=body.sector,
        )
        user = User(
            email=body.email.lower(),
            password_hash=hash_password(body.password),
            display_name=body.display_name,
        )
        db.add_all([tenant, user])
        db.flush()
        db.add(Membership(user_id=user.id, tenant_id=tenant.id, role=Role.owner))
        db.flush()
        user_id, tenant_id = user.id, tenant.id
        email = user.email
        chosen = sector_taxonomy.get(tenant.sector)

    # Outside the transaction that created the account: a session is a
    # separate fact, and one that must not be rolled back by a later failure
    # in account creation.
    session_id, expires_at = sessions.begin(user_id, tenant_id)
    token = issue_token(
        user_id, email, tenant_id, Role.owner, session_id=session_id, expires_at=expires_at
    )

    # The agent should know what kind of business it is looking after from its
    # first reading, not from whenever someone next edits a setting.
    sector_corpus.index_sector(tenant_id, chosen)
    return TokenResponse(access_token=token, tenant_id=tenant_id, role=Role.owner)


@app.post("/v1/auth/logout", status_code=204)
def logout(principal: Principal = Depends(authenticated)) -> Response:
    """End this session now.

    Before 6.7 there was no such thing: signing out dropped the cookie and
    left the token valid for the rest of its hour, so anyone holding a copy
    still had an account. Now the session is gone on the next request.
    """
    if principal.session_id:
        sessions.revoke(principal.session_id, reason=sessions.SIGNED_OUT)
    return Response(status_code=204)


@app.post("/v1/auth/logout-all", status_code=200)
def logout_everywhere(principal: Principal = Depends(authenticated)) -> dict[str, int]:
    """End every other session this person has.

    The one asking is kept, because the alternative is that "I think somebody
    else is in my account" signs you out too and leaves you typing your
    password on whatever machine you were worried about.
    """
    ended = sessions.revoke_all_for_user(
        principal.user_id,
        reason=sessions.SIGNED_OUT_EVERYWHERE,
        keep=principal.session_id,
    )
    return {"ended": ended}


@app.get("/v1/auth/sessions")
def my_sessions(principal: Principal = Depends(authenticated)) -> list[dict]:
    """This person's live sessions, so an unfamiliar one can be spotted.

    Deliberately thin. Recognising your own session is the job; building a
    record of where a customer works is not, so there is no device
    fingerprint here and no history of addresses.
    """
    out = sessions.for_user(principal.user_id)
    for row in out:
        row["current"] = row["id"] == str(principal.session_id)
    return out


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


@app.post("/v1/auth/forgot", status_code=202)
def forgot_password(body: ForgotPasswordRequest, request: Request) -> dict[str, str]:
    """Ask for a reset link. Answers identically whether or not the account
    exists — see `core.recovery`, where the reasoning lives."""
    who = {SCOPE_RESET_EMAIL: body.email.lower(), SCOPE_RESET_IP: client_ip(request)}
    guard(who)
    # Before the work, not after: every request spends an attempt, and a
    # caller who is about to be locked should not get one last email out.
    counted(who)

    recovery.request_reset(
        body.email,
        base_url=get_settings().web_base_url,
        requested_from=client_ip(request),
    )
    return {"detail": "If that address has an account, a reset link is on its way."}


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


@app.post("/v1/auth/reset")
def reset_password(body: ResetPasswordRequest, request: Request) -> dict[str, str]:
    """Use a reset link.

    Throttled by address, but say what that is worth: both front ends are
    BFFs, so `client_ip` is empty unless `client_ip_source` is configured, and
    where it is empty this guard does nothing. It is depth, not the defence —
    the defence is that the token is 256 bits of randomness and a guess has no
    better strategy than chance.
    """
    who = {SCOPE_RESET_IP: client_ip(request)}
    guard(who)

    problem = recovery.complete_reset(body.token, body.password)
    if problem is None:
        return {"detail": "Password changed. Sign in with it."}

    counted(who)
    if problem == recovery.WEAK_PASSWORD:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at least {recovery.MIN_PASSWORD_LENGTH} characters.",
        )
    raise HTTPException(status_code=400, detail=_RESET_PROBLEMS[problem])


# Phrased for the person who is trying to get into their own account: "already
# used" and "expired" are different instructions to them, and neither says
# whose account the link was for.
_RESET_PROBLEMS = {
    recovery.UNKNOWN_TOKEN: "That reset link is not valid. Request a new one.",
    recovery.ALREADY_USED: "That reset link has already been used. Request a new one.",
    recovery.EXPIRED: "That reset link has expired. Request a new one.",
}


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    org_slug: str | None = None  # required only when the user belongs to several orgs


@app.post("/v1/auth/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request) -> TokenResponse:
    email = body.email.lower()
    who = {"email": email, "ip": client_ip(request)}
    guard(who)

    with session() as db:
        user = db.scalar(select(User).where(User.email == email, User.is_active))
        if user is None:
            # Hash anyway, so a missing account and a wrong password cost the
            # same time. Without this the endpoint tells an attacker which of
            # our customers' email addresses are real, for free, by clock.
            verify_password(body.password, _DUMMY_HASH)
            refused(who)
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if not verify_password(body.password, user.password_hash):
            refused(who)
            raise HTTPException(status_code=401, detail="Invalid credentials")

        q = select(Membership, Tenant).join(Tenant, Membership.tenant_id == Tenant.id)
        q = q.where(Membership.user_id == user.id, Tenant.is_active)
        if body.org_slug:
            q = q.where(Tenant.slug == body.org_slug)
        rows = db.execute(q).all()

        if not rows:
            raise HTTPException(status_code=403, detail="No organization membership found")
        if len(rows) > 1:
            slugs = sorted(t.slug for _, t in rows)
            raise HTTPException(
                status_code=409,
                detail=f"Multiple organizations; pass org_slug (one of: {', '.join(slugs)})",
            )

        membership, tenant = rows[0]
        succeeded(email)
        user_id, tenant_id, role = user.id, tenant.id, membership.role
        address = user.email

    session_id, expires_at = sessions.begin(user_id, tenant_id, created_from=client_ip(request))
    token = issue_token(
        user_id, address, tenant_id, role, session_id=session_id, expires_at=expires_at
    )
    return TokenResponse(access_token=token, tenant_id=tenant_id, role=role)


# ── Tenant & fleet ────────────────────────────────────────────────────────────


class TenantInfo(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    currency: str
    sector: str
    sector_label: str


@app.get("/v1/tenant", response_model=TenantInfo)
def my_tenant(principal: Principal = Depends(authenticated)) -> TenantInfo:
    with session() as db:
        tenant = db.get(Tenant, principal.tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        chosen = sector_taxonomy.get(tenant.sector)
        return TenantInfo(
            id=tenant.id,
            name=tenant.name,
            slug=tenant.slug,
            currency=tenant.currency,
            sector=chosen.key,
            sector_label=chosen.label,
        )


@app.get("/v1/sectors")
def list_sectors() -> list[dict]:
    """The sectors a business can be, and exactly what each one would change.

    Unauthenticated on purpose: this is a fixed catalogue with no tenant data
    in it, and a signup form needs it before anyone has an account.

    Each entry carries the bands it moves and the caveat on where those figures
    came from. A dropdown that silently changes how a business is judged is
    worse than no dropdown — someone choosing Retail is agreeing to a stricter
    collection standard than the default, and someone choosing Marketing is
    getting no adjustment at all. Both are worth knowing while choosing rather
    than discovering from an alert three weeks later.
    """
    return [preview.summary_for(s) for s in sector_taxonomy.all_sectors()]


class TenantUpdate(BaseModel):
    """What a business may change about itself after signing up.

    Both fields are optional: sending one must not silently reset the other.
    """

    sector: str | None = None
    currency: str | None = None

    @field_validator("sector")
    @classmethod
    def _known_sector(cls, value: str | None) -> str | None:
        if value is not None and not sector_taxonomy.is_known(value):
            raise ValueError(f"{value!r} is not a known sector; GET /v1/sectors lists them")
        return value

    @field_validator("currency")
    @classmethod
    def _known_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return money.currency(value).code
        except money.UnsupportedCurrency as exc:
            raise ValueError(str(exc)) from None


@app.patch("/v1/tenant", response_model=TenantInfo)
def update_tenant(
    body: TenantUpdate,
    principal: Principal = Depends(require_role(Role.owner)),
) -> TenantInfo:
    """Change what kind of business this is, or what money it counts in.

    Owner-only, and written to the tenant's own audit log. A sector change
    moves the bands every future reading is judged against, so an unexplained
    shift in verdicts should be traceable to the day somebody changed this
    rather than looking like the agent became erratic.

    Readings already stored keep the band they were scored against. That is
    deliberate — the same reasoning that stamps currency onto an approval — and
    it means changing sector never rewrites history, only what happens next.
    """
    with session() as db:
        tenant = db.get(Tenant, principal.tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        changed: dict[str, dict[str, str]] = {}
        if body.sector is not None and body.sector != tenant.sector:
            changed["sector"] = {"from": tenant.sector, "to": body.sector}
            tenant.sector = body.sector
        if body.currency is not None and body.currency != tenant.currency:
            changed["currency"] = {"from": tenant.currency, "to": body.currency}
            tenant.currency = body.currency

        chosen = sector_taxonomy.get(tenant.sector)
        info = TenantInfo(
            id=tenant.id,
            name=tenant.name,
            slug=tenant.slug,
            currency=tenant.currency,
            sector=chosen.key,
            sector_label=chosen.label,
        )

    if "sector" in changed:
        # Replaces rather than adds: an agent remembering it was both a
        # retailer and a builders' merchant has two normals and no way to
        # choose. index_sector drops the old memory first.
        sector_corpus.index_sector(principal.tenant_id, chosen)

    if changed:
        with tenant_session(principal.tenant_id) as db:
            db.add(
                AuditLog(
                    tenant_id=principal.tenant_id,
                    # Not a business function, so not a domain. Named rather
                    # than left blank so it is filterable and obvious.
                    domain="organization",
                    action="TENANT_UPDATED",
                    triggered_by=principal.email,
                    risk_level="LOW",
                    details=changed,
                    status="completed",
                )
            )
    return info


class AgentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    kind: AgentKind = AgentKind.nano


class AgentInfo(BaseModel):
    id: uuid.UUID
    name: str
    kind: AgentKind
    is_active: bool


@app.post("/v1/agents", response_model=AgentInfo, status_code=201)
def create_agent(
    body: AgentCreate,
    principal: Principal = Depends(require_role(Role.operator)),
) -> AgentInfo:
    # Product scope: only Aether Nano (monitor/diagnose/report) is offered
    # today. The mega tier stays in the schema as the upgrade seam, but the
    # API refuses to provision capability that doesn't exist yet.
    if body.kind is not AgentKind.nano:
        raise HTTPException(
            status_code=422,
            detail="Only 'nano' agents can be provisioned; 'mega' is not yet available.",
        )
    with tenant_session(principal.tenant_id) as db:
        agent = AgentInstance(tenant_id=principal.tenant_id, name=body.name, kind=body.kind)
        db.add(agent)
        db.flush()
        return AgentInfo(id=agent.id, name=agent.name, kind=agent.kind, is_active=agent.is_active)


@app.get("/v1/agents", response_model=list[AgentInfo])
def list_agents(principal: Principal = Depends(authenticated)) -> list[AgentInfo]:
    with tenant_session(principal.tenant_id) as db:
        agents = db.scalars(select(AgentInstance)).all()
        return [AgentInfo(id=a.id, name=a.name, kind=a.kind, is_active=a.is_active) for a in agents]


# ── Ingest credentials ────────────────────────────────────────────────────────


class KeyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)


@app.post("/v1/api-keys", status_code=201)
def create_api_key(
    body: KeyCreate,
    principal: Principal = Depends(require_role(Role.owner)),
) -> dict:
    """Issue an ingest key. The secret is returned once and never again.

    Owner-only: a key is a standing credential that outlives any session, so
    minting one is a different act from using the product.
    """
    from aether.core.apikeys import create_key

    issued = create_key(principal.tenant_id, body.name, principal.email)
    return {
        "id": str(issued.id),
        "name": issued.name,
        "prefix": issued.prefix,
        # The only time this value exists outside the caller's own systems.
        "secret": issued.secret,
        "note": "Store this now. It cannot be shown again.",
    }


@app.get("/v1/api-keys")
def list_api_keys(principal: Principal = Depends(authenticated)) -> list[dict]:
    from aether.core.apikeys import list_keys

    return list_keys(principal.tenant_id)


@app.post("/v1/api-keys/{key_id}/revoke")
def revoke_api_key(
    key_id: uuid.UUID,
    principal: Principal = Depends(require_role(Role.owner)),
) -> dict:
    from aether.core.apikeys import revoke_key

    if not revoke_key(principal.tenant_id, key_id):
        raise HTTPException(status_code=404, detail="No such active key")
    return {"id": str(key_id), "revoked": True}
