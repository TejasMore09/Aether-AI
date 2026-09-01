# Progress log

Newest first. One entry per thing a person would call "done" — not per commit.

Keep entries honest about what was *not* finished. A log that only records
wins is a log that stops being read.

---

## 2026-08-28 — Phase 2.4: a tenant's own history, indexed

`knowledge/history.py`. Gated decisions and how they were resolved become
memories the agent can find again.

Observations are deliberately not indexed. The numbers are already in the
database and queryable; the useful memory is *"we have been here before, and
last time you decided this"* — which lives in the approvals, not the readings.

**The wording is most of the work.** This embedding model matches
near-duplicates and little else (D25), so two similar situations have to
*read* similarly or retrieval will never connect them. Every memory is
therefore built from one fixed template rather than written freely — a
constraint imposed by the tool, not a stylistic choice. A test pins it: two
comparable decisions must share over 80% of their words.

**The LLM explanation is kept but never embedded.** It is the richest thing
attached to an approval and the worst thing to vectorise — long, variable,
phrased differently every time, which is exactly what drowns a near-duplicate
signal. It lives in `meta` for display.

**Nothing claims to know how a decision turned out.** Outcomes are not tracked
anywhere yet — that is Phase 9 — so a memory says what was decided and stops.
A test asserts the sentence never contains "worked", "helped", "as a result"
or similar, because an agent implying it knew would be inventing the most
valuable part.

Re-indexing updates rather than accumulates, since a backfill will be run
repeatedly. Embedding is batched: loading the model dominates, so two hundred
decisions should pay that cost once.

335 tests, none skipped.

---

## 2026-08-28 — Phase 2.3: tenant-scoped retrieval

`knowledge/retrieval.py` — what the rest of the system calls. Embeds a
question, searches one tenant, marks which results are worth quoting.

**Reading and writing fail differently.** Writing without a model refuses (a
fake vector poisons the store). Reading without one returns nothing, because
an agent with no memory is where every tenant starts — raising would turn a
perfectly good diagnosis into none at all over an optional enrichment.

`worth_quoting()` is separate from `search()` because search always returns
*something*, and an agent that quotes its nearest memory regardless of how
near it is will eventually cite an irrelevant one with total confidence.

The isolation tests attack rather than assert, since a single-query check can
pass while production leaks:

  - twenty tenants, not two — two can pass by luck
  - eight threads interleaving two tenants across a shared connection pool.
    The case a sequential test cannot see: context is transaction-local via
    `set_config(..., true)`, and were it session-local instead, every other
    isolation test would still pass while production leaked the moment two
    tenants were served at once
  - thirty perfect matches belonging to a neighbour against one poor match of
    our own, so distance cannot outrank ownership
  - the same again with the real model, so the query genuinely resembles the
    neighbour's memory rather than only arithmetically

Those last ones also validate `standout()` on real embeddings rather than on
chosen distance arrays: a near-duplicate is found and marked quotable, and a
business remembering nothing like the question gets results from `search()`
and none from `worth_quoting()`.

318 tests, none skipped.

**Housekeeping:** the position marker in `PLAN.md` had been empty since Phase
1 closed. A `str.replace` whose pattern did not match had silently done
nothing, in the one document whose entire job is telling a cold session where
it is. Every roadmap edit now asserts that it landed.

---

## 2026-08-28 — Phase 2.2: local embeddings

`knowledge/embedding.py`. fastembed over ONNX with `BAAI/bge-small-en-v1.5`,
384 dimensions to match the column. ~50MB of runtime rather than torch's 2GB,
12s cold load, 0.22s for three texts.

Local by decision, not thrift — see D24. Routing a customer's decisions and
outcomes through an external embedding service is hard to defend in a product
whose pitch is that their data is unreachable from anyone else's.

**No fallback embedder anywhere.** If the model cannot load, embedding raises
and the knowledge base goes unwritten. A hashed fallback would answer every
query confidently with nonsense and nothing downstream could tell.

**Measured the model's limits before designing around them**, and they are
worse than expected. Unrelated marketing copy scores 0.537 against a
receivables query, while genuinely same-topic text scores 0.575 — a gap of
0.038. The recommended query prefix was tried and did not help. So absolute
similarity thresholds are close to useless here, and relevance is judged
relatively via `standout()`. See D25 for the full table.

That limitation is documented in the module rather than left to be
rediscovered by someone wondering why retrieval surfaces irrelevant memories.

Tests split: 10 logic tests that need no download, 3 marked `slow` that
exercise the real model and skip if it is absent. A fresh clone runs the suite
in seconds and still gets the real thing where the model exists.

306 tests, none skipped.

---

## 2026-08-28 — Phase 2.1: the agent knowledge base exists

Migration 0009, `core/models.py`, `knowledge/store.py`. pgvector enabled for
the first time — it had been in the Docker image since the beginning and the
extension was never created.

`knowledge_chunks` is tenant-scoped with the same RLS discipline as every
other tenant table, and registered in `RLS_TABLES`. It is the only tenant
table holding sentences rather than numbers, so a cross-tenant read here would
be a disclosure rather than a statistic — the 16 tests are the most paranoid
in the repository, and several go underneath the store to query the table
directly.

**Measured rather than assumed:** an HNSW index would be a correctness bug
here, not an optimisation. A 40-row tenant beside a 6,000-row neighbour, asking
for 10 nearest memories, gets **0 rows** with the index and iterative scans
off. Silently. See D22 for the full table. We ship an exact scan.

Also D23: the store relies on RLS alone rather than adding its own tenant
predicate, so the isolation tests prove the policy rather than the filter.

Embeddings are supplied by the caller for now; the pipeline is 2.2. Dimension
is fixed at 384, and a wrong-sized vector raises rather than being reshaped —
padding would bury an embedding-layer bug behind plausible-looking results.

293 tests, none skipped.

---

## 2026-08-28 — Phase 1.8, and Phase 1 complete

`tests/test_cross_domain_e2e.py`. Readings pushed through the real API, real
database, real RLS. 277 tests overall, none skipped.

Isolation is the test that matters: two tenants reporting the *same* domain,
one in trouble and one healthy. Different domains could pass by accident; the
same one cannot. It also asserts neither tenant's balance figure appears in
the other's view, which a domain-name check would miss.

**The first seed produced no findings at all**, and the reason is worth
keeping. It had the business declining across the entire window, so
calibration adapted and the decline became its normal — D7 working exactly as
designed. Real deterioration happens against a period of normality, so the
seed is now eight steady periods then five bad ones. Test data invented for
convenience had been quietly unrealistic.

**Found a real gap in the quality gate.** A reading of `ar_total: 0` with
`overdue_ratio: 0.45` passed every check. A share of a book that does not
exist is undefined, not low — and since Phase 1, `overdue_ratio` is a leg of a
cross-domain relation, so a nonsense value could satisfy half a finding about
the whole business while carrying no money at all. Now an error.

Also corrected: the `dso < 15 with overdue > 0.5` rule is a warning, not an
error, so a reading built on it is accepted. The test had assumed otherwise
and was skipping rather than asserting.

The plausible-relation guard could not be provoked here — that relation spans
sales and receivables, and the sales pack is on the unmerged PR #4. Rewritten
to assert the invariant over whatever findings the API produces, so it stays
meaningful as packs land.

---

### Phase 1 closed

A business with slowing collections and tightening cash now receives **one
message instead of four**, naming both domains, quoting the largest single
exposure rather than a misleading sum, carrying the mechanism in plain
language, and corroborated by that tenant's own history where it exists.

Six defects were found by running it rather than by reading it: two exposure
contradictions, a duplicated prompt paragraph, lost coverage on dedupe,
discarded readings and evidence, and a dashboard headline that said
"everything is tracking normally" above a live finding.

---

## 2026-08-28 — Phase 1.7: findings on the dashboard

`GET /v1/business` on the agent runtime, and a `ConnectedProblems` section
that leads the Overview page.

Given its own treatment rather than another per-domain card: the whole value
is the claim that two symptoms are one problem, and rendering it in the same
shape as the cards underneath would bury the only thing worth reading. The
mechanism is shown in full rather than truncated behind a link — it is the
reasoning, not decoration, and a customer who cannot see why we connected two
numbers has been asked to take it on trust.

The exposure basis is shown too, because a reader who assumed we had added the
two domains together would think we were overstating, and be right to.

**Found by looking at it:** the page said "Everything is tracking normally"
directly above a connected problem quoting $54.56 a day at risk, and the
"Exposure if unaddressed" figure read $0. Both headline numbers were computed
from gated approvals alone and ignored findings entirely. That kind of
contradiction teaches a customer to stop reading the headline.

Fixed both. The exposure figure is now the *larger* of gated exposure and the
biggest finding, never their sum — a gated receivables decision and a finding
naming receivables measure the same money, so the D20 reasoning applies here
too.

Verified end to end against a seeded tenant: twelve fortnights of slowing
collections and tightening cash, through the API, rendered in the browser,
zero console errors.

Incidentally confirmed the 1.3 trend guard on my own seed data: perfectly
linear trends have constant first differences, so Spearman is undefined and the
finding correctly reported "not corroborated" rather than inventing support.

---

## 2026-08-28 — Phase 1.6: the prompt sees the whole business

`business/briefing.py`, wired into `services/diagnosis.py`. An explanation of
slowing collections can now say what it is doing to cash, instead of
describing one domain and leaving the customer to notice.

The block states the arithmetic rather than implying it. It carries two
exposure figures, and a model handed two numbers will add them — which would
contradict the engine's own figure inside the explanation of the engine's own
decision. Same failure as D14, so it says outright: largest single exposure,
not a total, never add them.

Economy matters because tokens are metered per tenant. Connected domains and
impaired domains go in; healthy unconnected ones do not, because they cost
budget to teach the model nothing. Silent domains are named with an explicit
instruction not to read anything into their absence.

Gathering is wrapped in a try: a diagnosis that explains one domain well beats
no diagnosis because the cross-domain layer had a bad day.

**Found by running it:** the block rendered the same $54.40 paragraph twice
with two mechanisms. Deduplication lived in `presentation.apply`, and the
prompt layer had gone around it by calling `for_business` directly. Moved
dedupe into `for_business`, so no caller can route around it.

Fixing that exposed two more losses the tests caught: a folded sibling's
readings and its corroborating history were being discarded. The survivor now
absorbs both — otherwise the surviving explanation quotes fewer numbers than
the engine actually used.

15 tests. 264 overall, none skipped.

---

## 2026-08-28 — Phase 1.5: suppression

`business/presentation.py`. A cross-domain finding can now take over the
telling of the single-domain notices it explains.

Measured end to end: a business with slowing collections and tightening cash
went from **4 messages to 1**, and the surviving message kept the HIGH risk
level and approval gate it inherited.

This is the one feature here that makes the product say less, so its failure
mode is different from everything else: a missed fold costs a redundant
message, a wrong fold costs the customer the message they most needed. Hence
the rules in D21 — nothing deleted, urgency inherited, existential breaches
never folded, and overlap required rather than a shared domain name.

**Found by the tests, not the design:** two relations fired over the same pair
of domains quoting the *same money*, because a finding's exposure is the
largest single domain's either way. So findings covering identical domains are
collapsed too, strongest confidence surviving and naming the other.

The first attempt at that broke coverage — the survivor did not inherit the
dropped finding's legs, so notices the sibling would have explained fell
through to standalone and got told separately. Six tests caught it. Survivors
now absorb `also_covers`.

17 tests, no database. 249 overall, none skipped.

---

## 2026-08-28 — Phase 1.4: cross-domain findings

`business/findings.py`. A matched relation plus the business state becomes one
finding naming several domains, with a combined exposure figure.

Detecting the pair was the easy half. The hard part was the money, and the
obvious answer is wrong: summing the per-domain exposures counts the same
pounds twice, because the claim being made is that they are one problem
measured from two sides. Worse, it would overstate most exactly where the
relationship is strongest. See D20.

The headline is the largest single exposure, and the basis says so, naming the
smaller figure and why it is not added — understating quietly would be its own
dishonesty.

Exposure is computed with the same function the single-domain decision uses,
now public rather than private. If the two disagreed for the same reading, a
customer would be right to trust neither. DomainSnapshot carries the tenant's
resolved PolicyParams for the same reason.

Corroborating co-movements from 1.3 attach to a finding when they support that
specific relation. Absence is not weakness: most tenants will never have enough
history for the correlation pass to say anything either way.

20 tests, no database. 232 overall, none skipped — Docker came back.

---

## 2026-08-28 — Phase 1.3: correlation against a tenant's own history

`business/correlation.py`. Asks whether *this* company's history actually
shows the patterns `relations.yaml` claims in general.

The naive version of this feature is worse than not having it, and that shaped
everything: a couple of hundred cross-domain pairs against a dozen readings
will surface strong-looking noise on every run for every tenant. See D19.

Output is split. `evidence()` corroborates relations declared in advance;
`candidates()` reports undeclared patterns for a human, never a customer.
Neither becomes a finding alone.

Measured rather than asserted — on two independent trends with light noise,
levels correlate at −0.95 to −1.00 while differences sit at −0.44 to +0.31 and
are refused. That test runs five seeds, because one draw proves only that one
sample behaved.

Spearman and ranking written out rather than adding scipy: two short functions
over a dozen points, and the arithmetic is worth being readable here.

20 tests, no database needed. 212 overall.

**Note:** Docker Desktop stopped unprompted twice today, so the 81
database-backed tests skipped on the final run. They passed earlier in the
session; the correlation work itself needs no database.

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
