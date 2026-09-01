# Aether — architecture

Aether monitors the operating numbers of a small or mid-sized business,
decides when something is worth a person's attention, and explains why in the
language of the business rather than the language of the system watching it.

One agent per customer. Each agent's data is isolated from every other's. A
central control plane operates the fleet without being able to read what is
inside any of them, except deliberately, temporarily, and visibly.

This document describes what exists. It replaces `architecture_strategy.md`
and `implementation_plan.md`, which described an earlier prototype built
around model retraining and no longer match the code.

---

## 1. The shape of it

Four services and a database. Everything runs locally today; nothing here
assumes a cloud.

| Service | Port | Talks to | Holds |
|---|---|---|---|
| `control_plane` | 8100 | customers | identity, tenants, agent registry, API keys |
| `agent_runtime` | 8200 | customers, connectors | readings, decisions, approvals, audit |
| `main_brain` | 8300 | **staff only** | fleet health, break-glass grants, staff audit |
| `worker` | — | Temporal | the autonomous monitor loop |
| `web/` | 3000 | customers | the dashboard |
| `console/` | 3100 | **staff only** | the fleet console |

Postgres (pgvector image) on 5433. Temporal for durable scheduling. LiteLLM as
the model gateway, currently pointed at Gemini.

The staff surfaces are separate applications on separate ports, not route
groups inside the customer ones. That is the whole reason they are separate:
"is this endpoint staff-only?" is answered by which file it lives in, and the
customer deployment holds no credential that reaches the brain.

Both web apps are back-end-for-front-end. The JWT lives in an httpOnly cookie,
every call is a Server Component or Server Action, and the browser never
learns the service hostnames or holds a token.

---

## 2. Tenant isolation

This is the load-bearing claim of the product, so it is enforced by Postgres
rather than by application code remembering to filter.

Every tenant-scoped table carries `tenant_id` and a row-level security policy.
The application connects as `aether_app`, a **non-owner** role — table owners
bypass RLS, so connecting as the owner would silently disable the entire
isolation model. Migrations run as the owner; nothing else does.

Tenant context is set per transaction:

```sql
SELECT set_config('app.tenant_id', :tenant_id, true)
```

Transaction-local, so it is safe under connection pooling and cannot leak from
one request into the next.

Two details worth knowing, both found the hard way:

- Policies use the **strict** one-argument `current_setting('app.tenant_id')`
  deliberately. With no tenant context the query errors rather than returning
  zero rows, because a missing context is a bug and silence reads exactly like
  "this tenant has no data".

- `api_keys` is the one exception, and uses
  `nullif(current_setting('app.tenant_id', true), '')`. It is legitimately read
  *before* a tenant context exists — resolving a key is how the tenant gets
  established. Note the `nullif`: a transaction-local `set_config` defines the
  GUC for the whole session and reverts only its *value* at commit, so a pooled
  connection that previously served a tenant sees `''`, and `''::uuid` throws
  just as an unset one does.

A test asserts the isolation directly rather than trusting the design.

---

## 3. How data gets in

Three ways, in ascending order of realism:

1. **The dashboard.** A person types the period's numbers. Works from day one,
   does not scale past a pilot.
2. **API keys.** A per-tenant credential for unattended connectors, issued and
   revoked from the customer's own **Connections** page. Only a SHA-256 hash is
   stored — deliberate rather than lazy: these are 256-bit CSPRNG tokens, so
   there is nothing to brute-force, and bcrypt would add its cost to every
   ingest request for no security gain. A key authenticates exactly one
   dependency, so a leaked key can add readings and can never approve a
   decision or read an audit trail.
3. **Connectors.** Not built. The keys exist so they can be.

Every reading passes a quality gate before it counts. Failing readings are
**quarantined, not dropped** — kept visible with their reasons — because a
customer whose data silently vanished has no way to find out why. Quarantined
readings are excluded from diagnosis; a regression test pins that, after one
leaked through and produced a confidently wrong explanation.

---

## 4. From a reading to a decision

```
reading → quality gate → derive signals → decide → gate on a human → explain
```

**Derive** turns domain metrics into two numbers the engine understands:

- *Performance* — absolute health against the metric's band.
- *Drift* — movement against this tenant's own recent median.

They answer different questions. A business can be steadily unhealthy (low
performance, no drift) or suddenly worse from a healthy base (high
performance, high drift), and both matter.

The composite blends the weighted mean with the **worst single metric**
(`severity_bias`). A plain mean let one metric in crisis be cancelled by three
that were fine: a book at 95 days DSO with 45% overdue scored middling and
gated nothing.

**Decide** compares the money at risk per day against the one-off cost of
acting, over a `payback_days` horizon. Comparing a one-off cost to a daily
loss without a horizon is a category error — it once declined a $400
collections push against $147/day of exposure that would have repaid it in
under three days.

Some breaches are not cost-benefit questions at all. A metric marked
`existential` escalates on its own once past its critical bound, and the
payback test is skipped. Payroll cover is the current example: weighing "we
can make payroll for three more weeks" against the cost of a phone call
produces a confident wrong answer, because the downside is not a daily rate
and no daily rate can represent it.

Anything gated waits for a named human. The decision, its reasoning, and the
resolution are written to an append-only audit trail.

---

## 5. Healthy bands adapt, but not freely

A pack ships one band per metric. Those numbers are a reasonable starting
point and a bad permanent answer: a supplier on 60-day terms is not sick, and
a SaaS business at 60 days is in trouble.

So each tenant's history proposes its own band — and the pack's published band
constrains how far that proposal may travel, as a fraction of the distance
between healthy and critical.

The constraint is the point. The obvious version of this idea is broken: a
business that has *always* run 40% of its book overdue would learn that 40% is
normal and go quiet exactly when it should not. Pure "learn what's normal"
normalises dysfunction, and on business metrics dysfunction is often stable.

The critical bound never moves. It is an absolute line, not a preference, and
a tenant whose healthy bound drifts toward it gets a steeper curve — correct,
because their normal really is closer to trouble.

Measured on the receivables pack:

| Tenant | Band used | Score | A fixed band would give |
|---|---|---|---|
| 60-day terms, reading 60 | 61 → 90 | 1.00 | 0.67 — alarmed forever |
| Fast collector, slips to 40 | 21 → 90 | 0.72 | 1.00 — invisible |
| No history yet | 45 → 90 | 0.67 | unchanged |
| Chronic 40% overdue | 0.30 → 0.40 | 0.00 | own p75 of 0.44 clamped to 0.30 |

Every score carries the band it used and where that band came from, and
explanations quote the band actually applied — otherwise the paragraph would
tell a customer their 60-day book exceeds a threshold of 45 about a reading
the agent had just called healthy.

---

## 6. Domain packs

A pack is curated YAML describing one business function: its metrics, healthy
bands, economics, action vocabulary, and how an explanation for that domain
should read. Adding a business function must mean writing a pack, never
editing agent code — that constraint is what keeps expansion cheap.

Shipped: **Cash & Receivables**, **Cash & Runway**.

The engine reasons in domain-independent `ActionSlot`s — none, monitor,
investigate, intervene — and the pack supplies each slot's label for its
domain. This is why `RETRAIN` never appears in a finance product, and why the
engine has no idea what receivables are.

Adding the second pack tested that claim honestly. It mostly held — the pack
is configuration — but it exposed two real defects: `exposure_scaled` required
the at-risk fraction to be a *reported* metric, when no owner records "the
share of my bills I cannot pay" (hence `shortfall_scaled`, which derives it);
and the engine described every exposure as money "outstanding", receivables
vocabulary leaking out of the one abstraction built to keep domains apart.

Both were fixed in the engine, and the receivables pack was unchanged by
either. That is the property to preserve: a new domain should extend the
engine, never bend it.

---

## 7. The main brain

Operating a fleet means someone eventually has to debug a customer's agent.
The question is not whether staff *can* reach tenant data — at the database,
somebody always can — but whether reaching it is deliberate, bounded, and
visible to the customer afterwards.

**Fleet health is aggregate by construction.** `/v1/fleet` reads a database
view owned by the migration role, which owns the underlying tables and so
bypasses their RLS; the application role holds `SELECT` on the view and
nothing more. Staff see counts, timestamps, spend and error rates for every
tenant and *cannot* reach a metric value by that path, because the view does
not select one. There is no argument to the call that would change that.

**Tenant contents require a break-glass grant**: one named person, one named
organization, a written reason, a hard expiry capped by config and checked at
use, so a grant dies on time with no sweeper. There is no extend — a longer
look is a new grant with its own reason, which keeps the trail a list of
decisions rather than one open-ended session.

**The customer is told.** Opening a grant writes into *their* audit log, and
their Activity page shows it above their agent's own activity: who looked,
under what scope, the reason verbatim, when it ends. A staff-only trail asks
the customer to trust that we police ourselves; an entry in the log they
already read does not.

**Staff actions are recorded, reads included** — for a platform holding other
companies' operating data, looking is the act that needs explaining. The table
is append-only via a trigger that raises on `UPDATE` and `DELETE`, so the
guarantee holds against the application itself, which is what an attacker who
reached the app would be holding. It raises rather than silently ignoring,
because a swallowed `DELETE` leaves the caller believing it worked.

**Tokens cannot cross.** Staff tokens use their own signing key and their own
issuer, so a customer JWT at the brain and a staff JWT at a tenant endpoint
each fail two independent checks. A leak of the customer signing key costs one
organization's sessions, not the ability to mint fleet-wide identity.

---

## 8. What an agent remembers

Each agent has its own knowledge base: a `knowledge_chunks` table carrying a
384-dimension embedding per row, scoped by the same row-level policy as every
other tenant table. One business's memory is unreachable from another's, which
is why the isolation tests there go further than elsewhere — many tenants at
once, threads sharing a connection pool, and a query whose globally nearest
neighbour belongs to somebody else.

**Embeddings are computed locally**, by a small ONNX model on the machine
running the platform. No text leaves the deployment to be vectorised, and
there is no paid API in the path.

**Similarity search is an exact scan, deliberately.** Under row-level security
an approximate HNSW index searches the whole table and then discards what the
policy forbids, so a tenant whose rows are a small fraction of the table gets
back nothing at all — measured, and recorded in migration `0009`. The index
exists; the query does not use it. That is a correctness decision, and it will
need revisiting on volume rather than on principle.

**What is stored is decisions, not readings.** Numbers are already in the
database and directly queryable. The memory worth keeping is *"we have been
here before, and last time you decided this"*, which lives in the approvals.
Resolving an approval indexes it, as a background task after the response.

**What comes back is fenced before it reaches a customer.** Only memories
measurably closer than the tenant's others are quoted, the recalled text is
labelled as that business's own past rather than as fact, and the prompt
forbids any claim about how a past decision turned out — nothing tracks that
yet. Retrieval failing costs an explanation a sentence, never the explanation:
memory is an enhancement, never a precondition.

The limitation to hold onto: this model reliably answers *"have we seen almost
exactly this before?"* and is close to useless on *"is this vaguely related?"*
Everything above is built around the first question, and nothing downstream
should claim the second.

---

## 9. Where the numbers come from

The honest state of the data question.

**Healthy bands** start from published, defensible ranges written into each
pack, then adapt per tenant within the anchored limits above. No dataset is
purchased and none is required.

**Per-tenant history** is the only training signal in the system. There is no
shared model across tenants and no cross-tenant learning — that is a security
property, not an oversight, and it is why a knowledge base sits at the agent
level rather than the fleet level.

**There is no ML model.** The earlier prototype had drift detection and
retraining; the current system has curated economics and per-tenant
calibration. If a model is added later it belongs behind the pack interface,
not in the engine.

The unresolved part: bands are seeded from general knowledge rather than from
sector benchmarks. A construction supplier and a SaaS business currently start
from the same defaults and diverge only through their own history. Sector-
seeded starting points would shorten the cold-start period and are the obvious
next improvement.

---

## 10. Deliberately not built

- **Aether Mega.** The schema carries the tier as an upgrade seam; the API
  refuses to provision it. Nano monitors, diagnoses and reports. Nothing acts
  on a business system autonomously.
- **Connectors.** Credentials exist; integrations do not.
- **Cross-tenant analytics.** Would require exactly the data sharing the
  isolation model exists to prevent.
- **Deployment.** Everything runs locally. There is no infrastructure code.

---

## 11. Verification

141 tests. RLS isolation is proven by test rather than asserted by design, and
the break-glass gate is mutation-checked — stubbing the grant check to always
pass fails five tests, so they are load-bearing rather than decorative.

`ruff`, `mypy` and both Next.js builds run clean.
