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

---

## D29 — Throttling state lives in Postgres, not Redis

Redis is already in the compose file, so this looks like the wrong choice. It
is not, and the reason is the failure mode rather than the throughput.

Throttling sits inside the authentication path. Redis down and failing open
makes the mechanism decorative exactly when someone is hammering the service.
Redis down and failing closed makes a cache the single point of failure for
every login on the platform. Postgres introduces neither, because login
already cannot proceed without Postgres — there is no new way to fail. The
cost is one indexed upsert next to a bcrypt verification that already takes
about 100ms.

Revisit this only if login volume makes the write measurable, which at 30
tenants it will not.

---

## D30 — Per-address throttling stays off until a deployment can name the client

Both front ends are back-ends-for-front-ends: the browser never reaches the
API, so `request.client.host` is one Next.js server for every customer on the
platform. Throttling on it puts the entire customer base in a single bucket,
where twenty bad guesses by one attacker locks out everybody. That is an
outage wearing the costume of a security control.

Believing `X-Forwarded-For` instead is the opposite failure: without something
in front that overwrites it, every attacker gets a fresh identity per request
and the scope becomes theatre.

Neither is inferable at runtime, so `AETHER_CLIENT_IP_SOURCE` states which is
true (`none` | `socket` | `forwarded`) and defaults to claiming nothing.

**The cost of this is real and must not be forgotten:** password spraying —
one guess each against a thousand accounts — is not currently defended,
because the per-account counter never fires. Setting the variable once 6.1
puts a proxy in front is what closes it. Do not "fix" this by defaulting to
the socket address; that is the outage.

---

## D31 — Aether targets India, the US and Europe from the start

Not one market first. That is a larger commitment than it sounds and the
consequences are worth stating before Phase 3 starts, because two of them are
structural.

**The sector taxonomy cannot be borrowed.** India uses NIC, the US uses
NAICS (and SIC in SEC filings), Europe uses NACE. Adopting any one of them
makes the other two second-class. So Phase 3.1 defines a *coarse Aether
taxonomy* — tens of sectors, not hundreds — with a crosswalk to all three.
The crosswalk is also what lets a US-derived band (Damodaran, SIC-shaped)
apply to an Indian tenant, which we would need anyway.

**Money is not a float any more.** Every monetary column and figure in the
system is USD by name: `expected_loss_usd`, `cost_usd`, `$71.89 a day`. An
Indian SME thinks in rupees and a German one in euros, and an explanation
quoting dollars at either is not slightly wrong, it is unusable. Multi-currency
is now a Phase 3 prerequisite rather than a nicety — see PLAN 3.0.

**GDPR is an obligation, not a feature.** Serving Europe makes 6.8 mandatory
and constrains where the database may physically live. Data residency is now a
hosting decision with legal weight rather than a latency preference.

Also differing and cheaper to handle: fiscal year ends (India runs April to
March), date formats, and statutory filing calendars — which matters if a
compliance domain is ever built.

---

## D32 — Domains are chosen by how replaceable the job is, hardest one included

Tejas's framing, and it is a better selection rule than "what is easy to
build". In IT, the roles automated first were the ones with clear inputs and
an agreed definition of done — frontend, UI work — while senior engineering
held out. The same gradient exists inside a small business, and Aether should
target the replaceable end first *and stay several steps ahead of it*, which
means the pack must do what the clerk's manager does, not what the clerk does.

Six domains, deliberately not all easy:

| Tier | Domain | The job it stands in for | Status |
|---|---|---|---|
| Easy | Receivables | Credit controller / AR clerk | built |
| Easy | Cash & runway | Bookkeeper's cash reporting | built |
| Easy | **Payables & supplier terms** | AP clerk | **next** |
| Medium | Sales pipeline | Sales ops analyst | built |
| Medium | **Inventory & stock cover** | Stock controller | **next** |
| Hard | **Customer concentration & credit risk** | A good CFO's judgement | **next** |

Three reasons this particular set, beyond the tiering:

**Two of the three new bands are already in hand.** The Damodaran file at
`reference/` carries `Acc Pay/Sales` and `Inventory/Sales` alongside the
receivables figure already being used. Payables and inventory need no data
that does not already exist in the repository.

**Together they complete the cash conversion cycle.** DSO + DIO − DPO is the
standard working-capital measure an SME's own accountant uses. Receivables
alone is a third of it. With all three, Aether can say something an owner has
heard before and can check — which is worth more than a novel metric.

**The hard one needs no new ingestion.** `top5_concentration` is already a
metric on the receivables pack, and Phase 1's cross-domain machinery already
exists. "Your largest customer is 40% of the book and paying later than they
used to" is precisely the judgement a clerk does not make and a good finance
lead does — the five-steps-ahead case, reachable with data already flowing.

Workforce/HR is the obvious other "hard" candidate and is deliberately *not*
first: it needs data most SMEs do not hold, and "healthy attrition" is
genuinely contested, so it would mean inventing bands. It comes after real
data exists.

---

## D33 — The platform never converts currency

No FX rate is stored, fetched or applied anywhere in Aether, and adding one
should be treated as a significant decision rather than a convenience.

A rate is a fact about a moment. A stale one does not fail — it silently
produces figures that look right, and those figures go into explanations a
customer reads and decisions they act on. There is no way to notice
afterwards, and no way to explain to a business why the number they were shown
in March is not the number in the audit log.

Each business reports in one currency and it stays there. Most of the product
is already currency-neutral, which is what makes this cheap: DSO is days,
overdue share is a fraction, coverage is a ratio. Only money is affected.

The consequence to accept rather than work around: the fleet view cannot show
a single total across tenants in mixed currencies, and should not pretend to.
`month_spend_usd` is exempt because it is genuinely our cost in dollars.

If a business ever genuinely needs multi-currency *within itself* — a UK
company invoicing in euros — that is a different and much larger problem than
this, and it still does not require Aether to hold a rate.

---

## D34 — Two kinds of money, spelled differently on purpose

`expected_loss` carries a currency and may be rupees. `LLMUsage.cost_usd`
keeps its name because what a diagnosis costs *us* at the model provider is
billed in dollars whoever the tenant is.

They were previously spelled the same, which is how every figure on the
dashboard came to be a dollar amount regardless of who was reading it. Keeping
the `_usd` suffix on genuinely-dollar values is not an oversight to tidy up
later: it is the thing that stops the two being merged again.

The same split runs through both front ends — `money(value, currency)` for the
customer's money, `usd(value)` for platform spend.

---

## D35 — Aether has its own sector taxonomy, as coarse as the evidence allows

Serving India, the US and Europe (D31) means NIC, NAICS and NACE are all
first-class, and adopting any one demotes the other two. They are also far
finer than anything we can justify: NACE has hundreds of classes, NAICS over a
thousand, and defensible band data exists for roughly ninety industries.

**A taxonomy finer than the evidence is false precision.** Two sectors would
appear different on screen while being seeded from the identical number, and a
customer would reasonably read that difference as knowledge. So the rule is:
split a sector only when there is data showing the split matters. Twenty-one
sectors today.

The worked example is software versus IT services. The official
classifications do not separate them — ISIC 62 is both — but the reference
data puts them seventeen days apart on DSO (about 61 against 78). That gap is
material for a band, so both exist, and `sectors.yaml` declares which one an
ambiguous code resolves to. Loading fails if any shared code lacks that
declaration, so the choice cannot be made by iteration order.

**The crosswalk has two columns, not three.** NIC 2008 is identical to ISIC
Rev. 4 to four digits; NACE Rev. 2 is ISIC with European sub-divisions,
compatible at two. One list of ISIC divisions serves India and Europe. Only
NAICS needs its own.

Ambiguous codes resolve to the *more forgiving* band where there is a choice.
A business judged slightly generously is a missed alarm; one judged by a
stricter sector's band is a false alarm, and at this stage a false alarm costs
more trust than a missed one.

---

## D36 — A sector may say it has no band, and financial services does

`bands: unavailable` is a first-class state, not a gap to fill in later.

Measured on the reference table: banks compute to 0 days, brokerage to 512,
non-bank financial services to 4,863 — and four financial industries carry
blanks exactly where a working-capital figure belongs. Reported revenue in
these businesses is not comparable to what they are owed, so the arithmetic
that works everywhere else produces nonsense.

Seeding anyway would put a number wrong by a factor of thousands in front of a
customer. So the sector exists, carries no band, states why in a sentence the
product can show, and falls back to the pack's general bands.

Note where this bites: a stock brokerage is the vision's own example of a
sector-aware agent, and it is precisely the sector no reference data answers
for. Real bands there need real businesses, not a better dataset.

---

## D38 — Reference data is committed as CSV, with the workbook kept as the receipt

The Damodaran workbook is a binary blob. Committed alone, next January's
edition produces a diff that says "51200 bytes differ" — a band could move
thirty days and no reviewer would see it.

So `reference/extract.py` converts it to CSV, and the CSV is the artefact of
record: it is what the code reads, what a person reviews, and what the sector
crosswalk is tested against. The workbook stays alongside as provenance, and
the script keeps the two honest.

This also removed a dependency and a skipped test. Reading the workbook needed
`xlrd`, which was not installed, so the check that every `damodaran:` entry
actually exists — the one that catches a typo silently seeding no band — was
skipping. A test that skips on the machine that runs it is not a test.

---

## D39 — The sector band is clamped, and the clamp is what makes it honest

A sector's reference figure may move the healthy bound only as far as the
pack's existing calibration allowance — the same limit a tenant's own history
gets, for the same reason.

The reference table describes US *public* companies. An SME's levels are
simply different: smaller firms have worse terms and less leverage over
customers. What does transfer is the **ordering** across sectors — grocery
retail collects in days, engineering firms in months. Clamping takes the
ordering and declines the level, which is precisely the distinction
`roadmap/DATA.md` records about this source.

The worked case is retail. Published retail DSO is 6.4 days; judging a corner
shop against that would flag every ordinary week. Clamped, retail lands at 18
days — still far stricter than the pack's 45, without betting on 6.4 being
true of a shop in Nashik.

Where the clamp bites, the band says so in its `basis`, because a customer
looking at an unexpected verdict deserves to know the reference and the pack
disagreed.

The layering is pack → sector → tenant, each anchored to the one beneath. Once
a tenant has enough history their own number wins outright, which is correct:
eight months of their readings is better evidence about them than an industry
average. The sector then stops changing the answer and only bounds how far
their history may move it.

---

## D40 — Marketing has no sector band either, and this was measured

The only industry matching creative agencies is Advertising, whose implied DSO
is 172.9 days and implied DPO 168.3. Agencies carry clients' gross media spend
as both receivable and payable while reporting only commission as revenue, so
*every* working-capital figure in that row is inflated, not just one.

Seeding it would tell every agency that half a year to collect is normal.

No defensible adjustment exists. Inventing a multiplier to bring 173 days down
to something plausible would be exactly the confident guessing this project
refuses, so the sector declares `bands: unavailable` with the reason and uses
the pack's general bands.

Two of twenty-one sectors now say they do not know: financial services (D36)
and marketing. That is not a gap to close by finding a better dataset — both
need real businesses.

---

## D41 — A sector change moves future readings only, never past ones

Bands are stored on each observation when it is ingested, so changing sector
does not re-score anything already recorded.

This is deliberate and it is the same reasoning that stamps currency onto an
approval (D31). Re-scoring history under a new sector would silently rewrite
verdicts a customer has already seen, possibly acted on, and possibly
discussed with their accountant. A number in the audit log that changes
because a dropdown moved is not an audit log.

The consequence is stated on the settings page rather than hidden: readings
already stored keep the band they were judged against, and only new readings
change. The change itself is written to the tenant's own audit log, so an
unexplained shift in verdicts is traceable to the day somebody changed it
rather than looking like the agent became erratic.

---

## D42 — `/api/sectors` is reachable without a session, and that list is a disclosure decision

The signup form needs the sector catalogue before anyone has an account, so
the BFF exposes one unauthenticated route and `proxy.ts` lets it through.

That is safe for exactly the reason `/explore` is: the catalogue holds no
tenant data at all, only what the platform can and cannot judge. It is not
safe because it is convenient, and the distinction matters because
`PUBLIC_PATHS` is the kind of list that grows by habit. Anything added there
must be checked to be genuinely tenant-free first — the comment in `proxy.ts`
says so at the point where somebody would be tempted.

---

## D43 — A sector's industries must agree before their median is treated as evidence

Found while building 3.4, after 3.2 had already shipped the bug.

The construction sector named Engineering/Construction and Homebuilding. The
first bills clients and waits **100 days** holding almost no stock; the second
sells houses for cash in **7 days** and holds **226 days** of land. Their
median is 54 days, which describes neither, and Aether was presenting it as
what is normal in construction.

**The median does not protect against this.** It defends against one distorted
industry among several — advertising among a group — but with two values the
median sits exactly between them, and between two opposites is nowhere.
Averaging opposites is a different failure and needed a different guard.

`reference._represents` requires at least half a group's values to sit within
25% of their median. That admits a group where most agree and one differs (three
building-supply industries, where a retail outlier is correctly ignored) and
refuses one where nothing is near the middle. Three sectors lost their
receivables band as a result — construction, wholesale and healthcare — and
each now says why.

The general lesson, worth carrying into Phase 5: **a sector is a claim that its
industries are alike.** Where the data says they are not, the sector is drawn
wrongly or the evidence does not reach it, and either way an average is the
wrong answer.

---

## D44 — Sector knowledge is looked up, not searched, and the corpus says so

A tenant has exactly one sector. Asking a vector index which sector they are in
returns the only candidate and calls it a match — theatre, and the kind that
demos well.

Similarity earns its place where there are many memories and the question is
which few are relevant. Where the answer is "the one", `store.of_kind` is the
honest mechanism.

It is still written into the knowledge base rather than computed on demand,
for three reasons: it is genuinely part of what the agent knows, it must show
up in the chunk counts the fleet view reports (2.6), and the corpus is where
real industry documents land once Phase 7 brings document ingest. At that
point similarity starts doing real work here, and this stays correct.

**Every sentence is derived from the committed reference table.** Nothing is
written from general knowledge, however plausible. "Construction businesses
have long payment cycles because of retentions" is probably true and cannot be
cited, and a knowledge base mixing citable figures with confident-sounding
invention is worse than one with fewer facts — nothing downstream can tell
which is which.

---

## D45 — Metrics scope by sector *traits*, not by lists of sectors

A metric declares what a business must be like for the metric to mean
anything: `requires_traits: [invoices_customers]`. Sectors declare what they
are like. Neither names the other.

The alternative — a metric listing the fifteen sectors it applies to — has a
silent failure mode. Adding a sixteenth sector means editing every such list,
and forgetting means the metric quietly stops applying to a business it should
cover, with nothing to notice. A sector declaring its own traits is checked at
load: omitting `traits` is a startup error, not a default.

Both sides are validated. An unknown trait on a sector or on a metric fails
when the file loads, because a misspelled trait makes the metric apply to
nobody, which is indistinguishable from a metric correctly scoped to a sector
that happens to have no tenants.

`KNOWN_TRAITS` is deliberately one entry long. A trait earns its place when a
metric actually depends on it; inventing a taxonomy of business properties in
advance is how configuration becomes fiction.

**The concrete case, which is why this is not speculative.** Top-five customer
concentration is a real risk for a wholesaler — one slow payer becomes a
cash-flow event. For a corner shop with thousands of customers it is near zero
by arithmetic, and scoring it would award a perfect mark on a 0.75-weight
metric that says nothing about them, pulling their composite *up*. Not scoring
beats scoring something meaningless.

The exclusion has to reach four places, and reaching three would look like it
worked: the score, the quality gate (a metric that does not apply cannot be
*required*), the catalogue a customer builds an integration against, and the
diagnosis prompt.

---

## D46 — `observed_at` is the customer's fact; `seq` is ours, and it settles ties

Two readings can carry the same `observed_at` — a connector posting a batch, a
source with second precision, a coarse system clock — and `created_at` ties
with it, because both come from the same call to the clock.

With both equal there was nothing left to order by, so "the latest reading"
was whichever row the database returned. Measured: two readings recorded back
to back collided about a quarter of the time on this machine, and the wrong
one was evaluated in half of those. **The same data gated an action or did
not, roughly one time in eight.**

A monotonic sequence is the only thing that can settle it, so migration 0014
adds one. `observed_at` says when a reading refers to and belongs to the
customer; `seq` says when we were told and belongs to us. Where two readings
claim the same moment, the later arrival wins — it is the later information
about that moment, which is what a correction looks like.

Deliberately **not** a unique constraint on `(tenant, domain, observed_at)`.
Resending a reading for a moment already recorded is a legitimate correction,
and refusing it would turn a fixable mistake into a permanent one.

This was found as an intermittent test failure and twice written off as
probable connection-pool pressure. It was a product bug both times. An
intermittent that is not reproduced is not diagnosed.

---

## D47 — The threshold shown is always the threshold used

A surface that displays a band must display the one the engine scored
against, never the pack's published default, and must say which of the three
layers it came from.

This was already true of the diagnosis prompt (fixed in 3.4) and was still
false on the dashboard, in two places on one screen: a metric card printed
"healthy below 45 days" beside a figure it had marked unhealthy at 30, and the
reading form printed 45 beside a card showing 18. Since sector bands landed
the pack default is frequently *not* the number used, so quoting it is not a
simplification — it is a contradiction, and the same failure as quoting the
wrong band in prose (D14).

The band comes from what was stored with the reading, not recomputed. A
customer asking about a reading from March is asking what we said in March;
recomputing would answer "what we would say today" and quietly rewrite a
verdict they may have acted on. Changing sector therefore leaves old readings
displaying their original band, which is the same guarantee D41 makes.

The general rule, since this has now been fixed three times in three places:
**any number a customer can compare against a verdict must come from the same
place the verdict did.**

---

## D48 — Forecasts report a prediction interval, not a confidence interval

They answer different questions and the difference is not academic. A
confidence interval says where the *average* future reading probably sits; a
prediction interval says where *next Tuesday's* reading probably sits, and
includes the scatter of individual readings about the line.

An owner asking "where will my DSO be in six weeks" is asking the second.
Measured on a representative series the prediction interval is **1.76×** the
width of the confidence interval, so answering the wrong question would
present every forecast as nearly twice as precise as the data supports.

Default confidence is 80% rather than 95%, and that is a trade rather than a
convention: a 95% interval on a dozen noisy weekly readings is wide enough to
contain both "fine" and "in trouble" — true, and useless to act on. The level
is carried on every forecast so nobody has to guess which was used.

---

## D49 — The horizon cap covers what the interval structurally cannot

A projection never reaches further ahead than the history behind it.

This is not belt-and-braces over the interval, and the distinction is the
whole point. **A prediction interval measures uncertainty given that a line is
the right shape.** It has no way to express "a straight line is the wrong
model by then" — which is the assumption that fails first on business data.

Measured: twelve noisy weekly readings project to 117–153 days DSO at a year
out, with 80% confidence. Arithmetically correct, and a confident-sounding
claim no metric earns from three months of history. The interval widens
honestly but never widens *enough*, because the error it cannot see is model
error rather than sampling error.

One-to-one is the rule because it is defensible and easy to state: twelve
weeks of readings support a twelve-week projection.

---

## D50 — Refusing is a family of answers, not one silence

`NoForecast` is an enum with a sentence for each member, because the reasons
are not interchangeable and collapsing them loses information a customer
needs:

- **too few readings** — a matter of time, and it will resolve on its own.
- **no detectable trend** — the business is steady. Good news, not a gap.
- **heading away** — improving. Better news, and briefly returned the same
  reason as "we cannot tell", which is the opposite message.
- **not within horizon** — genuinely drifting toward the threshold, just not
  soon enough to date. A business on a slow drift needs to hear the drift.
- **horizon too far** — asked for more than the history supports.

The failure this guards against is a forecast that reports the tilt of a line
through noise as a direction. A line always tilts; saying so is inventing a
signal, and a business may act on it.

---

## D51 — A forecast changes when we act, never what we say is at stake

A trajectory can bring attention forward. It cannot raise the money at risk,
and it cannot reach `intervene` on its own.

**Not the money.** Today's exposure is today's money. A breach expected in
three weeks has cost nothing yet, and folding a forecast into the loss figure
would inflate a number the customer cannot reconcile against their own books —
the same failure as summing exposures across domains, arriving from a
different direction. So the escalated message says explicitly that nothing has
been counted against it.

**Not to `intervene`.** That slot gates a human decision and spends money.
Acting on an 80% prediction interval would trade a real cost for a predicted
one, and at this stage a false alarm costs more trust than a missed one.
Getting somebody to *look* early is the entire value, and looking is free. If
the level then deteriorates for real, the ordinary path escalates as it always
did.

**Never twice for the same problem.** A metric that is bad now *and* getting
worse is one problem. The escalation applies only where the level has not
already asked for attention, so a struggling business is not told off twice
for one thing.

The window is the tenant's payback horizon rather than a new constant. That
number already answers "how far ahead is worth acting on" for this business,
and inventing a second one would make the two drift apart.

---

## D52 — Seasonality is detected on residuals, and mostly refuses

Three things, and the first is the one that surprised me.

**Removing a season buys precision, not accuracy.** The intuition is that a
seasonal pattern biases the trend. Measured on a monthly sawtooth over a real
underlying climb, the naive slope was already within 0.02 of the truth — the
sawtooth was being counted as *noise*, so what it wrecked was the interval.
The 28-day projection went from 14.5 wide to 0.1. A projection that vague
cannot say when anything crosses, which is the whole product of Phase 4.

**Detection runs on the residuals of the trend line, never the raw values.**
On raw values a steady climb reads as a season whose phases happen to be in
ascending order, and the system would confidently report a rhythm that is
simply growth.

**Refusing is the expected answer.** Three monthly cycles take a quarter to
accumulate; three annual ones take three years, and the forecast window holds
52 readings. `annual` is listed as a candidate anyway, because it is the cycle
people ask about and it should visibly refuse rather than appear unconsidered.
Two cycles is a coincidence, not a season.

A phase counts when its mean residual is further from zero than ordinary
scatter would put it — the same t-based test the prediction interval uses, so
there is one notion of "distinguishable from noise" in this module rather than
two that could drift apart.

---

## D53 — The backtest found the forecasts lying, and the fix was to refuse

Building the harness was supposed to be bookkeeping. It found a real defect.

Measured coverage of the stated 80% prediction interval, walk-forward, ten
independent series each:

    line plus independent noise      0.78    honest
    random walk                      0.52    badly overconfident
    accelerating curve               0.12    uselessly overconfident

The interval is trustworthy only where the metric behaves the way the model
assumes. Both failing shapes are ordinary in business data — a cash balance
wanders close to a random walk, and a book that is deteriorating usually
accelerates rather than sliding in a straight line.

**Documenting that would not have been enough.** A 0.12 coverage figure quoted
as "80% confidence" is a lie the product tells at scale, and this module's
whole posture is that refusing is a real answer. So `fit` now detects the two
shapes and declines:

- **Positive lag-1 autocorrelation** catches a walk: its residuals persist,
  because the "trend" is really the last value plus a step. One-sided
  deliberately — *negative* autocorrelation makes the interval conservative
  rather than overconfident, and the first version rejected it wrongly.
- **Bowing residuals** catch a curve: a line under-predicts at both ends of an
  accelerating series and over-predicts through the middle.

After the guard, both shapes get **no forecast at all**, while an honest
straight line is still forecast at 0.74 coverage across 559 forecasts. Some
legitimate windows are refused as a result, and that is the right side to err
on: a missing forecast costs a look, a lying one costs trust.

**The general lesson.** Every other refusal in this module was reasoned from
first principles. This one was invisible until it was measured, and it was the
worst of them. A harness that only ever confirms good news is decoration —
there is now a test asserting it can still detect a lie.


---

## D54 — Password reset gets its own throttle counters, not the login ones

Reusing the login throttle for `/v1/auth/forgot` was the obvious move and
would have built an attack.

The login throttle counts failures per email address. If reset requests
counted against the same tally, anyone could hammer the reset form for a named
person — no password guessing, no failures, nothing that looks like an attack
— and that person would be locked out of signing in. That is precisely the
denial of service the two-scope design in `throttle.py` exists to prevent,
re-entered through the door built to escape it.

So reset has `reset_email` and `reset_ip` scopes of its own.

**And every reset request counts, not only failed ones.** For a login, only
failures are worth counting: a successful sign-in is not evidence of anything
bad. For a reset, there is no such thing as a failure from the caller's side —
the endpoint answers 202 whether or not the address exists, by design. What is
being rationed is *mail to somebody's inbox*, and an attacker who knows a real
address never fails at all. Counting failures there would count nothing, and
the reset form would be an open mail relay pointed at one victim.

Three requests per address per fifteen minutes, then backoff.

---

## D55 — No test may send real email, and this is not hypothetical

Pointing `notifications` at the unified `core.mail` module broke a test that
had passed for two weeks — `test_unconfigured_smtp_records_skip_not_silence`.
It passed because the developer's machine had no `AETHER_SMTP_HOST`. It never
asserted that; it inherited it from the environment.

With the send path unified, the same test found the live Resend key in `.env`
instead and **made a real outbound API call trying to mail a made-up address**.
It failed only because the sending domain is not verified yet. With a verified
domain — the next item on Tejas's list — a full test run would have quietly
emailed strangers, and nothing in the suite would have said so.

`tests/conftest.py` now clears both transports for every test by default and
replaces `_via_resend` and `_via_smtp` with something that raises. A test that
wants to observe sending patches `mail.send`, which sits above both. Setting a
transport is now the loud, deliberate act it should always have been.

**The lesson is the same one D46 recorded about the intermittent failure:** a
test that passes for a reason nobody chose is not evidence. The reason has to
be pinned inside the test, not left to whatever happens to be in the
environment — because the environment changes, and the test keeps its green
tick while it stops meaning anything.

---

## D56 — Completing a password reset does not sign you in

The reset endpoint returns "password changed, sign in with it" rather than a
session token, and the web page redirects to `/login`.

Auto-signing-in is friendlier by one click and wrong. A reset link proves
control of a **mailbox**. It does not prove control of the **account** — that
is what the password proves, and the person has just chosen one. Making them
use it immediately turns the reset into a complete proof instead of half of
one, and it means a reset link intercepted in transit still does not hand over
a live session without the attacker also setting, and knowing, a password the
real owner will notice is broken.

**The gap this leaves, stated plainly.** Session tokens are stateless JWTs
with a sixty-minute life, so a reset does *not* end a session an attacker
already has. For up to an hour, changing the password does not evict them.
That is a real weakness and it cannot be fixed here — it needs server-side
session state, which is 6.7. Until then the product must not imply that
resetting a password secures a compromised account.


---

## D57 — Faults are stored in our own Postgres, and staff see the shape before the words

The usual answer for error tracking is Sentry, and for most products it is the
right one. Not for this one.

A stack trace from a multi-tenant platform carries other companies' operating
data. `IntegrityError` puts a customer's email in its message; SQLAlchemy
appends `[parameters: ...]`, which for this product means real revenue
figures, real invoice totals, real names. Shipping that to a third party means
every customer's data can arrive in an external account on any exception. The
no-paid-subscription constraint points the same way, but it is not the reason.

So faults go in `error_events`, and three things protect a customer:

1. **Request and response bodies are never captured.** Not scrubbed: never
   read. The safest data is the data that was not collected.
2. **What is captured is scrubbed** (`core/scrub.py`) -- emails, bound
   parameters, tokens, long digit runs. Stated plainly in that module: it is a
   filter, not a guarantee. It matches shapes it was taught and cannot
   recognise a customer's data in a form nobody anticipated.
3. **The role split is inside the payload, not at the door.** `StaffRole`
   already documents `observer` as "counts, timestamps, error rates. Never the
   contents of a tenant's data" -- so an observer gets the exception type, our
   code location, the occurrence count and how many tenants were hit, and the
   `message` and `traceback` keys are absent from their response entirely.
   Reading them requires `engineer` and is written to the staff trail, like
   every other look at something a customer owns.

The trail records fingerprints and never the message, because a trail that
copied the text would just be a second, less guarded copy of the thing it is
auditing access to.

**One row per fingerprint, not per occurrence.** An outage produces thousands
of identical errors; a row each would make the incident's first casualty the
table meant to explain it. The fingerprint is the exception type plus the
deepest frame *in our code* -- never the message, because messages carry the
varying part and fingerprinting on one gives every occurrence its own row.

The cost is real: individual occurrences are lost, so "was it only this one
tenant?" cannot be answered exactly. `tenants_seen` answers the version of it
that matters -- one customer broken and every customer broken are different
emergencies.

---

## D58 — A context variable set inside an endpoint does not reach the middleware

Written down because it cost a real bug and the reasoning is not obvious.

Faults are attributed to a tenant so that "one customer is broken" and
"everyone is" can be told apart. The tenancy dependency knows the tenant, the
middleware handles the exception, and a `ContextVar` is the obvious way to get
one to the other.

It does not work. Every endpoint in this platform is a sync `def`, which
Starlette runs in a threadpool -- and a thread receives a **copy** of the
context, so `ContextVar.set()` inside an endpoint or a dependency rebinds the
copy and the middleware never sees it. Every fault would have been recorded as
belonging to nobody, losing precisely the field that makes the count useful. A
test caught it; nothing about the code looked wrong.

Two things follow.

**The middleware is pure ASGI, not `BaseHTTPMiddleware`.** That one runs the
downstream app in a separate task, which loses the context for the same reason
and would additionally have made this unfixable.

**The variable holds a mutable dict, not the id.** The copied context still
points at the same dict object, so mutating one crosses the boundary that
rebinding cannot. `attribute()` writes into the holder; `attributed_tenant()`
reads it.

The general shape is worth remembering: **context propagates into a thread and
never back out.** Anything a worker thread needs to tell its caller has to live
behind a reference, not in the variable itself.

---

## D59 — `/healthz` was a liveness lie, and readiness is a separate question

All three services answered `/healthz` with `{"status": "ok"}` unconditionally.
That is not a health check; it checks that Python is running. An uptime monitor
watching it would have reported a green month through a total outage, because
it says `ok` just as loudly while every request in the building is failing on
an unreachable database.

The fix is not to make `/healthz` check the database. A liveness probe that
touches a dependency is how a brief database blip becomes an orchestrator
killing every healthy container it has.

So the two questions are separated. **`/healthz` is liveness** and stays
deliberately dumb. **`/readyz` is readiness**, touches the database, and
returns 503 when it cannot serve. That is the one to route on and the one to
monitor.

`snapshot()` adds what a console needs, including the part easy to leave out:
whether alerting is configured at all. An alerting system nobody set up looks
exactly like an alerting system with nothing to report. And when the database
is unreachable it says `errors: {unavailable}` rather than omitting the count
-- "no errors" is the most dangerous thing that endpoint could say during an
outage.


---

## D60 — A production process refuses to start on a development configuration

The repository ships working defaults so that a checkout runs with no
configuration at all: a signing secret, a staff signing secret, a database
password. Every one of them is printed in a public repository, and each is one
forgotten environment variable away from being what production runs on.

That failure is silent by construction. A platform running on a published
signing secret looks entirely healthy; anyone who has read the repository can
mint a token for any tenant, and nothing anywhere would say so.

So `verify_deployable()` runs at import in all four processes, and when
`AETHER_ENV` is not a development value it refuses to start.

**Fatal and warning are split on a real distinction, not on severity.** Fatal
means the deployment is unsafe — a forged token would be accepted, or a
credential would cross the network in the clear. Warning means it works and
something will not be noticed: nobody is alerted, no mail can be sent.

Warnings are deliberately not fatal, and that is the judgement worth writing
down. A check strict enough to block a launch over an operational gap teaches
people to set `AETHER_ENV=dev` in production, which disables every check
including the ones that stop forged tokens. Strictness is spent where it buys
safety, and nowhere else.

Every problem is reported at once. Fixing a deployment should be one pass, not
one restart per mistake — the person doing it at two in the morning stops
reading after the first line.

**This needed a migration to be satisfiable at all.** Migration 0001 creates
the `aether_app` role with the password `aether_app_dev_only` and nothing had
ever changed it, so the check would have demanded a password the schema had no
way to set. 0017 sets it from the environment, quoted by Postgres rather than
interpolated by Python, and stays silent when unset because that is the
development case.

---

## D61 — The client's address travels three hops, and every one of them had to
change

6.4 built per-address throttling and then switched it off, because the
deployment could not name a client. Both front ends are
backends-for-frontends: the browser never talks to the API, so from the API's
point of view every login on the platform arrives from one Next.js server, and
counting against that address would collapse the entire customer base into a
single bucket where twenty bad guesses by anyone locks out everyone.

Turning it on took a change at each hop, and the middle one is the part that
would have been missed.

**Caddy → Next.** Measured rather than assumed, because everything else rests
on it: sending `X-Forwarded-For: 9.9.9.9` through the proxy arrives upstream
as the real remote address. Caddy replaces an incoming value unless it came
from a configured trusted proxy. An explicit `header_up` was written first and
then removed — it was redundant, and Caddy said so. This mattered because the
application reads the **leftmost** value, so an appending proxy would have
handed every attacker a fresh identity per request.

**Next → API.** Nothing carried it. Each front end builds its outgoing request
from scratch, so the API saw no forwarded header at all and
`AETHER_CLIENT_IP_SOURCE=forwarded` would have read a header nobody set —
throttling on the empty string, which disables it. `forwardedFor()` in each
app's `lib/api.ts` is the fix, and it is the least visible part of the chain.

**API.** Already correct, and now proven: three failed logins carrying
`X-Forwarded-For: 203.0.113.77, 10.1.1.1` produce one throttle row against
`203.0.113.77`.

**The setting is a claim about the deployment, not a preference.** It is true
only because no API is reachable from outside the compose network. Publish a
route to the control plane and anything on the internet can name itself
whatever it likes — per-address throttling becomes theatre without a line of
code changing. That is written in the compose file, in the Caddyfile, in
`forwardedFor()` and in the deployment guide, because it is the kind of thing
that gets undone by someone solving an unrelated problem.

---

## D62 — Compose is the infrastructure, and that is a decision with an expiry

Not Terraform, not Kubernetes, not a PaaS. One compose file that stands the
platform up from nothing on any machine with Docker.

There is one machine, no autoscaling and no second environment. The cost of
the larger tools is paid at every change and their benefit arrives at a scale
this platform has not reached. Compose also happens to be the only one of them
that runs identically on the developer's laptop, which is why the whole stack
could be brought up and verified rather than reasoned about.

**When there is a second machine this is wrong**, and it is written here so
that it is revisited rather than inherited.

The free-tier question has an honest answer and it is not the convenient one.
The stack measures ~690 MiB resident and ~2.6 GB of images. **No PaaS free
tier will run it** — Render, Railway and Fly are built around one or two small
processes with a managed database, not ten containers with Temporal and a
persistent volume. What fits is Oracle Cloud Always Free (4 ARM cores, 24 GB,
genuinely free, though the images have only been built for x86 so far) or a
$10–20 VPS. Saying "free tier" and meaning "a trial that expires" would be the
kind of plan that removes the prompt that would have corrected it.


---

## D63 — A backup counts only once it has been restored and questioned

The plan asked for "automated backups with a *tested* restore, not merely
configured", and building it turned that emphasis from a preference into the
only defensible design. Three things were measured, none guessed:

1. **`pg_dump` run as the application role writes a plausible backup with none
   of anyone's data in it.** Row-level security does exactly what it was built
   to do: the dump hits a policy, prints one error, **exits 0**, and leaves a
   54 KB file containing the schema and the non-tenant tables. Every customer
   row is missing and nothing downstream would notice.
2. **`pg_restore` also prints errors and exits 0.** A version-skewed client
   emits `SET transaction_timeout` at a server that does not know it, reports
   the error, and returns success.
3. **`pg_stat_user_tables.n_live_tup` is an estimate, not a count.** It read
   4,331 rows in the source against 55,839 in a restore of that same source —
   stale statistics on one side and fresh ones on the other.

So the exit code of either tool is worth nothing as evidence, and a row count
taken the cheap way can be wrong by an order of magnitude. Verification means
restoring the file into a scratch database and asking it questions.

Five are asked. The Alembic revision matches; no table is missing; **every
table carrying a row-level-security policy in the source carries one in the
restore**; no table that has rows came back empty; pgvector is present.

The third matters most and is the one whose absence would be invisible: a
restored database with the tables but not the policies is a database where
every tenant can read every other tenant, and it looks entirely normal from
the outside. The fourth is what catches finding (1), and it is deliberately
**not** an equality check on counts — the source is live and moves on after
the snapshot, so demanding equality would fail honest backups and teach people
to ignore the result.

`verified` is a separate column from `status` for the same reason. Producing a
file and being able to recover from it are different claims, and folding them
together is how "we have backups" comes to mean nothing.

**What this does not protect against, stated where it will be read.** The
dumps are a volume on the same machine as the database. This survives a
dropped table, a bad migration, a corrupted index and a careless DELETE, and
does not survive losing the host. Off-site copying is not implemented; when it
is, the copy must be encrypted before it leaves, because a dump is every
customer's operating data in one file and the only artefact of this platform
that carries no access control of its own.

---

## D64 — Redis was removed, because nothing had ever used it

It was in both compose files and had a setting in `config.py`. It had no
client library in `pyproject.toml`, and `redis_url` appeared in exactly one
place in the repository: its own definition.

Found by asking 6.2's first question — what has to be backed up — and finding
that the answer for this component was "nothing, because nothing writes to
it". A datastore that no code touches is not neutral: it is memory, an open
port on the internal network, an image to keep patched, and a line in the
architecture that makes a reader assume caching exists somewhere.

Removed rather than left with a comment. If a later phase needs a cache or a
queue, adding it back is a three-line change and it will arrive with a caller.


---

## D65 — Sessions in a table, not refresh tokens

The plan named refresh tokens and gave two reasons: a sixty-minute hard expiry
is a support burden, and — from D56 — a password reset cannot sign out a
session that is already running. This is a session table instead, and the
substitution is deliberate rather than incidental.

Refresh tokens exist so an access token can be short without forcing a login,
in systems where validating that access token is **stateless and cheap**.
Nothing about this platform is stateless: every endpoint opens a transaction
and sets `app.tenant_id` before it can read a row. The saving refresh tokens
are designed to protect does not exist here, and their cost — rotation, reuse
detection, a second credential in the cookie — is real.

More importantly they only half-solve the second problem. With a stateless
access token, revocation still waits for that token to expire. "Your password
is changed and the intruder is out in fifteen minutes" is a worse promise than
"they are out now", and the person resetting their password is very often
doing it *because* they think somebody else is in their account.

So every request resolves its session against the table. One indexed lookup on
a connection that was going to be opened anyway, and in exchange:

- **Revocation takes effect on the next request.** D56's gap, closed.
- **Role, membership, account-active and organisation-active are read live.**
  They used to be frozen into the JWT at login, so a demoted or deactivated
  user kept their rights until it expired. A test that minted a token
  asserting `role: viewer` for a user id that did not exist had to be
  rewritten against a real membership — under the old design a token could
  claim a role, and now it cannot.
- **The hard expiry can go**, replaced by an idle window that slides with use
  and an absolute cap that does not. Two expiries because one is always wrong:
  the first stops an abandoned session lingering, the second stops an active
  one becoming permanent.

**The JWT does not go away.** It still carries the signature that makes a
session id unforgeable — without it anyone could name a session and the lookup
would find it. It simply stops being the only thing consulted, and the two
questions are now separate: `security` answers "is this token genuine",
`sessions` answers "is the session behind it still good".

**The write is throttled, not skipped.** Bumping `last_seen_at` on every
request would put a row lock in the path of every call and turn a read-heavy
dashboard into a write-heavy one. It is bumped at most every five minutes,
which makes `last_seen_at` approximate — and it is only used to decide expiry
and to show somebody their own sessions, both of which tolerate minutes.

**Staff sessions are not covered, and that is a stated gap rather than an
oversight.** Staff tokens are a separate world with a thirty-minute life and
no table behind them. The mitigation is that thirty minutes is short and every
break-glass grant is already separately revocable, but a compromised staff
token has fleet-wide reach for those thirty minutes and nothing can stop it.
The mechanism built here is the one that would fix it.
