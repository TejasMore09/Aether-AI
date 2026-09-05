# The plan

Ten phases. Ordered so each one unlocks the next rather than by what is
easiest — several later phases are impossible until Phase 1 exists.

**Status key:** `[x]` done · `[~]` in progress · `[ ]` not started

---

## ▶ CURRENT POSITION: Phase 6

Phases 0–4 complete, plus 6.4 and 6.5. Phase 4 closed with a real finding:
the backtest showed the 80% intervals covering only 52% on a random walk and
12% on a curve, so `fit` now refuses both shapes rather than quoting a
confidence it has not earned (D53).

**Phase 6 is where "production-level" actually lives.** 4 of 10 items open.
Both finished items closed holes nobody was looking for: 6.5 found the *test
suite* sending real email through the live Resend key, stopped only by an
unverified sending domain (D55); 6.3 found that a fault could never learn
which tenant it belonged to, because sync endpoints run in a threadpool and a
context variable set there never comes back (D58). Phase 5 needs no new data
(two bands already sit in `reference/`) and can follow. 669 tests, none
skipped.

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

## Phase 2 — Agent knowledge base `[x]` COMPLETE

The thing asked for in the very first vision message and still entirely
unbuilt. `pgvector` is in the Docker image; the extension has never been
created.

Per-agent, isolated. One business's knowledge must be unreachable from
another's — same RLS discipline as every other tenant table, and worth a
dedicated isolation test because this is where a leak would be worst.

- [x] **2.1** Enable pgvector; `knowledge_chunks` table, tenant-scoped, RLS enforced
- [x] **2.2** Embedding pipeline with a free/local model — no paid API dependency
- [x] **2.3** Retrieval scoped to one tenant, with an isolation test that fails loudly on any cross-tenant hit
- [x] **2.4** Ingest a tenant's own history — past decisions, approvals, outcomes — so the agent remembers what it already told them
- [x] **2.5** Retrieval feeds the diagnosis prompt: prior similar situations and how they resolved
- [x] **2.6** Main brain can see chunk counts and freshness, never chunk contents, without break-glass

**Done when:** an agent's explanation can reference what happened to that same
business six months ago, and no query path can reach another tenant's chunks.
Both hold as of 2026-09-01.

### Completion debt `[ ]`

Phase 2 is complete as scoped above, and the scope was narrower than the
words "agent knowledge base" imply. What is missing is written here rather
than left for someone to discover:

- The store holds only what the system generated about itself — its own
  decisions. A business cannot give its agent their contracts, policies or
  reports. That arrives with document ingest in **7.1/7.2**.
- ~~It knows nothing about the sector the business is in.~~ Done in **3.4**:
  each agent now holds a paragraph on what is normal in its industry.
- [ ] **2.7** Hybrid retrieval: keyword search alongside vectors, and a
  reranker. The embedding model reliably answers only "have we seen almost
  exactly this?" (D25), and this is the standard fix for exactly that.
- [ ] **2.8** A retrieval evaluation harness — measured recall on realistic
  queries, published. There is currently no number for how good retrieval is,
  only tests proving it does what it was designed to do.

So: **structurally complete now, genuinely complete after Phase 7**, with
2.7 and 2.8 doable at any point in between.

---

## Phase 3 — Sector awareness `[x]` COMPLETE

Currently a stock brokerage and a bakery receive byte-identical packs. This is
the specific gap Tejas called out, and there is no hook to hang it on yet.

Note the honest constraint: sector bands need *real-world truth*. Code here is
days; defensible numbers are the slow part and need Tejas's domain access.
Build the mechanism first so numbers can be filled in as they are learned.

- [x] **3.0** Multi-currency: money stops being USD-by-name (D31, D33)
- [x] **3.1** Sector taxonomy on the tenant: 21 sectors, crosswalked to ISIC (which
  NIC and NACE share) and NAICS, with ambiguity declared rather than guessed
  (D35, D36)
- [x] **3.2** Per-sector bands layered over pack defaults, clamped to the pack's
  allowance so the ordering across sectors transfers and the levels do not (D39)
- [x] **3.3** Sector chosen at signup and changeable in settings, with the effect on
  bands previewed before saving — including when it is nothing (D41, D42)
- [x] **3.4** Sector knowledge in the agent's knowledge base, derived entirely from
  the committed reference table, and reaching the explanation (D43, D44)
- [x] **3.5** Sector-specific metrics: a metric declares the traits a business must
  have for it to mean anything, and sectors declare their traits (D45)
- [x] **3.6** Provenance everywhere: the threshold shown is always the threshold
  used, and says which of the three layers it came from (D47)

**Done when:** two tenants in different sectors reporting identical numbers
receive different, defensible verdicts — and each can see why.

---

## Phase 4 — Forecasting `[x]` COMPLETE

The system is entirely reactive. It cannot say "at this rate you cross
critical in six weeks", which is most of what "future precautions" means.

Classical methods, not deep learning — 52 points a year supports trend and
seasonality and nothing heavier.

- [x] **4.1** Per-metric trend extrapolation, with a prediction interval rather than
  a confidence interval and a horizon that never exceeds the history (D48, D49)
- [x] **4.2** Time-to-critical, as a range rather than a date — the early edge is
  the one worth acting on
- [x] **4.3** Seasonality, detected on residuals and refusing where the history
  cannot support it. Removing one buys precision rather than accuracy (D52)
- [x] **4.4** Trajectories reach the decision engine: they bring a look forward,
  never raise what is said to be at stake, and never reach `intervene` (D51)
- [x] **4.5** Refusing is a family of answers with a sentence each, not one silence
  (D50). Steady, improving and drifting are different news
- [x] **4.6** Backtest harness. It found the intervals lying on two ordinary
  series shapes, and the fix was to refuse them rather than document it (D53)

**Done when:** a decision can be justified by where a metric is heading, with
a stated confidence, and the system declines when it does not know.

---

## Phase 5 — Domain breadth `[ ]`

Three of roughly a dozen, and all three are finance-adjacent — the most
standardised corner. HR and marketing are harder because "healthy" is far less
agreed.

Each domain is cheap in code and expensive in truth. Do not add a pack whose
bands are pure invention; that scales confident guessing.

**Chosen by how replaceable the job is, hardest one included (D32).** Three of
these are built; the three marked next complete the set.

- [ ] **5.1** *(easy)* **Payables & supplier terms** — the AP clerk's job. Band
  comes from `Acc Pay/Sales` in `reference/`, already in hand
- [ ] **5.2** *(medium)* **Inventory & stock cover** — the stock controller's job.
  Band comes from `Inventory/Sales` in the same file
- [ ] **5.3** *(hard)* **Customer concentration & credit risk** — the judgement a
  clerk does not make. Needs no new ingestion: `top5_concentration` is already a
  receivables metric and Phase 1's cross-domain machinery already exists
- [ ] **5.4** Workforce / HR — deliberately after real data. "Healthy attrition"
  is genuinely contested and most SMEs hold no HRIS data to check it against
- [ ] **5.5** Marketing — spend efficiency, channel mix
- [ ] **5.6** Compliance — filing deadlines, licences. Jurisdiction-specific, so it
  waits on 3.1

**5.1 + 5.2 + receivables complete the cash conversion cycle** (DSO + DIO — DPO),
which is the working-capital measure an SME's own accountant already uses.

---

## Phase 6 — Production hardening `[ ]`

Not client-facing readiness — product completeness. Several of these are
cheap now and painful later.

- [x] **6.1** Deployment. Ten containers from one compose file, a Caddy edge with
  automatic certificates and rate limiting (measured: 59 served then 429), and
  production processes that refuse to start on a development configuration
  (D60). Unlocked 6.4's per-address throttle, which needed a change at all three
  hops (D61). **"Free tier" has an honest answer and it is not a PaaS**: the
  stack is ~690 MiB and ~2.6 GB of images, so Oracle Always Free or a $10–20 VPS
  (D62). Not yet run on a real host, and no CI
- [x] **6.2** Automated backups with a tested restore. Every dump is restored
  into a scratch database and asked five questions — revision, tables, **RLS
  policies**, no emptied table, pgvector — because `pg_dump` as the app role and
  `pg_restore` both error and exit 0 (D63). Removed Redis, which nothing had
  ever used (D64). **Off-site copying is not implemented**: this survives a
  dropped table, not a lost host
- [x] **6.3** Error tracking and metrics; alerts that reach a person. Faults in
  our own Postgres rather than a third party, because a stack trace here carries
  customers' data (D57); one row per distinct fault; scrubbed text readable only
  by engineers and recorded in the staff trail; alerts rationed per-fault and
  globally; a console page; `/readyz` that actually checks, since `/healthz` was
  answering "ok" through any outage (D59). **Alerts go nowhere until
  `AETHER_ALERT_EMAIL` is set**, which the page says out loud
- [x] **6.4** Login throttling per account, with backoff. Per-address is built but
  inert until a deployment can name the client (see PROGRESS 2026-09-02).
  General per-endpoint rate limiting belongs at the proxy in 6.1 and is not done
- [x] **6.5** Password reset. Hashed single-use tokens, 45-minute life, no
  enumeration oracle, its own throttle counters so asking to reset somebody's
  password cannot lock them out of logging in, and completing one clears the
  login lockout. Raised the account lockout cap from 15 minutes to an hour,
  which 6.4 had deliberately held down. **Does not revoke live sessions** —
  JWTs are stateless; that gap belongs to 6.7
- [ ] **6.6** MFA, at least for owners
- [x] **6.7** Sessions in a table rather than refresh tokens (D65), because
  refresh tokens make *stateless* validation cheap and nothing here is
  stateless — and because they leave revocation waiting for an expiry. Closes
  D56: a password reset now ends every session. Role and membership are read
  live, so a token can no longer claim a role. Idle window replaces the
  60-minute hard expiry. **Staff sessions are not covered** — still 30-minute
  tokens with nothing behind them
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
