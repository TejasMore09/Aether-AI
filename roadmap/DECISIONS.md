# Decisions already made

Choices a session arriving cold might plausibly reverse by accident. Each one
cost something to arrive at; several were found by getting the opposite wrong
first.

If you disagree with one, that is fine — but change it deliberately and update
this file, rather than drifting away from it.

---

## D1 — Tenant isolation is enforced by Postgres, not application code

Every tenant table has a row-level security policy, and the application
connects as `aether_app`, a **non-owner** role. Table owners bypass RLS
entirely, so connecting as the owner would silently disable the whole isolation
model while every test still passed.

Tenant context is set per transaction with `set_config(..., true)`, which is
pooling-safe.

**Do not** add a tenant table without an RLS policy, and **do not** change the
app's connection to an owner role for convenience.

---

## D2 — RLS policies use the strict `current_setting` form, on purpose

`current_setting('app.tenant_id')` raises when no tenant context is set. That
is deliberate: a missing context is a bug, and an error is better than silently
returning zero rows, which reads exactly like "this tenant has no data".

`api_keys` is the sole exception and uses
`nullif(current_setting('app.tenant_id', true), '')`, because resolving a key
is *how* a tenant gets established, so it is legitimately read before context
exists.

The `nullif` matters: a transaction-local `set_config` defines the GUC for the
whole session and reverts only its *value* at commit, so a pooled connection
that previously served a tenant sees `''` — and `''::uuid` throws just as an
unset one does. This cost an afternoon to diagnose.

---

## D3 — A business function is configuration, never code

Domain packs are YAML. Adding a domain must not mean editing agent code; that
constraint is what keeps expansion cheap.

Tested rather than trusted: the sales pipeline pack was added as two files with
an empty diff against the engine. Cash & runway did force two engine changes,
and both were genuine defects rather than cash being special — see D5, D6.

---

## D4 — The engine reasons in generic action slots

`none / monitor / investigate / intervene`. The pack supplies each slot's
label for its domain.

This is why `RETRAIN` never appears in a finance product and why the engine has
no idea what receivables are. A test asserts no ML vocabulary reaches the
customer surface; keep it.

---

## D5 — Some breaches are not cost-benefit decisions

A metric marked `existential` escalates on its own past its critical bound, and
the payback test is skipped.

Found by getting it wrong: the engine weighed "payroll is covered for 0.8
months" against a $1,200 cost of acting, found $42/day would not repay it
inside 21 days, and recommended *a review*. A business with three weeks of
payroll in the bank does not need a review. The downside of missing payroll is
not a daily carrying charge, so no daily rate can represent it.

Exactly one metric carries the flag today. Marking everything existential
turns the economics engine off, which is the failure this exists to prevent in
the other direction.

---

## D6 — Three economics models, because domains fail in different shapes

`exposure_scaled` (money at risk × rate), `shortfall_scaled` (obligations minus
what is available), `degradation_scaled` (volume × error rate × unit cost).

`shortfall_scaled` exists because cash has no reported at-risk fraction — no
owner records "the share of my bills I cannot pay". They record cash, and they
record what is due.

Each pack also supplies its own `exposure_noun`. Without it the engine
described every exposure as money "outstanding" — receivables vocabulary
leaking out of the one abstraction built to keep domains apart.

---

## D7 — Healthy bands adapt per tenant, but anchored

A tenant's history proposes a band; the pack's published band constrains how
far it may travel, as a fraction of the healthy-to-critical span. The critical
bound never moves.

The anchoring is the entire point. The obvious version of this idea is broken:
a business that has *always* run 40% of its book overdue would learn 40% is
normal and go quiet exactly when it should not. Pure "learn what's normal"
normalises dysfunction, and on business metrics dysfunction is often stable.

---

## D8 — No per-tenant neural network

The vision calls for an agent that restructures itself per business. The way
to deliver that is **retrieval over a sector-aware knowledge base, plus a
business-level reasoning graph, plus the calibration in D7** — not a model
per tenant.

An SME produces roughly 52 readings per domain per year. That supports trend
and seasonality; it cannot train a network. Thirty tenants across a dozen
domains would also mean hundreds of models to train, version, monitor and
debug — an operational load that would consume the company.

This is not a decision to skip ML. It is a decision about *which* machine
learning fits the data that actually exists.

---

## D9 — Staff can see fleet health freely; tenant contents need break-glass

`/v1/fleet` reads a database **view** owned by the migration role, which
bypasses the underlying tables' RLS. The app role has `SELECT` on the view and
nothing more, so staff code *cannot* reach a metric value by that path — the
view does not select one.

Tenant contents need a grant: one named person, one named organization, a
written reason, a hard expiry checked at use. No extend — a longer look is a
new grant with its own reason.

Opening a grant writes into **the customer's own audit log**. A staff-only
trail asks the customer to trust that we police ourselves; an entry in the log
they already read does not.

---

## D10 — The staff audit trail is append-only at the database

A trigger raises on `UPDATE` and `DELETE`, so the guarantee holds against the
application itself — which is what an attacker who reached the app would be
holding.

It raises rather than silently ignoring, because a swallowed `DELETE` leaves
the caller believing it worked, and that is how a bug hides.

---

## D11 — Staff and customer identities cannot cross

Staff tokens use a separate signing key *and* a separate issuer, so a customer
JWT presented to the brain and a staff JWT presented to a tenant endpoint each
fail two independent checks.

If the customer-facing signing key leaks, the blast radius is one
organization's sessions — not the ability to mint fleet-wide identity.

---

## D12 — Staff surfaces are separate applications

The main brain is its own ASGI app on its own port; the console is its own
Next.js app. Not route groups inside the customer ones.

"Is this endpoint staff-only?" is answered by which file it lives in, and the
customer deployment holds no credential that reaches the brain.

The console also looks deliberately unlike the customer product — flat, cold,
dense. That is a safety property: staff should never be even briefly unsure
which surface they are on.

---

## D13 — Bad readings are quarantined, never dropped

A customer whose data silently vanished has no way to find out why.
Quarantined readings are kept visible with their reasons and excluded from
diagnosis — a regression test pins the exclusion, after one leaked through and
produced a confidently wrong explanation.

---

## D14 — Explanations quote the band actually used

Found by getting it wrong: the diagnosis prompt quoted the pack's published
band while the engine scored against the tenant's calibrated one. The customer
would have read "your 60 days exceeds the healthy threshold of 45" about a
reading the agent had just called healthy.

A customer who spots that contradiction is right to stop trusting the rest of
the paragraph.

---

## D15 — The provider key must be a real environment variable

`litellm.completion()` reads `GEMINI_API_KEY` from `os.environ` itself.
Nothing here loads a `.env` into `os.environ` — pydantic-settings parses
`platform/.env` into its own object and stops.

A key written into that file is ignored, and the failure is silent: diagnosis
falls back to the deterministic generator forever, with nothing in the logs.
Check `/v1/usage/llm` — spend stuck at zero while decisions are being gated
means the key is not arriving.

---

## D16 — Nothing acts on a business system

Nano monitors, diagnoses and reports. The `mega` tier exists in the schema as
an upgrade seam and the API refuses to provision it.

That refusal is deliberate and should stay until Phase 8 is genuinely built.
An agent that acts on a real business without rollback, permissions and blast
radius limits is not a feature, it is a liability.

---

## D17 — Small branches, one PR each

Work happens on a branch per feature, merged promptly. This followed one
25-commit, 33,000-line PR that nobody could meaningfully review.

Commit messages carry the reasoning, not just the change. They are the most
reliable memory this project has — a future session reads them when this
folder is not enough.
