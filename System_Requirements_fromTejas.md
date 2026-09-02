# What Aether needs from Tejas

Everything the product needs that cannot be written in code, in one place.
Kept current as phases land — if something here is stale, fix it here rather
than remembering it.

**Priority markers used throughout:**

| Marker | Meaning |
|---|---|
| 🔴 **BLOCKING** | Work is stopped, or will ship broken, until this exists |
| 🟠 **SOON** | Needed within the next phase or two |
| 🟢 **LATER** | Named now so it is not a surprise; no action yet |
| ⚪ **NOT NEEDED** | Listed because it looks necessary and is not |

---

## Read this first: the data requirement is far smaller than it sounds

The phrase that keeps coming up is *"data to train the system"*. It is worth
being exact, because it changes the size of the job by orders of magnitude.

**Aether has no machine-learning model, and Phases 0–10 do not add one.** There
is nothing to train. What exists is:

- **Curated economics** — formulas relating a metric to money at risk.
- **Per-tenant statistical calibration** — each business's bands adapt to its
  own history, anchored so dysfunction cannot normalise.
- **An LLM writing prose** — it explains a decision the engine already made. It
  never makes the decision, and it is never fine-tuned.

So there is no training corpus to assemble. What is actually needed is:

1. **Reference tables** — what "normal" looks like per sector. Kilobytes, not
   terabytes. One is already in hand.
2. **Validation series** — enough real history to check whether the claimed
   relationships between domains are true. Free and public.
3. **Real operating data** — to know whether findings are *useful* rather than
   merely correct. This is the one that matters and the one no dataset has.

And a constraint that caps this permanently: **there is no cross-tenant
learning, ever.** One business's data must never inform another's model — that
is a security property, and it is why the knowledge base sits at the agent
level. So even if a model is added later, it trains on one tenant's own
history. Nothing is gained by hoarding data across the fleet.

If you were budgeting time or money for dataset acquisition, most of it is not
required.

---

## 1. Data

### 1A. Public data — nothing needed from you ⚪

I can fetch and process all of this. Listed so you know what the system will
be standing on.

| Source | Gives | Status |
|---|---|---|
| Damodaran working capital (NYU Stern) | Per-sector receivables / inventory / payables bands | ✅ **In hand**, committed at `reference/`, verified |
| SEC Financial Statement Data Sets | Quarterly XBRL per filer since 2009 — validates `relations.yaml` and Phase 4 forecasting | Free, I fetch when Phase 3/4 starts |
| Eurostat SBS | NACE Rev. 2 sector taxonomy for Phase 3.1 | Free, I fetch |

**One thing you should know about the data you already gave me:** it cannot
supply a band for financial sectors. Banks compute to 0 days, brokerage to
512, non-bank financial services to 4,863. A stock brokerage — your own
example of a sector-aware agent — is precisely the sector this file cannot
answer for. Phase 3 will refuse those rather than seed nonsense. Full detail
in `reference/README.md`.

### 1B. Real SME operating data — via your other product 🟠

You said this comes from the SME product you are building. That is a better
answer than design partners, and it changes what I should do now.

**What I need from you, and when:**

🟠 **Before Phase 7 (connectors) starts — a data contract.** Not the data. The
*shape*: what your SME product will hold, at what granularity, how often, and
under what identity. Specifically:

- Which entities exist (invoices? balances? headcount? stock levels?)
- Whether history is retained or only current state
- Push or pull, and how a business is identified across both products
- Whether Aether reads from its database, or your product calls Aether's
  ingest API (**strongly prefer the second** — a shared database would
  collapse the isolation boundary that Phase 0 spent its whole effort proving)

Getting this wrong is expensive to undo, and it is cheap to decide now while
both products are being designed. A page of notes is enough; I will turn it
into the contract.

🟢 **Later — the first real dataset.** Even one business's real year of
history changes more than any amount of code. Until then every band and
constant in Aether is a considered guess, and that remains the single largest
risk in the product.

### 1C. What no dataset can answer — human judgement 🟠

These need a person who has run or advised small businesses. An accountant, a
CA, a family business owner. One conversation each, not a study.

| Question | Why code cannot answer it |
|---|---|
| Is 60-day DSO *actually* a problem for a builders' merchant, or normal? | The number is knowable; whether it warrants an alert is not |
| Which of Aether's findings would a real owner act on vs. ignore? | This is the difference between a useful product and a noisy one |
| What breaks a small business first — cash, a key customer, a key person? | Determines which domains Phase 5 builds first |
| For HR and marketing: what does "healthy" even mean? | Genuinely contested; inventing bands here would scale confident guessing |

**This is the highest-value hour you can spend on Aether**, and it costs
nothing but a conversation.

---

## 2. Accounts, API keys and services

Ordered by when they block work. Everything marked free is free at the scale
of 30 Nano + 10 Mega tenants.

### Needed now or next 🔴🟠

| # | Service | For | Cost | Status |
|---|---|---|---|---|
| 1 | **Gemini API key** (already have) | Diagnosis prose | Free tier, metered per tenant | 🔴 **BLOCKING a real check** — see below |
| 2 | **Transactional email** — Resend, SendGrid, Mailgun or AWS SES | Password reset (6.5), alert delivery | Free tier | 🔴 **BLOCKING 6.5** |
| 3 | **A domain name** | Email deliverability (SPF/DKIM), and the product needs a URL | ~$10/year | 🟠 Needed with #2 |
| 4 | **Sentry** (or equivalent) | Error tracking, 6.3 | Free tier | 🟠 Phase 6 |

**On #1 — the single cheapest thing you can do this week.** The LLM is stubbed
in every one of the 374 tests. I have written a great deal of careful prompt
engineering and **never once seen a real model respond to any of it.** Put the
key in, run one diagnosis against the seeded scenario, and read the output. It
costs cents. If it reads like a competent advisor wrote it, a large amount of
work is validated at once. If it reads like filler, I have been polishing the
input to a black box — and you want to know that before Phase 3 stacks more
context on top.

### Needed for deployment — Phase 6 🟠

| # | Service | For | Cost |
|---|---|---|---|
| 5 | **Managed Postgres with pgvector** — [Neon](https://neon.tech) or [Supabase](https://supabase.com) | The database (see §3) | Free tier is genuinely enough for years |
| 6 | **App hosting** — Fly.io, Railway or Render | The four services + two front ends | Free/hobby tier to start |
| 7 | **Object storage** — Cloudflare R2 or S3 | Documents, once 7.1 exists | Free tier; R2 has no egress fee |
| 8 | **Backup destination** | 6.2 — backups with a *tested* restore | Included with #5, but the restore test is ours |

### Needed for connectors — Phase 7 🟢

All free developer/sandbox accounts. Each takes minutes to register, and each
comes with a demo company containing realistically shaped data — which means
**I can build and test every connector before your SME product has a single
real user.**

| # | Service | For |
|---|---|---|
| 9 | Xero developer account | Accounting connector (7.3) |
| 10 | Intuit/QuickBooks developer account | Accounting connector (7.3) |
| 11 | Stripe account, test mode | Payments connector (7.4) |
| 12 | HubSpot or Zoho developer account | CRM connector (7.5) |

### Automation engine 🟢

Temporal runs the monitor loop. Today it is self-hosted in Docker, which is
free and correct for now.

For production there are two options, and one of them you may already qualify
for: self-hosting stays free (MIT) but a production cluster is a distributed
system to deploy, monitor and upgrade; [Temporal Cloud](https://temporal.io/pricing)
starts around $100/month. **Their startup program offers $6,000 in credits to
startups with under $30M raised in the last three years** — worth applying for
before paying anything, since that covers years at this scale.

---

## 3. The database — you asked, and the honest answer is "no Mongo"

You said you need *"a real database like mongo"*. Postgres already is one, and
for this system it is strictly the better choice. Not a compromise — the
reasons are specific:

**Tenant isolation is enforced by the database, not by our code.** Postgres
row-level security means a query for tenant A *cannot* return tenant B's row,
even if the application asks wrongly, because the policy runs below the
application. The whole of Phase 0 was spent proving this, including a test
that catches leakage across a pooled connection under concurrency. **Mongo has
no equivalent.** Isolation would move back into application code — one
forgotten `WHERE` clause away from a breach, on a platform holding other
companies' books.

**The knowledge base lives in the same transactional store.** `pgvector` means
a decision and the agent's memory of it are written in one transaction. Split
across Postgres and Mongo, that becomes two sources of truth that can disagree.

**The fleet view is a database view** owned by a role that bypasses RLS,
granted `SELECT` only. Staff *cannot* read a customer's numbers through it
because it does not select them. That guarantee is a Postgres construct.

**Adding Mongo would mean a second isolation mechanism to prove, a second
backup story, and a second thing to be breached.** There is no capability it
would add.

### What you actually need is *managed* Postgres, which is a hosting decision

That is #5 above. Both options index pgvector. [Neon](https://neon.tech) gives
0.5 GB per project across up to 100 projects with copy-on-write branching on
the free tier (branching is genuinely useful for testing migrations against
production-shaped data). [Supabase](https://supabase.com) gives 500 MB with
better pgvector documentation and auth/storage bundled — which we do not need,
since Aether has its own identity layer.

**Size reality check:** 40 tenants × 6 domains × weekly readings is a few
hundred thousand rows a year. Knowledge chunks are ~1.5 KB each. The whole
platform stays comfortably under a gigabyte for years. **The free tier is not a
stopgap here — it is correctly sized.** The thing that will eventually grow is
uploaded documents, and those belong in object storage (#7), not the database.

⚪ **Not needed, so you can stop worrying about them:** Mongo, Elasticsearch, a
separate vector database (Pinecone/Weaviate/Qdrant), a data warehouse, Kafka,
a feature store, GPUs. Each solves a problem Aether does not have at 40
tenants, and each adds a boundary to secure.

---

## 4. Legal and business 🟠

Unglamorous, and genuinely blocking before anyone else's data enters the
system.

| # | Item | Why |
|---|---|---|
| 13 | **Privacy policy and terms of service** | You will hold other companies' financial data. Non-optional |
| 14 | **A data processing agreement template** | Any business customer with a competent advisor will ask for one |
| 15 | **Decide the jurisdiction** | India-only, EU, or both. Determines whether GDPR (6.8) is an obligation or a nicety, and where the database may physically live |
| 16 | **Business entity + bank account** | Only when charging money (6.10). Not before |

🔴 **#15 is worth deciding early** because it constrains hosting region and
therefore #5 and #6. Changing it after deployment means migrating a database
containing customer data across borders.

---

## 5. Decisions only you can make

Not tasks — judgement calls I should not make alone.

| # | Decision | Why it is yours | When |
|---|---|---|---|
| 17 | Is Aether India-first or global? | Sets sector taxonomy (NIC vs NACE), currency, jurisdiction | 🟠 Before Phase 3 |
| 18 | Which sectors matter most to you? | Phase 3 seeds bands for the ones you name first | 🟠 Before Phase 3 |
| 19 | Which domains after the current three? | Phase 5 order. Each pack costs truth, not code | 🟢 Phase 5 |
| 20 | How much may Mega ever spend or move unsupervised? | The blast-radius limits in 8.6. A product decision wearing an engineering costume | 🟢 Phase 8 |
| 21 | Monthly budget ceiling, if any | Everything above is free-tier today; I will keep it that way unless told otherwise | Anytime |

---

## The short list — if you only do a few things

1. 🔴 **Run one real LLM diagnosis and read it.** Ten minutes, costs cents,
   and it validates or invalidates a large amount of existing work. This is
   the single highest-value item on this page.
2. 🔴 **Sign up for transactional email** (#2) and **buy a domain** (#3).
   Password reset is blocked without them, and password reset is what lets the
   login lockout cap rise above fifteen minutes.
3. 🟠 **One conversation with an accountant or SME owner** (§1C). Costs
   nothing, and answers questions no dataset can.
4. 🟠 **Write a page on your SME product's data shape** (§1B) so the contract
   between the two products is designed rather than retrofitted.
5. 🟠 **Decide India-first or global** (#17). It constrains hosting, taxonomy
   and legal obligations, and it is expensive to change later.

Everything else on this page has a date attached and can wait for it.
