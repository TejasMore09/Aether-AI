"""Control plane ("main brain") API.

Owns identity, tenants, and the agent fleet registry. Holds no tenant business
data — that lives with each agent runtime.

Run: uvicorn aether.control_plane.app:app --port 8100
"""

import uuid

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select

from aether import __version__
from aether.core import money
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
from aether.core.throttle import client_ip, guard, refused, succeeded
from aether.domains import preview
from aether.domains import sector as sector_taxonomy

app = FastAPI(title="Aether Control Plane", version=__version__)

# A real bcrypt hash of a value nothing can supply, so an unknown email costs
# the same verification as a known one. Computed once: generating it per
# request would be its own timing signal.
_DUMMY_HASH = hash_password(uuid.uuid4().hex)


@app.get("/")
def root() -> dict:
    return {"service": "aether-control-plane", "version": __version__, "status": "ok"}


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


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
        token = issue_token(user.id, user.email, tenant.id, Role.owner)
        return TokenResponse(access_token=token, tenant_id=tenant.id, role=Role.owner)


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
        token = issue_token(user.id, user.email, tenant.id, membership.role)
        return TokenResponse(access_token=token, tenant_id=tenant.id, role=membership.role)


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
