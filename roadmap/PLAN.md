# The plan

Ten phases. Ordered so each one unlocks the next rather than by what is
easiest — several later phases are impossible until Phase 1 exists.

**Status key:** `[x]` done · `[~]` in progress · `[ ]` not started

---

## ▶ CURRENT POSITION: Phase 1

Phase 0 complete. Phase 1 started 2026-08-28. 

Keep this line in step with `roadmap/README.md`.

---

## Phase 0 — Foundation `[x]` COMPLETE

The multi-tenant platform everything else stands on.

- [x] Postgres row-level security, enforced via a non-owner app role, proven by test
- [x] Control plane: identity, tenants, agent registry (port 8100)
- [x] Agent runtime: readings, decisions, approvals, audit (port 8200)
- [x] Domain pack format — a business function is configuration, not code
- [x] Cost-aware decision engine with payback horizon and severity bias
- [x] Data quality gate with quarantine, never silent drops
- [x] Temporal durable monitor loop, one schedule per (tenant, domain)
- [x] LLM diagnosis via LiteLLM, metered per tenant, with deterministic fallback
- [x] Per-tenant calibrated bands, anchored so dysfunction cannot normalise
- [x] Three domain packs: receivables, cash & runway, sales pipeline
- [x] Customer dashboard (port 3000)
- [x] Per-tenant ingest API keys
- [x] Main brain: fleet health view, break-glass grants, append-only staff trail (port 8300)
- [x] Staff console (port 3100)

170 tests. Roughly 70% of "a robust multi-tenant monitoring platform" and
roughly 15% of the vision in `VISION.md`.

---

## Phase 1 — Cross-domain reasoning `[x]` COMPLETE

**Why first.** Nothing in the system currently represents *a business*. Each
domain is scored in complete isolation: receivables has no idea cash exists.
So when a client's DSO stretches and their runway shortens, they get two
unrelated alerts from two agents that have never met — while any competent
advisor would say instantly that these are one problem.

That gap is the difference between a metrics tool and something that
understands a business. Every later phase assumes a business-level object
exists to hang knowledge, sector context and forecasts on.

- [x] **1.1** `BusinessState` — one object holding every domain's latest reading, signals and decision for a tenant
- [x] **1.2** A relations file: which metrics across domains move together, and in which direction, with reasons
- [x] **1.3** Correlation pass — detect co-movement across domains in a tenant's own history, not just the declared relations
- [x] **1.4** `CrossDomainFinding` — a finding that names several domains at once, with a combined exposure figure
- [x] **1.5** Suppression: when a cross-domain finding subsumes single-domain ones, raise the former and mute the latter rather than sending both
- [x] **1.6** Diagnosis prompt receives the whole business, not one domain
- [x] **1.7** Dashboard surface for cross-domain findings, visibly distinct from per-domain ones
- [x] **1.8** Tests: co-movement detected, spurious correlation rejected, suppression correct, no leakage across tenants

**Done when:** a tenant with stretching DSO and shortening runway receives one
finding that connects them, with combined money at risk, instead of two.

---

## Phase 2 — Agent knowledge base `[ ]`

The thing asked for in the very first vision message and still entirely
unbuilt. `pgvector` is in the Docker image; the extension has never been
created.

Per-agent, isolated. One business's knowledge must be unreachable from
another's — same RLS discipline as every other tenant table, and worth a
dedicated isolation test because this is where a leak would be worst.

- [ ] **2.1** Enable pgvector; `knowledge_chunks` table, tenant-scoped, RLS enforced
- [ ] **2.2** Embedding pipeline with a free/local model — no paid API dependency
- [ ] **2.3** Retrieval scoped to one tenant, with an isolation test that fails loudly on any cross-tenant hit
- [ ] **2.4** Ingest a tenant's own history — past decisions, approvals, outcomes — so the agent remembers what it already told them
- [ ] **2.5** Retrieval feeds the diagnosis prompt: prior similar situations and how they resolved
- [ ] **2.6** Main brain can see chunk counts and freshness, never chunk contents, without break-glass

**Done when:** an agent's explanation can reference what happened to that same
business six months ago, and no query path can reach another tenant's chunks.

---

## Phase 3 — Sector awareness `[ ]`

Currently a stock brokerage and a bakery receive byte-identical packs. This is
the specific gap Tejas called out, and there is no hook to hang it on yet.

Note the honest constraint: sector bands need *real-world truth*. Code here is
days; defensible numbers are the slow part and need Tejas's domain access.
Build the mechanism first so numbers can be filled in as they are learned.

- [ ] **3.1** Sector taxonomy on the tenant — coarse enough to be useful, fine enough to matter
- [ ] **3.2** Packs carry per-sector band overrides layered over their defaults
- [ ] **3.3** Sector selected during onboarding, changeable, with the effect on bands shown honestly
- [ ] **3.4** Sector corpus in the knowledge base — what normal looks like in that industry
- [ ] **3.5** Sector-specific metrics: a pack may declare metrics that only apply to some sectors
- [ ] **3.6** Provenance everywhere: every band states whether it came from the pack, the sector, or the tenant's own history

**Done when:** two tenants in different sectors reporting identical numbers
receive different, defensible verdicts — and each can see why.

---

## Phase 4 — Forecasting `[ ]`

The system is entirely reactive. It cannot say "at this rate you cross
critical in six weeks", which is most of what "future precautions" means.

Classical methods, not deep learning — 52 points a year supports trend and
seasonality and nothing heavier.

- [ ] **4.1** Per-metric trend extrapolation with honest confidence intervals
- [ ] **4.2** Time-to-critical: when the current trajectory crosses the band
- [ ] **4.3** Seasonality, where enough history exists to justify claiming it
- [ ] **4.4** Forecasts enter the decision engine — act earlier when the trajectory is bad, not only when the level is
- [ ] **4.5** Refuse to forecast on thin history rather than guessing; say so plainly
- [ ] **4.6** Backtest harness — measure forecast error, publish it, do not hide it

**Done when:** a decision can be justified by where a metric is heading, with
a stated confidence, and the system declines when it does not know.

---

## Phase 5 — Domain breadth `[ ]`

Three of roughly a dozen, and all three are finance-adjacent — the most
standardised corner. HR and marketing are harder because "healthy" is far less
agreed.

Each domain is cheap in code and expensive in truth. Do not add a pack whose
bands are pure invention; that scales confident guessing.

- [ ] **5.1** Workforce / HR — headcount, attrition, time-to-fill, absence
- [ ] **5.2** Inventory / supply — cover, stockouts, dead stock, lead time
- [ ] **5.3** Marketing — spend efficiency, pipeline contribution, channel mix
- [ ] **5.4** Operations — delivery, utilisation, rework
- [ ] **5.5** Customer health — churn, concentration, satisfaction
- [ ] **5.6** Compliance — filing deadlines, licences, obligations

---

## Phase 6 — Production hardening `[ ]`

Not client-facing readiness — product completeness. Several of these are
cheap now and painful later.

- [ ] **6.1** Deployment: containerised, infrastructure as code, free tier
- [ ] **6.2** Automated backups with a *tested* restore, not merely configured
- [ ] **6.3** Error tracking and metrics; alerts that reach a person
- [ ] **6.4** Rate limiting and login lockout — currently absent, credential stuffing is wide open
- [ ] **6.5** Password reset — a locked-out user currently cannot be helped at all
- [ ] **6.6** MFA, at least for owners
- [ ] **6.7** Refresh tokens; 60-minute hard expiry is a support burden at scale
- [ ] **6.8** GDPR: export and delete, as an obligation not a feature
- [ ] **6.9** Load test at 30 tenants; size the connection pools from evidence
- [ ] **6.10** Billing and subscription tiers

---

## Phase 7 — Connectors `[ ]`

Ingest credentials exist; nothing pulls data from anywhere. Today a business
types numbers into a form or writes its own curl job.

- [ ] **7.1** Spreadsheet upload with column mapping — what an SME actually has
- [ ] **7.2** Connector framework: scheduled pull, incremental, failure-visible
- [ ] **7.3** Accounting integration (Xero or QuickBooks)
- [ ] **7.4** Payments (Stripe)
- [ ] **7.5** CRM (HubSpot or Zoho)
- [ ] **7.6** Connector health surfaced to the tenant and to the fleet view

---

## Phase 8 — Mega foundations `[ ]`

Everything Mega needs *before* it may act. Do not start until Nano has run
against real data long enough to be trusted.

- [ ] **8.1** Action framework: declared, permissioned, reversible
- [ ] **8.2** Write-scoped connector credentials, separate from read
- [ ] **8.3** Dry run — show exactly what would happen, execute nothing
- [ ] **8.4** Rollback for every action type; no action ships without one
- [ ] **8.5** Per-action permission model the customer controls
- [ ] **8.6** Blast-radius limits: value caps, rate caps, hard stops
- [ ] **8.7** Kill switch, per tenant and fleet-wide

---

## Phase 9 — Mega autonomy `[ ]`

- [ ] **9.1** Autonomy levels the customer sets per action class
- [ ] **9.2** Graduated trust: an action type earns autonomy through a record of correct recommendations
- [ ] **9.3** Multi-step plans, gated as a plan rather than step by step
- [ ] **9.4** Outcome tracking — did acting actually help? Feed it back
- [ ] **9.5** Liability and audit posture fit for a machine acting on a real business

---

## Phase 10 — Scale and operate `[ ]`

- [ ] **10.1** Onboarding a tenant without an engineer
- [ ] **10.2** Support tooling in the console: replay a decision, explain a verdict
- [ ] **10.3** Cost per tenant measured and controlled
- [ ] **10.4** 30 Nano + 10 Mega proven under load, not assumed

---

## The constraint that outranks the plan

Phases 3, 4 and 5 are each gated on knowing what is true about real
businesses. That knowledge cannot be generated — it has to come from data or
from people who run these companies.

Building the mechanisms without it is worthwhile: the code is real and the
numbers can be replaced. Shipping invented numbers as though they were
knowledge is not, because a confidently wrong verdict costs more trust than
an admitted gap.

If progress stalls, it will stall here, and the fix is not more code.
