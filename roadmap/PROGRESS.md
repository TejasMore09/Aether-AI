# Progress log

Newest first. One entry per thing a person would call "done" — not per commit.

Keep entries honest about what was *not* finished. A log that only records
wins is a log that stops being read.

---

## 2026-08-28 — Phase 1.2: cross-domain relations

`business/relations.yaml` and `business/relations.py`. Four relations across
the three existing domains, each stating in plain language why the link
exists.

This is the first file in the project that makes claims about how businesses
work rather than how software should behave, and nothing in the test suite can
tell you whether one of them is true. A wrong relation does not crash — it
tells a real company that two unrelated numbers are one problem, and they
believe it because the system sounds certain.

The answer is confidence tiers, and the rule that **`plausible` relations
never reach a customer**. They load, they match, and `include_silent=True`
returns them purely so they can be checked once real data exists. See D18.
That is what makes it honest to write a guess down rather than either shipping
it or losing it.

Relations shipped:

  mechanical  overdue book uncovers obligations  (receivables ↔ cash)
  strong      collections slowing drains cash    (receivables ↔ cash)
  strong      thin pipeline precedes thin cash   (sales ↔ cash, lagged)
  plausible   pressure to close buys worse terms (sales ↔ receivables) — silent

The lagged one carries a `lag_note`, because pipeline weakness reaches cash a
quarter later; treating that as simultaneous would keep diagnosing the wrong
cause.

22 tests, most of them negative — good news never fires a relation, stale data
cannot join one, a partial match is not a weak match, and an unvalidated claim
stays quiet. 192 overall.

**Still not real:** every one of these is reasoned rather than observed. The
mechanical one is close to arithmetic and the two strong ones would be
uncontroversial to an accountant, but none has been checked against a company's
actual books.

---

## 2026-08-28 — Phase 1.1: the business object

`aether/business/state.py`. `BusinessState` holds every domain a tenant
reports, gathered in one query; `DomainSnapshot` describes each one.

Deliberately inert — it gathers and describes, and decides nothing. Keeping
the gathering separate from the reasoning means cross-domain findings can be
tested against a hand-built state without a database, which is exactly what
saved this task when Docker went down mid-work.

Two ideas worth keeping:

  - **Severity, not raw performance.** 0.74 is comfortable against a floor of
    0.72 and a real problem against one of 0.92, so ranking domains by
    performance would put cash last precisely when it matters most. Severity
    is distance below each domain's own floor, and is zero — not a small
    number — while healthy.

  - **Stale domains are excluded from impairment.** A reading too old to
    decide on is too old to call impaired; counting it manufactures a problem
    out of missing data.

Also carries `silent`: domains a tenant configured that have never reported.
Configured-and-silent is a setup failure and looks exactly like healthy unless
something names it.

**Tests split.** 16 pure-logic tests with no database, plus a separate
`test_business_state_db.py` for `load()`. Reasoning should not need
infrastructure to verify — these run in under a second on any machine.

**Verified** once Docker was back: 13 database-backed tests pass, including
cross-tenant isolation and the refusal to treat a quarantined reading as the
business's current position. 170 tests overall, none skipped.

One of those tests had been driving the monitoring endpoint, which needs
Temporal, so it skipped on a machine where the feature worked fine. `silent`
is derived from `PolicyConfig`, so it now configures a policy directly — the
same principle that split the pure tests out in the first place: do not
require infrastructure that is not part of what is being tested.

Also fixed, unrelated: `test_garbage_keys_are_refused` had no database guard,
so it failed where its neighbours skipped. A suite whose result depends on
whether Docker happens to be running is a suite people stop trusting.

---

## 2026-08-28 — Roadmap folder created

Phase 0 assessed as complete; Phase 1 started.

The prompt for this was a blunt question — how far is this from the product I
described? — and the honest answer needed writing down rather than saying once
in a conversation that will be discarded.

**Assessed position:** roughly 70% of "a robust multi-tenant monitoring
platform", roughly 15% of the vision in `VISION.md`. The gap is the
distinctive half: no knowledge base, no sector awareness, no cross-domain
reasoning, no forecasting.

Verified rather than assumed — each of those returned nothing when searched
for. `pgvector` is in the Docker image and the extension has never been
created.

---

## 2026-08-28 — Repository cleaned, prototype removed

74 files, 12,919 lines: `api/`, `database/`, `adaptation/`, `features/`,
`frontend/`, `models/`, `scripts/`, `main.py`, `aether.db`, `mlflow.db`.

The repository had contained two systems — an MLOps prototype built around
drift detection and retraining, and the platform that replaced it — and anyone
opening the root found the wrong one first. PR #3 had been closed a week
earlier precisely because it was editing code nothing called.

Verified dead before removing: nothing under `platform/` imported any of it,
CI already only built `platform/**`, and `aether.db` only kept appearing as
modified because `database/db.py` opened it on import.

Also retired five secrets, since `api/services/` was the sole consumer of each.
`GEMINI_API_KEY` is now the only secret this project needs.

Also fixed: `.env.example` never mentioned the provider key, and getting it
wrong fails silently. See D15.

**Working copy moved** to `C:\dev\Aether-AI`, out of the Google Drive synced
folder. Drive had been syncing a live `.git` directory; `git gc` took the
repository from 748MB to 36MB, almost all unreachable loose objects.

---

## 2026-08-27 — Sales pipeline pack (domain three)

Two files, zero engine changes — the diff against `policy/`, `pack.py` and
`derive.py` was empty, and a test asserts that.

This was the domain that had to justify cash breaking the engine. It is also
the hardest case for a published band anywhere in the product: a referral firm
closing half its quotes and an outbound firm closing one in twenty are both
healthy, and judged against each other either looks broken.

**Not real:** the thresholds were tuned against invented scenarios until the
ladder looked sensible. That is not validation.

---

## 2026-08-27 — Cash & runway pack, and two engine gaps it exposed

Domain two, and the one that broke the engine twice — both genuine defects.

`shortfall_scaled` economics, because no owner reports the fraction of bills
they cannot pay. And `existential` metrics, because the payback test weighed
"payroll covered for 0.8 months" against $1,200 and recommended a review.

See D5 and D6.

---

## 2026-08-27 — Per-tenant calibrated bands

The pack already claimed a tenant's baseline superseded its defaults. That was
true for drift and false for health: every business was judged against one
fixed band, so a supplier on 60-day terms scored 0.67 on every reading it
would ever submit.

Anchored so a chronically unhealthy business cannot normalise its own
dysfunction. See D7.

Also fixed a contradiction it exposed — explanations quoted the pack's band
while the engine used the tenant's. See D14.

---

## 2026-08-27 — Main brain and staff console

Fleet control that does not cost tenants their privacy: an aggregate-only
database view, break-glass grants with written reasons mirrored into the
customer's own audit log, and an append-only staff trail enforced by a
trigger.

The break-glass gate was mutation-checked — stubbing it to always pass fails
five tests, so they are load-bearing rather than decorative.

Console built as a separate Next.js app, deliberately unlike the customer
product. See D9 through D12.

---

## 2026-08-26 — Ingest API keys and the Connections page

Per-tenant credentials so an unattended connector can push readings without
borrowing a human's session. SHA-256 rather than bcrypt, deliberately: these
are 256-bit CSPRNG tokens, so there is nothing to brute-force.

Verified by running the page's own printed curl verbatim, then confirming the
same key got 401 on the audit trail.

---

## Earlier — Phase 0 foundation

Multi-tenant platform with Postgres RLS, control plane, agent runtime, domain
pack format, cost-aware decision engine, quality gate with quarantine,
Temporal monitor loop, LLM diagnosis with fallback, receivables pack, customer
dashboard.

Detail lives in the commit history, which carries the reasoning.
