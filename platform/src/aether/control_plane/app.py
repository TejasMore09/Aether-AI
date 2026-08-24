"""Control plane ("main brain") API.

Owns identity, tenants, and the agent fleet registry. Holds no tenant business
data — that lives with each agent runtime.

Run: uvicorn aether.control_plane.app:app --port 8100
"""

import uuid

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from aether import __version__
from aether.core.db import session, tenant_session
from aether.core.models import (
    AgentInstance,
    AgentKind,
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

app = FastAPI(title="Aether Control Plane", version=__version__)


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

        tenant = Tenant(name=body.org_name, slug=body.org_slug)
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
def login(body: LoginRequest) -> TokenResponse:
    with session() as db:
        user = db.scalar(select(User).where(User.email == body.email.lower(), User.is_active))
        if not user or not verify_password(body.password, user.password_hash):
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
        token = issue_token(user.id, user.email, tenant.id, membership.role)
        return TokenResponse(access_token=token, tenant_id=tenant.id, role=membership.role)


# ── Tenant & fleet ────────────────────────────────────────────────────────────


class TenantInfo(BaseModel):
    id: uuid.UUID
    name: str
    slug: str


@app.get("/v1/tenant", response_model=TenantInfo)
def my_tenant(principal: Principal = Depends(authenticated)) -> TenantInfo:
    with session() as db:
        tenant = db.get(Tenant, principal.tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        return TenantInfo(id=tenant.id, name=tenant.name, slug=tenant.slug)


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
    with tenant_session(principal.tenant_id) as db:
        agent = AgentInstance(tenant_id=principal.tenant_id, name=body.name, kind=body.kind)
        db.add(agent)
        db.flush()
        return AgentInfo(id=agent.id, name=agent.name, kind=agent.kind, is_active=agent.is_active)


@app.get("/v1/agents", response_model=list[AgentInfo])
def list_agents(principal: Principal = Depends(authenticated)) -> list[AgentInfo]:
    with tenant_session(principal.tenant_id) as db:
        agents = db.scalars(select(AgentInstance)).all()
        return [
            AgentInfo(id=a.id, name=a.name, kind=a.kind, is_active=a.is_active) for a in agents
        ]
