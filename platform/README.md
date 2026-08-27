# Aether Platform

Phase 1 foundation for the Aether vision: a **control plane** ("main brain" —
identity, tenants, agent fleet registry) and a **per-tenant agent runtime**
(governed decision loop with audit trail and human approval gates), on a
multi-tenant Postgres enforced by **Row-Level Security**.

Everything here runs on free, self-hosted tooling. The prototype in the repo
root is untouched; this directory is the rebuild.

## Layout

```
platform/
├── src/aether/
│   ├── core/            config, DB + tenant sessions, auth, models
│   ├── policy/          cost-aware decision kernel (per-tenant params)
│   ├── control_plane/   FastAPI app: signup/login, tenants, agents  (port 8100)
│   └── agent_runtime/   FastAPI app: policies, evaluate, approvals  (port 8200)
├── migrations/          Alembic — schema + RLS policies + app role
├── tests/               unit tests + the RLS isolation proof
└── docker-compose.yml   Postgres(pgvector) on 5433 + Redis on 6379
```

## Setup (Windows)

Prereqs already on this machine: Docker Desktop, Python 3.12, Node 24, git.

```powershell
cd platform

# 1. Python env
py -3.12 -m venv .venv
.venv\Scripts\pip install -e ".[dev]"

# 2. Infrastructure (start Docker Desktop first)
docker compose up -d

# 3. Configuration
copy .env.example .env
# then edit .env: set AETHER_JWT_SECRET to the output of
#   .venv\Scripts\python -c "import secrets; print(secrets.token_urlsafe(48))"

# 4. Database schema + RLS (runs as DB owner)
$env:AETHER_MIGRATION_DATABASE_URL="postgresql+psycopg://aether:aether_dev_only@localhost:5433/aether"
.venv\Scripts\alembic upgrade head

# 5. Tests — including proof that tenant A cannot read tenant B
.venv\Scripts\pytest -v
```

## Run the services

```powershell
.venv\Scripts\uvicorn aether.control_plane.app:app --port 8100 --reload
.venv\Scripts\uvicorn aether.agent_runtime.app:app --port 8200 --reload
```

Try the loop end to end (control plane issues the token, agent runtime
enforces it):

```powershell
# Create an org + owner
curl -s -X POST localhost:8100/v1/auth/signup -H "Content-Type: application/json" -d '{\"org_name\":\"Acme Corp\",\"org_slug\":\"acme\",\"email\":\"owner@acmecorp.io\",\"password\":\"a-long-password\"}'

# Use the returned access_token
curl -s -X POST "localhost:8200/v1/domains/churn/evaluate" -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" -d '{\"drift_fraction\":0.6,\"performance\":0.5}'
# → RETRAIN decision with requires_approval=true and an approval_id

curl -s "localhost:8200/v1/approvals" -H "Authorization: Bearer <TOKEN>"
```

## Design notes

- **RLS is the tenancy boundary.** The app connects as `aether_app`, a
  non-owner role, so Postgres enforces `tenant_id = current_setting('app.tenant_id')`
  even against buggy application code. Migrations connect as the owner.
  `tests/test_rls_isolation.py` proves the boundary and runs in CI.
- **Auth is OIDC-shaped.** JWT claims are sub/tenant/role, issued by the
  control plane. Swapping issuance to Auth0/Keycloak later leaves the
  `Principal` contract and every route untouched.
- **The decision kernel is policy-driven.** All constants the prototype
  hardcoded (retrain cost, business impact, thresholds) live in per-tenant
  `PolicyConfig` rows — the same engine produces different decisions for
  different businesses.
- **Approval gates are the Nano/Mega mechanism.** HIGH-risk actions never
  execute directly; they create a `PendingApproval` an owner must resolve.
  Later, Mega agents get executor nodes behind these same gates.

## Not in Phase 1 (by design)

Temporal workflows, LangGraph agents, the LiteLLM gateway, connectors
(Nango/Airbyte), pgvector knowledge base, frontend wiring, billing. Each
plugs into a seam that already exists here (policies, approvals, audit,
tenancy) — see the Aether Platform Blueprint artifact for the sequence.
