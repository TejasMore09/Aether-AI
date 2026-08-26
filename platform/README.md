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
.venv\Scripts\python -m aether.worker   # Nano monitor worker (needs Temporal from compose)
```

Then the dashboard:

```powershell
cd web
npm install
copy .env.example .env.local
npm run dev                             # http://localhost:3000
```

Temporal UI (inspect schedules/workflow runs): http://localhost:8233

## The autonomous Nano loop

Telemetry flows in, decisions flow out on a schedule — no request required:

1. `POST /v1/domains/{domain}/observations` — connectors or the customer's
   systems push drift/performance readings.
2. `PUT /v1/domains/{domain}/monitoring {"interval_minutes": 60}` — creates a
   Temporal Schedule for (tenant, domain). Overlap policy SKIP; deleting via
   `DELETE .../monitoring`.
3. Every interval, Temporal starts `NanoMonitorWorkflow` → the worker runs the
   shared evaluation service: latest observation × tenant policy → decision →
   immutable audit entry; HIGH-risk actions wait in `/v1/approvals` for a human.
4. Stale telemetry (>24h) is refused, not acted on; missing telemetry reports
   `no_data`. Activity retries with backoff; a crashed worker resumes where
   Temporal left off.

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

## The dashboard (`web/`)

Next.js 16 App Router, built on the **BFF pattern**: the browser never holds a
token and never talks to the platform APIs. Sign-in is a Server Action that
stores the JWT in an httpOnly cookie; every read happens in a Server Component
and every mutation in a Server Action, with the token attached server-side.
Consequences worth knowing:

- No token in JavaScript (XSS cannot steal a session) and no CORS surface —
  the APIs stay reachable only from the server.
- `proxy.ts` (Next 16 renamed Middleware → Proxy) is an *optimistic* redirect
  for cookieless requests only; real authorization is the API's JWT check plus
  Postgres RLS on every query.
- Pages: Overview, Approvals (diagnosis + approve/reject), Domains and domain
  detail (telemetry, monitoring schedule, on-demand run), Activity (audit trail
  + notification log), AI Usage (spend vs budget).

"Evaluate now" calls `POST /v1/domains/{domain}/monitor-run`, which starts the
*same* Temporal workflow the schedule uses — so an on-demand run diagnoses and
notifies exactly like an autonomous one, rather than being a lesser path.

## Domain packs — what the platform knows about a business function

A pack (`src/aether/domains/packs/*.yaml`) is curated configuration: which
metrics a business function reports, what healthy looks like, how raw metrics
become risk signals, what actions exist, and how an explanation should read.

Adding a business function means writing a pack. It must never mean editing
agent code — that constraint is what keeps expansion cheap, and it is enforced
by the engine reasoning in generic *action slots* (`none`, `monitor`,
`investigate`, `intervene`) that each pack labels for its own domain. This is
why a finance product says `ESCALATE_COLLECTIONS` and never inherits `RETRAIN`
from the ML prototype.

Shipping today: **receivables** (cash owed and whether it arrives on time).

### The path a reading takes

```
raw metrics → quality gate → baseline + derivation → decision
```

- **Quality gate** (`domains/quality.py`) — accuracy is enforced here, not
  assumed upstream. Required fields, numeric types, physical ranges, unknown
  keys, and cross-metric contradictions (disputed cannot exceed overdue; a
  balance cannot exist with zero invoices). A failing reading is
  **quarantined, not dropped**: it stays visible with its reasons and never
  reaches a decision.
- **Derivation** (`domains/derive.py`) — health is scored per metric against
  the pack's bands, then combined. The composite blends the weighted mean with
  the *worst* single metric, because a mean alone lets healthy secondary
  metrics average away a crisis in a core one. Drift is measured against the
  tenant's own rolling median, and only movement in the unhealthy direction
  counts. With too little history there is no baseline and drift reports zero
  — an unknown is not a signal.
- **Economics** — a pack picks how "what does this cost" is computed.
  Receivables uses `exposure_scaled` (money at risk × carrying rate), which is
  far more honest than an invented error rate. Acting is worthwhile when the
  loss repays the one-off intervention cost inside the payback window, because
  comparing a one-off cost to a daily loss is a category error.

### Endpoints

```
GET  /v1/catalogue                     what the platform can watch, and what it expects
POST /v1/domains/{domain}/readings     submit business metrics (goes through the gate)
POST /v1/domains/{domain}/observations submit pre-derived signals (no pack required)
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

## Not built yet (by design)

LangGraph diagnosis agents, the LiteLLM gateway, connectors (Nango/Airbyte),
pgvector knowledge base, frontend wiring, billing. Each plugs into a seam that
already exists here (observations, policies, approvals, audit, tenancy) — see
the Aether Platform Blueprint artifact for the sequence.
