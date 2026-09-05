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
│   ├── agent_runtime/   FastAPI app: policies, evaluate, approvals  (port 8200)
│   └── main_brain/      FastAPI app: fleet health, break-glass        (port 8300)
├── web/                 Next.js customer dashboard                    (port 3000)
├── console/             Next.js staff console — talks only to 8300    (port 3100)
├── migrations/          Alembic — schema + RLS policies + app role
├── tests/               unit tests + the RLS isolation proof
├── Dockerfile           the three APIs and the worker, one image
└── docker-compose.yml   the whole backend for development, one command
```

Production deployment lives in `deploy/` at the repository root: one compose
file, a Caddy edge that holds the certificates, and `deploy/README.md` for what
"free tier" actually means for a stack this size.

## Running it

Prereqs: Docker Desktop, Node 24, git. Python 3.12 only if you want to run the
tests on the host.

```powershell
cd platform

# Everything on the back end: Postgres, Temporal, migrations, and the three
# APIs. First run builds the image, which takes a few minutes; after that it
# is seconds.
docker compose up -d

cd web && npm install && npm run dev        # http://localhost:3000
```

That is the whole thing. The staff console is a second app:

```powershell
cd console && npm install && npm run dev    # http://localhost:3100
```

| | |
|---|---|
| Dashboard | http://localhost:3000 |
| Staff console | http://localhost:3100 |
| Control plane | http://localhost:8100 · `/readyz` |
| Agent runtime | http://localhost:8200 |
| Main brain | http://localhost:8300 (staff only) |
| Temporal UI | http://localhost:8233 |
| Postgres | `localhost:5433`, user `aether` |

`src/` is bound into the API containers with `--reload`, so editing Python
takes effect immediately. The two Next apps run on the host because their hot
reload through a Windows bind mount is slower than the extra terminal is
annoying.

The autonomous monitor worker is off unless asked for — it is only useful once
a domain has monitoring enabled, and until then it is noise in the logs:

```powershell
docker compose --profile worker up -d
```

**Nothing needs configuring to run.** The development secrets ship in the
repository so a checkout works with no `.env` at all; production refuses to
start on them (D60). Copy `.env.example` to `.env` only when you want to add
an LLM or email key.

### Tests

They run on the host against the same database the containers use, so they
need the Python environment:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\pytest -q          # includes the proof tenant A cannot read tenant B
```

The backup tests additionally need `pg_dump` on PATH and skip without it.

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

## The main brain (`main_brain/`, port 8300)

Operating a fleet of isolated agents eventually means someone has to debug one
of them. The question is not whether staff *can* reach tenant data — at the
database, somebody always can — but whether reaching it is deliberate,
bounded, and visible to the customer afterwards.

It is a separate ASGI app on its own port precisely so "is this endpoint
staff-only?" is answered by which file the route lives in, rather than by
remembering to attach the right dependency. Bind it to an internal interface.

### The console (`console/`, port 3100)

```powershell
cd console; npm install; npm run dev
```

A separate Next.js application from `web/`, for the same reason the API is a
separate app: if the console were a route group inside the customer
dashboard, that deployment would hold main-brain credentials and one routing
mistake would be a cross-boundary mistake. As it stands the customer app has
no configuration pointing at the brain and no code that talks to it.

It also looks nothing like the customer product — flat, cold and dense where
Forge is warm and roomy. That is a safety property rather than a preference:
staff should never be even briefly unsure whether they are looking at their
own console or a customer's dashboard.

Three surfaces:

- **Fleet** opens on *needs attention*, not on everything. It scores each
  tenant — silent agents, quarantine rates, undelivered notifications, budget,
  waiting decisions — and sorts worst first. The distinction it works hardest
  to keep is between an agent that has gone quiet and a tenant that never
  started; collapsing those is how a real outage hides in a list of unused
  accounts.
- **Tenant** carries the break-glass form. It states the consequence in the
  form itself: this organization will see your email and this reason, word
  for word, immediately and permanently. Their data appears on the same page
  once a grant is open, and nowhere until then.
- **Staff trail** is the whole append-only record, readable by every staff
  member.

While a grant is open, a sticky bar follows you across every page in a colour
used nowhere else in the interface, counting down and offering one click to
end it. Friction belongs on opening access, never on closing it.

### The first admin

```powershell
.venv\Scripts\python -m aether.main_brain.bootstrap you@company.com --role admin
```

A local command, not an endpoint: a route that mints the first superuser is a
route that has to be right forever, including on the day someone forgets to
disable it. It refuses once any admin exists; after that, staff are added
through `POST /v1/staff` by someone already accountable.

### Two things staff can do, and the line between them

**Fleet health** (`GET /v1/fleet`) is free to read. Per tenant: agent count,
observation and quarantine counts, last reading time, pending approvals,
active keys, month-to-date AI spend, failed notifications. Counts and
timestamps — never a metric value, a diagnosis, or an approval reason.

That restriction is structural, not a convention. `/v1/fleet` reads a database
**view** owned by the migration role, which owns the underlying tables and so
bypasses their row-level security; the application role is granted `SELECT` on
the view and nothing else changes about its access to the tables. Staff code
*cannot* read a tenant's numbers through this path, because the view does not
select them — there is no argument to the call that would change that.

**Tenant contents** require a break-glass grant: one named person, one named
organization, a written reason of at least 12 characters, and a hard expiry
capped by `AETHER_BREAK_GLASS_MAX_MINUTES` (default 240). Expiry is checked at
use, so a grant dies on time even if no sweeper has run. There is no "extend" —
a longer look is a new grant with its own reason, which keeps the trail a list
of decisions rather than one open-ended session.

```bash
curl -X POST localhost:8300/v1/grants -H "Authorization: Bearer <STAFF_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"...","reason":"Nightly sync stopped after key rotation, SUP-118.","minutes":15}'
```

### Why the customer is told

Opening a grant writes into **the tenant's own audit log**, and their Activity
page shows it in a section of its own above their agent's activity: who
looked, under what scope, the reason verbatim, and when it ends. A staff-only
trail asks the customer to trust that we police ourselves. An entry in the log
they already read means staff access turns up beside their own agent's
decisions, unprompted.

### What the platform records about itself

Every staff action lands in `staff_audit_logs`, **reads included** — for a
platform holding other companies' operating data, looking is the act that
needs explaining. The table is append-only at the database: a trigger raises
on `UPDATE` and `DELETE`, so the guarantee holds against the application
itself, which is what an attacker who reaches the app would be holding. It
raises rather than silently ignoring, because a swallowed `DELETE` leaves the
caller believing it worked.

The trail is readable by every staff member, not only admins — oversight only
the powerful can see is not oversight.

### Token separation

Staff tokens are signed with `AETHER_STAFF_JWT_SECRET`, distinct from
`AETHER_JWT_SECRET`, and carry issuer `aether-main-brain`. A customer's JWT
presented to the brain, and a staff JWT presented to a tenant endpoint, each
fail on two independent checks. If the customer-facing signing key ever leaks,
the blast radius is one organization's sessions — not the ability to mint an
identity with reach across the whole fleet.

Staff roles: `observer` (fleet health), `engineer` (may open a grant), `admin`
(may manage staff and end anyone's grant).

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

## Frontend: chosen directions and deferred polish

Two surfaces, chosen from `/preview` (delete that route once both are built):

- **Minimal** — the public, no-signup explore surface. Calm, legible to a
  stranger, colour reserved for money at risk.
- **Forge** — the authenticated product. Neumorphic form on Console's warm
  charcoal with a copper accent, Manrope + JetBrains Mono.

They share the data model and differ only in treatment.

### Motion rules already established

These hold wherever motion is added later, and exist because breaking them
produced real bugs (see the Forge commit):

- Motion happens on **arrival and interaction only**. Nothing loops — ambient
  looping animation is the clearest tell of a generated interface.
- **Animation is an enhancement, never the source of a value.** `rAF` and
  timers are frozen in a backgrounded tab, so anything that animates *toward*
  a figure can strand it at zero. Elements carry their true value in the
  resting style and animate a transform on top of it.
- Every primitive collapses to a correct static render under
  `prefers-reduced-motion`, rather than merely running faster.
- One counting figure per view. Applied to every number it is noise.

### Deferred (explicitly parked, not forgotten)

- Richer interaction polish: route/page transitions, optimistic UI on approve
  and reject, skeleton loaders shaped like their content rather than spinners
- Charts for the trend data (currently a table); sparkline in each metric card
- Command palette, keyboard navigation, focus management on route change
- Composed empty and error states rather than plain text
- Toasts for background outcomes (a scheduled run completing)
- shadcn/ui component layer — deliberately not installed until the direction
  was settled, so it does not have to be fought later

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
