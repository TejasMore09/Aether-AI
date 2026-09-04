# Progress log

Newest first. One entry per thing a person would call "done" — not per commit.

Keep entries honest about what was *not* finished. A log that only records
wins is a log that stops being read.

---

## 2026-09-04 — Phase 4.6: the backtest caught the forecasts lying

Building this was meant to be bookkeeping. It found a real defect, which is
the best argument for having built it.

Measured coverage of the stated 80% interval, walk-forward, ten independent
series each:

    line plus independent noise      0.78    honest
    random walk                      0.52    badly overconfident
    accelerating curve               0.12    uselessly overconfident

The interval is trustworthy only where a metric behaves as the model assumes,
and both failing shapes are ordinary: a cash balance wanders close to a random
walk, and a deteriorating book usually accelerates rather than sliding in a
straight line.

**Documenting it would not have been enough** (D53). A 0.12 coverage quoted as
"80% confidence" is a lie told at scale, so `fit` now detects both shapes and
declines: positive lag-1 autocorrelation for a walk, bowing residuals for a
curve. After the guard both get **no forecast at all**, while an honest
straight line is still forecast at 0.74 coverage across 559 forecasts. Some
legitimate windows are refused too, which is the right side to err on — a
missing forecast costs a look, a lying one costs trust.

The one-sided autocorrelation test was itself a correction. The first version
rejected *negative* autocorrelation as well, which refused every zigzagging
series in the test suite — nineteen failures — and was simply wrong: alternating
residuals make an interval conservative rather than overconfident.

`measure_fleet` reports what a figure was measured on and returns nothing at
all today, which is honest: no real business has used this system, so any
number now would describe how well the forecast predicts invented data.

A no-peeking test was rewritten after passing for the wrong reason. It had
corrupted the back half of a series and watched the error move — but the
corruption was being caught by the new shape guard, not by the horizon. It now
asserts directly on what `fit` is handed.

**Phase 4 is complete.**

550 tests, none skipped.

---

## 2026-09-04 — Phase 4.3: seasonality, which mostly refuses

Detected on the residuals of the trend line rather than the raw values — on
raw values a steady climb reads as a season whose phases happen to be in
ascending order, and the system would confidently report a rhythm that is
simply growth.

**The measurement that corrected my intuition** (D52). I expected a seasonal
pattern to bias the trend. It barely does: on a monthly sawtooth over a real
underlying climb, the naive slope was already within 0.02 of the truth,
because the sawtooth was being counted as *noise*. What it wrecked was the
interval — the 28-day projection went from **14.5 wide to 0.1** once the season
was removed. A projection that vague cannot say when anything crosses, which
is the entire product of this phase. So removing a season buys precision, not
accuracy, and the module says so where somebody would otherwise assume the
opposite.

**Refusing is the expected answer.** Three monthly cycles take a quarter to
accumulate; three annual ones take three years against a 52-reading window.
`annual` is listed as a candidate anyway, because it is the cycle people ask
about and should visibly refuse rather than look unconsidered. Two cycles is a
coincidence.

The phase test reuses the same t-based margin the prediction interval uses, so
there is one notion of "distinguishable from noise" in the module rather than
two that could drift apart.

Wired into `approaching()`, so the decision engine gets the tighter interval
rather than it being merely available.

A failing test was my fixture rather than the code: the series I wrote climbed
straight through critical, and `approaching` correctly ignores a metric
already past it — that is the level's business, not the trajectory's.

538 tests, none skipped.

---

## 2026-09-04 — Phase 4.4: acting on where a metric is heading

A trajectory now reaches the decision engine, so a business can be told to
look at something *before* the level goes bad rather than after.

**It changes when we act, never what we say is at stake** (D51). Today's
exposure is today's money; a breach expected in three weeks has cost nothing
yet. Folding a forecast into the loss figure would inflate a number the
customer cannot reconcile against their own books — the same failure as
summing exposures across domains, arriving from a different direction. The
escalated message says so out loud: *"Nothing is at risk yet, so no cost has
been counted against it."*

**It never reaches `intervene` on its own.** That slot gates a human decision
and spends money, and acting on an 80% interval would trade a real cost for a
predicted one. Getting somebody to look early is the whole value, and looking
is free. If the level then deteriorates for real, the ordinary path escalates
as it always did.

**And never twice for one problem.** A metric that is bad now *and* getting
worse is one problem, so the escalation applies only where the level has not
already asked for attention. A test pins that the slot, risk level and reason
are all unchanged in that case.

The window is the tenant's payback horizon rather than a new constant — that
number already answers "how far ahead is worth acting on" for this business,
and a second one would drift from it.

Two things fixed while writing it. `RiskLevel` is a `StrEnum`, so comparing
severities with `max()` would have ordered them alphabetically and put HIGH
below LOW, silently downgrading anything relying on it; there is now an
explicit order. And `approaching()` first took the values-only history shape
the calibration layer uses, which carries no timestamps — a trend fitted
against reading number rather than elapsed time is exactly the bug 4.1 already
has a test for.

529 tests, none skipped.

---

## 2026-09-04 — Phase 4.1, 4.2, 4.5: where a metric is heading

`domains/forecast.py`. Ordinary least squares against elapsed time, which is
what fifty readings a year supports and nothing heavier. Most of the module is
about refusing.

**A prediction interval, not a confidence interval** (D48). They answer
different questions: one says where the *average* future reading sits, the
other where *next Tuesday's* does. Measured on a representative series the
second is 1.76 times wider, so answering the wrong question would present
every forecast as nearly twice as precise as the data supports.

**Time-to-critical is a range, not a date.** A steep rise reports "about 4.5
weeks, as early as 2.3" — and the early edge is the one worth acting on,
because quoting only the middle systematically understates how soon a business
needs to move.

**Refusing is five answers, not one silence** (D50). Too few readings is a
matter of time; no detectable trend means steady; heading away means
improving; not within horizon means genuinely drifting but not datable yet.
Each has a sentence. Two of these were briefly returning the same reason as
each other, which meant a business whose collections were *improving* read the
same message as one we could not measure at all.

**The horizon cap covers what the interval cannot** (D49), and my first
reasoning for it was wrong. I had written it as belt-and-braces over the
interval; running it showed otherwise. The interval measures uncertainty
*given that a line is the right shape* and has no way to say the shape is
wrong by then. Twelve noisy weekly readings project to 117–153 days DSO at a
year out with 80% confidence: arithmetically correct, and a claim no metric
earns from three months of history. So the rule is now one-to-one — never
project further ahead than the history reaches back — which also loosened the
cap from a third of the span, making the feature considerably more useful.

Two test failures were mine rather than the code's: I asserted a factor of
three where the measured value is 1.76, and wrote an uneven-spacing test whose
arithmetic I had not worked out. Both now assert measured numbers.

522 tests, none skipped.

---

## 2026-09-03 — Phase 3.6: the threshold shown is the threshold used

Bands now travel out with each stored reading, and every surface that displays
one shows the band the engine scored against rather than the pack's published
default — plus which of the three layers it came from.

**The dashboard was contradicting itself, twice on one screen.** A metric card
printed "healthy below 45 days" beside a figure it had marked unhealthy at 30,
and the reading form printed 45 beside a card showing 18. Since sector bands
landed in 3.2 the pack default is frequently not the number used, so quoting
it is not a simplification but a contradiction — the same failure as quoting
the wrong band in prose (D14), which had already been fixed in the prompt and
not here.

The card now reads *30d – healthy below 18d, normal for your industry*, and the
form beside it agrees. Verified in the browser rather than assumed.

**The band comes from what was stored, never recomputed.** A customer asking
about a reading from March is asking what we said in March; recomputing would
answer "what we would say today" and quietly rewrite a verdict they may have
acted on. Changing sector leaves old readings showing their original band.

Since this is now the third place the same lie has been found and fixed, it is
written as a rule (D47): **any number a customer can compare against a verdict
must come from the same place the verdict did.**

Found while verifying: two `uvicorn` processes left running from the 3.3 check
were still bound to the API ports, so the newly started servers silently failed
to bind and the old code answered. The "services up" health check passed
against the stale build. Worth remembering the next time a browser check
disagrees with the tests.

**Phase 3 is complete.**

501 tests, none skipped.

---

## 2026-09-03 — Phase 3.5: a shop is not scored on things shops do not have

A metric now declares the traits a business must have for it to mean anything,
and sectors declare their traits. Neither names the other (D45), because a
metric listing the fifteen sectors it applies to is a list somebody must
remember to edit when a sixteenth appears — and forgetting is silent.

**The concrete case, which is why this is not speculative configuration.**
Top-five customer concentration is a real risk for a wholesaler: one slow
payer becomes a cash-flow event. For a corner shop with thousands of customers
it is near zero by arithmetic, and scoring it would award a perfect mark on a
0.75-weight metric that says nothing about them, pulling their composite *up*.
Disputed share of the book is the same story — a business paid at the till has
no book to dispute.

The exclusion reaches four places, and reaching three would have looked like
it worked: the score, the quality gate (a metric that does not apply cannot be
*required* either), the catalogue a customer builds an integration against,
and the diagnosis prompt.

One test was rewritten because it proved nothing: no shipped pack yet requires
a scoped metric, so the quality-gate check passed through an escape hatch. It
now builds a pack that does — which is exactly what Phase 5's inventory pack
will look like.

## The intermittent was a product bug, twice written off

Two fixture errors had appeared under full test runs and been recorded as
probable connection-pool pressure. They were neither.

The monitor evaluates the latest reading for a domain, ordered by
`observed_at`. Two readings can share it, and `created_at` ties with it because
both come from one call to the clock. With nothing left to order by, the
database returned whichever row it liked. Measured on this machine: two
readings recorded back to back collided about a quarter of the time, and the
wrong one was evaluated in half of those — **the same data gated an action or
did not, roughly one time in eight.**

Migration `0014` adds a monotonic `seq` (D46). `observed_at` is the customer's
fact about when a reading refers to; `seq` is ours about when we were told,
and the later arrival wins because it is the later information about that
moment. Reproduced at 35/40 before and 60/60 after, with a test pinning it and
three consecutive clean suite runs.

Running the code found a second thing the tests would not have: the app role
had no privilege on the new sequence, because 0001 granted default privileges
for tables and there had never been a sequence to cover.

**An intermittent that is not reproduced is not diagnosed.** Recording it
against a plausible cause twice was the mistake.

493 tests, none skipped.

---

## 2026-09-03 — Phase 3.4: the agent knows what is normal in its industry

`knowledge/sector_corpus.py`. Each tenant's knowledge base gains a paragraph
about its industry, written at signup and rewritten when the sector changes.

**It exists mainly to close a gap 3.2 left.** Scoring a retailer against 18
days rather than 45 changed the verdict and said nothing about it, so an
explanation would have called 30 days unhealthy against a threshold the
customer had never been shown — the same failure as quoting the wrong band
(D14), one layer along. Bands that are not the pack's default now say where
they came from, and the industry paragraph reaches the prompt.

**Every sentence is derived from the committed reference table** (D44).
Nothing is written from general knowledge, however plausible it would sound. A
knowledge base mixing citable figures with confident-sounding invention is
worse than one with fewer facts, because nothing downstream can tell which is
which.

**It is a lookup, not a search, and the module says so.** A tenant has one
sector; asking a vector index which one would return the only candidate and
call it a match. It still lives in the knowledge base — it is genuinely part
of what the agent knows, the fleet's chunk counts must see it, and it is where
real industry documents land in Phase 7.

## The bug this found in 3.2

Construction named Engineering/Construction and Homebuilding. The first bills
clients and waits **100 days** holding no stock; the second sells houses for
cash in **7 days** and holds **226 days** of land. Their median was 54 days,
described neither, and was being shipped as what is normal in construction.

The median defends against one distorted industry among several. It does not
defend against averaging opposites: with two values it sits exactly between
them, and between two opposites is nowhere. `reference._represents` now
requires half a group to sit within 25% of its median (D43). Three sectors
lost their receivables band — construction, wholesale and healthcare — and each
now says why, as do the two whose data was already known unusable.

`has_bands` was also lying: it read the YAML rather than the data, so a sector
could claim a band and produce none. It now checks.

**Known and not fixed:** two fixture errors appeared once under a full suite
run and did not reproduce. No error text was captured, so nothing has been
diagnosed and nothing has been changed on a guess. Recorded against 6.9, which
is where connection-pool sizing belongs.

478 tests, none skipped.

---

## 2026-09-03 — Phase 3.3: choosing a sector, and being told what it does

`domains/preview.py`, `PATCH /v1/tenant`, a signup field and a settings page.

**A dropdown that silently changes how a business is judged is worse than no
dropdown.** So the catalogue at `/v1/sectors` carries the effect of each
choice, and both surfaces render it live as someone browses: choosing Retail
says *DSO healthy below 18 days rather than 45 — stricter than the default*,
and choosing Construction says *53.8 rather than 45 — more room*.

Two things a vendor would leave out are on the page. That the figures describe
US public companies and only the ordering transfers, and that for Marketing
and Financial Services there is **no adjustment at all**, with the measured
reason. A customer who picks their own industry and gets nothing deserves to
be told why rather than left assuming it worked.

**Changing your mind never rewrites the past** (D41). Bands are stored on each
observation at ingestion, so a sector change moves future readings only. The
settings page says so where someone is about to save, and the change is
written to the tenant's own audit log — an unexplained shift in verdicts
should be traceable to the day somebody changed a setting rather than looking
like the agent became erratic. A test proves a stored reading keeps its
original band while the next one picks up the new sector.

Verified in the browser rather than assumed: signed up as a builders' merchant
in rupees, watched the preview switch from 50.3 days to 18 on changing to
Retail, saved, and confirmed it persisted.

Found while doing it: the BFF's `proxy.ts` was redirecting the catalogue route
to `/login`, which would have shipped a signup form permanently missing its
sector field. `/api/sectors` is now explicitly public, with a note at the point
of temptation that `PUBLIC_PATHS` is a disclosure decision and not a
convenience (D42).

Partial updates were an obvious trap and are tested: sending only a sector must
not silently reset the currency.

463 tests, none skipped.

---

## 2026-09-03 — Phase 3.2: the same number, two different verdicts

`domains/reference.py`, `sector_band()` in `domains/calibration.py`. The gap
the vision named is closed for receivables: a bakery and a builders' merchant
both collecting in 50 days no longer get the same answer.

Bands now layer pack –> sector –> tenant, each anchored to the one beneath.
The seeded figures, median across each sector's named industries:

    retail            18.0     construction      53.8
    food service      19.4     manufacturing     63.9
    automotive        35.9     professional      67.3
    logistics         44.6     IT services       72.0

**The clamp is the honest part** (D39). Reference figures describe US public
companies, whose levels an SME does not share — but the ordering across
sectors does transfer. Allowing a sector band to move only as far as the
pack's existing calibration allowance takes the ordering and declines the
level. Published retail DSO is 6.4 days; judging a corner shop against that
would flag every ordinary week, so retail lands at 18 — far stricter than the
default of 45, without betting on 6.4. Where the clamp bites, the band says so.

**A second sector admitted it does not know** (D40). Marketing's only matching
industry is Advertising at 172.9 days implied DSO and 168.3 DPO: agencies
carry clients' gross media spend as both receivable and payable while
reporting only commission as revenue, so every figure in the row is inflated.
No defensible adjustment exists, and inventing a multiplier would be the
confident guessing this project refuses. Two of twenty-one sectors now say
they do not know, and neither gap closes with a better dataset.

**A test failure corrected a real misunderstanding.** With ten readings of
history a tenant's own number wins outright regardless of sector — and that is
right, because their own readings are better evidence about them than an
industry average. The sector then stops changing the answer and only bounds
how far their history may move it. The test now pins both behaviours rather
than the one I assumed.

Reference columns are validated when a pack loads. A typo would seed no band
for every tenant in every sector, forever, while looking entirely correct.

Only DSO has a published reference figure today. Payables and inventory join
it in Phase 5 from the same file, and the mechanism is already general.

449 tests, none skipped.

---

## 2026-09-03 — Phase 3.1: a business can say what kind of business it is

`domains/sectors.yaml`, `domains/sector.py`, migration `0013`. Twenty-one
sectors, chosen so an owner recognises themselves in one, crosswalked to the
classifications India, the US and Europe actually use.

**The crosswalk needs two columns, not three.** NIC 2008 is identical to ISIC
Rev. 4 down to the four-digit class, and NACE Rev. 2 is ISIC with European
sub-divisions, compatible at two. One list of ISIC divisions therefore serves
India and Europe; only NAICS needs its own. Checked before building on it
rather than assumed.

**Granularity is capped by the evidence** (D35). A taxonomy finer than the
data is false precision: two sectors would look different on screen while
being seeded from the identical number, and a customer would reasonably read
that difference as knowledge.

**The validator caught a real ambiguity in the first draft.** ISIC 62 covers
both software houses and IT services firms. The reference data puts them
seventeen days apart on DSO, so the split is genuine and the code is
ambiguous — and loading now fails unless the file declares which sector wins.
Ambiguity resolves toward the more forgiving band, because a false alarm costs
more trust than a missed one.

**A sector may have no band and say so** (D36). Financial services carries
none: banks compute to 0 days, brokerage to 512, non-bank financial services
to 4,863, and four financial industries have blanks exactly where a
working-capital figure belongs. It falls back to the pack's general bands with
a sentence explaining why. A stock brokerage — the vision's own example — is
precisely the sector no reference data answers for.

**Reference data is now committed as CSV** (D38), with the workbook kept as
the receipt and `reference/extract.py` keeping them honest. A binary diff says
"51200 bytes differ" when next January's edition lands. It also removed a
skipped test: the check that every referenced industry actually exists needed
`xlrd`, so the one test that catches a typo silently seeding no band was not
running at all.

429 tests, none skipped.

---

## 2026-09-03 — Phase 3.0: money stops being dollars by assumption

Migration `0012`, `core/money.py`. A prerequisite for the rest of Phase 3
rather than polish: Aether targets India, the US and Europe (D31), and every
monetary value was USD by name. Telling a Pune manufacturer they are losing
$147 a day is not slightly wrong — it is a number they cannot check against
anything they know.

**The platform never converts.** No FX rate is stored, fetched or applied. A
rate is a fact about a moment, and a stale one silently corrupts figures that
have already been shown to a customer and acted on. Businesses report in their
own currency and it stays there. Most of the product turned out to be
currency-neutral already: DSO is days, overdue share is a fraction.

**Two kinds of money were spelled the same and are now separated.**
`expected_loss_usd` became `expected_loss` plus a currency, because it may be
rupees. `LLMUsage.cost_usd` kept its name, because what a diagnosis costs *us*
at the model provider is billed in dollars whoever the tenant is. The same
distinction runs through both front ends.

**Currency is copied onto each approval rather than joined from the tenant**,
so a decision recorded last March keeps meaning what it meant last March even
if the business later switches. Same reasoning that put the band on the
observation instead of looking it up at read time.

**Indian grouping is implemented rather than approximated.** Rupees group in
lakhs and crores: ₹1,50,000, not ₹150,000. Nine parametrised cases pin it,
including one crore. Getting this wrong is a small constant signal that the
product was built for somebody else, and it is fifteen lines.

Found along the way: `money.for_tenant` opened a second database session
inside callers that already held one, which surfaced as an intermittent
failure under a full test run. It now takes the session its caller is holding.

Not done, and named so it is not mistaken for done: per-locale symbol
placement. A German reader writes `1.234,56 €` and gets `€1,234.56`. Smaller
than the currency itself being wrong, and it should be fixed before anyone is
charged money for this.

399 tests, none skipped.

---

## 2026-09-02 — Phase 6.4: credential guessing gets expensive

Pulled forward out of Phase 6 because it was not a missing feature. Every
password endpoint on the platform accepted unlimited attempts at whatever rate
a caller could manage — the cheapest serious attack available against a
system holding other companies' operating data, requiring no skill at all.

Migration `0011`, `core/throttle.py`. Failures are counted per account and per
address, and a lock doubles from one minute once the free attempts are spent.

**Postgres, not Redis, although Redis is already in the compose file.** This
state sits in the authentication path, so its failure mode is the whole
question. Redis down and failing open makes the mechanism decorative exactly
when someone is hammering the service; failing closed makes a cache the single
point of failure for every login. Postgres introduces neither, because login
already cannot proceed without it. One upsert against a bcrypt verify is free.

**The customer login was an enumeration oracle** and is not any more. An
unknown email returned before any hashing while a real one paid ~100ms, so the
endpoint told an attacker which of our customers' addresses were real, by
clock, for nothing. It now verifies against a fixed dummy hash. Staff login
already did this; the two had drifted.

**The finding worth recording: per-address throttling would have been an
outage.** Both front ends are back-ends-for-front-ends, so the browser never
reaches the API and `request.client.host` is one Next.js server for every
customer on the platform. Throttling on it puts the entire customer base in a
single bucket, where twenty bad guesses by one attacker locks out everybody.
A test caught it. Believing `X-Forwarded-For` instead is the opposite trap:
without a proxy that overwrites it, every attacker gets a fresh identity per
request.

Neither can be inferred at runtime, so `AETHER_CLIENT_IP_SOURCE` states which
is true and the default states nothing. **Per-address throttling is therefore
inert in this deployment**, which means password spraying — one guess each
against a thousand accounts — is not currently defended. That is honest and
it is the right trade: the alternative shipped an outage. It activates when
6.1 puts a proxy in front.

The account cap is 15 minutes rather than longer for a reason that expires:
password reset does not exist (6.5), so a longer lock strands a real customer
with no way out. And what this does not do, stated so nobody assumes
otherwise: it bounds the *rate* of guessing. A patient attacker with a good
wordlist is 6.6's problem, not a bigger number here.

Not done, and not claimed: general per-endpoint rate limiting. That belongs at
the reverse proxy in 6.1, where doing it well is easy and doing it in the
application is worse than not doing it.

374 tests, none skipped.

---

## 2026-09-01 — Phase 2.6: the fleet sees how much, never what

Migration `0010`. The fleet view gains three columns: how many memories an
agent holds, when it last gained one, and how many resolved decisions were
never indexed.

The third is the reason this exists. A knowledge base fails silently: approvals
resolve, the indexing task raises, the store stops growing, and the only
symptom is that explanations quietly stop mentioning the past. Nobody gets an
error, and the customer cannot tell, never having seen the version that works.
A count of decisions with no memory of them is how that becomes noticeable
from outside.

The line from `0008` holds unchanged, and this is where it matters most.
Everything else the view counts is telemetry a business pushed at us; a
knowledge base is the agent's record of what its owners *decided*, written in
prose a person can read at a glance. It is the one place where "just show the
body, for debugging" would be most tempting and worst. So the guarantee is
structural rather than good manners: the view cannot return a body because it
does not select one, and it is owned by the migration role.

Console shows both counts on the tenant page with that stated plainly, and
raises a fleet signal once unindexed decisions reach three — one or two is a
model that was missing when a decision happened, which a backfill repairs; a
steady climb is a pipeline that stopped.

**Phase 2 is complete.** Its own test: an agent's explanation can reference
what happened to that same business months ago, and no query path reaches
another tenant's chunks. Both hold.

What Phase 2 is *not*: the retrieval only answers "have we seen almost exactly
this before?" A tenant with one prior decision gets nothing quoted. And no
real business has used any of it — the memories in every test are invented.

354 tests, none skipped.

---

## 2026-09-01 — Phase 2.5: the agent remembers out loud

`knowledge/briefing.py`. What this business decided last time now reaches the
explanation an approver reads, so they are reminded rather than left to
remember for themselves.

**The question is written in the store's own template.** The query is
`history.describe()` of the decision being explained — the identical template
that produced every memory. That is not a shortcut; D25 measured that this
model matches near-duplicates and nothing else, so asking in any other words
is the version that quietly returns nothing (D26).

**Only standouts are quoted**, never raw `search`. The honest consequence,
written down rather than discovered later: a tenant with a single prior
decision gets nothing quoted, because `standout` has nothing to compare
against. The feature stays quiet for a business's first months (D27).

**Nothing may be called a success.** The instructions forbid the model from
saying a past decision worked, helped or caused what followed — outcomes are
not tracked until Phase 9, and it is the most persuasive unevidenced sentence
available (D28).

Two exclusions live in SQL rather than in the caller, and the placement is the
point: a backfill indexes pending approvals too, so without them the nearest
memory to a decision is reliably that same decision, offered back as precedent
for itself — and filtering it afterwards would still leave it skewing the
comparison that decides what stands out.

Resolving an approval now indexes it, as a background task after the response.
Previously the store only grew when someone ran a backfill by hand. The
end-to-end test approves a decision over HTTP and then finds it.

352 tests, none skipped.

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
