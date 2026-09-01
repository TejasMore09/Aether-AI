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

---

## D18 — Unvalidated claims are recorded but stay silent

`relations.yaml` states how one part of a business shows up in another. Unlike
everything else here, those are claims about the world rather than about
software, and no test can tell you whether one is true.

So each carries a confidence tier. `mechanical` is an accounting identity;
`strong` is a direct causal mechanism a competent advisor would reach for
first; `plausible` is a hypothesis nobody has checked against real data.

**Only `mechanical` and `strong` reach a customer.** A `plausible` relation
loads and matches, and `active(state, include_silent=True)` will return it —
but only so it can be tested once real data exists. Nothing that renders to a
customer may pass that flag.

This is what makes it honest to write down a guess before anyone has seen a
real company's books. Without the tier the choice would be between shipping
untested claims and not writing them down at all, and both are worse.

Every relation must also state its `mechanism` in plain business language;
the loader raises without one. A relation nobody can explain is one nobody can
audit, and being auditable is that file's entire value.

---

## D19 — A discovered correlation is evidence, never a finding

Three domains give a couple of hundred cross-domain metric pairs; an SME
reports perhaps a dozen times a year. At any conventional threshold you will
find several strong-looking correlations in pure noise, every run, for every
tenant. A product that surfaced those would generate confident nonsense at
scale, and would look most convincing exactly when it was most wrong.

So `correlation.py` splits its output. `evidence()` returns co-movements that
corroborate a relation declared in advance — the hypothesis was written before
the data was examined, which is what makes finding it meaningful.
`candidates()` returns undeclared patterns, for a human to read and
occasionally recognise. Neither may become a finding on its own.

Four defences underneath that, each load-bearing:

  - **First differences, not levels.** Two metrics that both drift correlate
    at 0.85–1.00 whether or not they are related. Measured: on the same data
    where levels correlate at −0.95, differences sit at −0.44 to +0.31 and are
    correctly refused.
  - **Spearman, not Pearson.** Business series are lumpy, and one large
    invoice can manufacture a Pearson correlation on a short series.
  - **|rho| >= 0.7 over at least 8 pairs**, enforced after differencing
    consumes one.
  - **No reading is paired twice** during alignment, or one cash reading would
    pair with six receivables readings and manufacture a correlation from a
    single observation repeated.

`spearman()` returns None rather than 0.0 on constant input: no correlation
*exists* there, which is different from "these do not move together".

---

## D20 — A cross-domain finding takes the largest exposure, never the sum

Each domain computes its own money at risk. Receivables might say $147 a day
and cash $26. The obvious combined figure is $173, and $173 is false.

The entire claim a cross-domain finding makes is that these are **one problem
measured twice** — the overdue book *is* the cash shortfall. Adding them counts
the same money in both places, which would inflate every such finding by
exactly the amount that made it worth raising, and would overstate most where
the domains are most strongly related. The better the product got at
connecting things, the more it would exaggerate.

So the headline is the largest single exposure, and the basis says so out
loud, naming the smaller figure and why it is not added. Understating quietly
would be its own dishonesty.

A relation may one day declare `exposure: sum` where its legs genuinely
describe separate money. Nothing does today, and the default is the
conservative one: being quietly understated is survivable in a system whose
job is to be believed; being enthusiastically overstated is not.

Severity is likewise the worst domain involved, not the average — a finding is
as serious as the most serious thing in it, and averaging would let one
healthy leg dilute a real crisis in the other.

Findings are ordered by money rather than by confidence. A merely strong claim
about a large sum deserves attention before a mechanical certainty about a
trivial one; the customer is deciding where to spend a morning, not grading
the epistemology.

---

## D21 — Suppression changes what is said, never what is recorded

Cross-domain findings create a problem the moment they work: a business whose
collections slow and cash tightens generates a receivables decision, a cash
decision, and a finding saying they are the same thing. Three messages about
one problem is worse than before any of it existed.

So a finding can subsume the notices it explains. Three rules keep that safe:

**Nothing is deleted.** Every domain decision still happens, still lands in
the audit trail, still gates a human where it should. Only the telling
changes. A system that hid a decision would trade the customer's
understanding for its own tidiness.

**A finding inherits the urgency of what it folded.** If receivables alone
would have demanded action, the finding replacing it demands action too.
Folding an urgent notice into a calm summary is the failure that would make
this feature actively dangerous.

**An existential breach is never folded.** Whatever else is true of a business
that cannot make payroll, the message about it must not arrive as a
subordinate clause in a summary about collections.

A notice is only folded when the finding genuinely explains it — the metrics
must overlap, not merely the domain. A book can be slow *and* disputed, and
suppressing the whole domain would hide the disputes.

Findings covering the same domains are also collapsed, which the tests found
rather than the design: two relations fired over the same pair quoting the
*same money*, because exposure is the largest single domain's either way. The
strongest confidence survives and names the other rather than repeating it —
and it absorbs the other's coverage, or the notices that sibling explained
fall through and get told separately, reintroducing exactly the duplication
the fold removed.

---

## D22 — No approximate vector index, and the measurement behind that

The knowledge base uses an exact scan. An HNSW index is the obvious addition
and would currently be a correctness bug, not an optimisation.

An approximate index answers "the k nearest rows in the table"; row-level
security filters *after* that. The index walks to the global nearest
neighbours, RLS discards everyone else's, and the query returns whatever
survives. Measured on this schema — a 40-row tenant beside a 6,000-row
neighbour, asking for 10 nearest:

    HNSW, hnsw.iterative_scan = off             0 rows
    HNSW, hnsw.iterative_scan = relaxed_order  10 rows
    exact scan                                 10 rows

Zero, silently. The small tenant's agent would simply have had less to say and
nobody could have told why.

At this size no index is needed: thousands of chunks per tenant, not millions.
When volume justifies one it needs `hnsw.iterative_scan` set on every
searching session, plus a test reproducing that table.

## D23 — The knowledge store relies on RLS alone, not RLS plus a WHERE clause

Every query in `knowledge/store.py` runs inside `tenant_session` and carries no
`tenant_id` predicate of its own. Belt-and-braces looks safer and is not: a
redundant filter in application code would make the isolation tests pass
whether or not the database policy worked. The day someone drops the policy in
a migration, every test stays green and the only real defence is gone.

One mechanism, tested directly — including tests that go underneath the store
and query the table, because an application-level assertion only proves the
application agrees with itself.

---

## D24 — Embeddings are computed locally, and never faked

**Local rather than an API**, and that is a product decision rather than a
cost one. This system's central promise is that one business's data is
unreachable from another's. Routing every decision, outcome and note through
an external embedding service would put all of it through a third party —
defensible for most products, awkward for one whose isolation story is the
thing being sold. `fastembed` over ONNX keeps it on our own machine, and
happens to be free and to work offline: ~50MB of runtime rather than torch's
~2GB.

**No fallback embedder.** If the model cannot load, embedding raises and the
knowledge base goes unwritten. A hashed or random fallback would produce a
store that answers every query confidently with nonsense, and nothing
downstream could tell the difference. An agent citing an irrelevant memory
with total assurance is worse than an agent with no memory at all.

---

## D25 — Relevance is judged relatively, because this model's range is compressed

Measured on `BAAI/bge-small-en-v1.5`, cosine similarity against "Days sales
outstanding is rising and cash is getting tight":

    near-identical restatement                  0.758
    same topic, different words                 0.575
    same domain, different subject              0.556
    unrelated finance (payroll ran fine)        0.550
    unrelated business (marketing campaign)     0.537
    nonsense                                    0.387

The gap between *same topic* and *entirely unrelated marketing copy* is 0.038.
That is noise. The model's recommended query prefix was tried and does not
help — it moved the spread from 0.221 to 0.215.

So no absolute similarity threshold can separate relevant from irrelevant
here: any cutoff admitting "same topic" also admits marketing copy. The
store's `max_distance` is for callers who know their own data and **must not
be used as a relevance filter**. `embedding.standout()` instead asks whether a
result is meaningfully closer than the rest of the candidates, which survives
a compressed range where a magic number does not.

The honest summary: this retrieves *"have we seen almost exactly this
before?"* reliably and *"is this vaguely related?"* not at all. For an agent
asking whether a situation has happened to this business before, the first
question is the useful one — but nothing downstream should claim more.

---

## D26 — The agent asks its memory a question written in its own template

Retrieval for the diagnosis prompt does not embed a free-form question. It
embeds `history.describe()` of the decision being explained — the identical
template that produced every memory in the store.

This looks like a shortcut and is the opposite. D25 measured that this model
finds near-duplicates and nothing else, so the *only* reliable way to match a
stored memory is to ask in the words it was written in. A hand-written query
("collections are slowing, has this happened before?") is the version that
quietly returns nothing.

The dependency runs both ways and is worth stating: changing the wording in
`history.describe()` changes what old memories can still be found. A backfill
after any such change is not housekeeping, it is a repair.

---

## D27 — Only standouts reach a prompt, and a young tenant therefore gets nothing

`knowledge/briefing.py` calls `worth_quoting`, never `search`. Since
`standout` needs candidates to compare against, a business with one prior
decision has none quoted, however apt it is.

That is a real cost and the right side to err on. A recalled precedent arrives
in an explanation the customer already trusts; an irrelevant one, quoted with
the same confidence, will be believed and acted on. Silence costs a sentence.

The obvious "fix" — quote the nearest memory when there is only one — is the
thing to not do. With one candidate there is no evidence of relevance at all,
only a nearest row, and this model's nearest row to anything is something.

---

## D28 — A recalled decision may never be described as having worked

Whether acting helped is not tracked anywhere (Phase 9.4). The prompt
instructions explicitly forbid the model from saying a past decision worked,
helped, fixed anything, or caused what followed.

Without that fence the model will supply it, because it reads naturally: "you
escalated collections in September and DSO recovered" is the most persuasive
sentence available and entirely unevidenced. It would also be the single
hardest claim for a customer to check.
