# The vision

Stated by Tejas across several conversations, consolidated here so no session
has to reconstruct it from scratch. Where a phrase is his, it is kept.

---

## The product

A **self-evolving automated system for enterprises, starting with SMEs**, that
monitors the complete operations of a business — finance, marketing, HR,
data, and whatever else that business runs on — and does more than report:
it adapts itself to the business it is watching.

Not a dashboard. Not threshold alerts. Something that understands a specific
company well enough to tell its owner what matters this week, in the language
that owner already thinks in, and why.

The reference point Tejas uses is *"an upgraded version of what Palantir is
doing"* — with the difference that this is aimed at businesses far too small
to buy Palantir.

---

## Two tiers

**Aether Nano** — monitors, diagnoses, explains. Detects what is wrong or
about to be, quantifies it in money, and recommends. It never touches the
business's systems.

**Aether Mega** — everything Nano does, and then acts. Makes and executes its
own decisions inside the customer's systems. *"Three steps ahead"* of Nano:
full automation rather than recommendation.

These are subscription tiers. Target scale is **30 Nano and 10 Mega clients**,
each client a separate business.

---

## The architecture, as specified

A **main brain** that controls the whole system, with **one isolated child
agent per business**. Child agents are not connected to each other. Each is
connected only to the main brain.

**Security is the primary constraint**, stated first and repeated. The
knowledge base must live *at the agent level* — one business's knowledge is
never reachable from another's. Only the main brain spans them, and only
deliberately.

When something breaks, the operating team must be able to diagnose and fix it
*from the brain* — fleet control has to be real, not decorative, without that
becoming a hole in tenant privacy.

---

## The part that makes it distinctive

This is the half that is least built and most important. Two ideas:

**Sector compatibility.** A business in stock trading needs an agent that
knows about stocks. A bakery needs one that knows about perishable inventory.
The same agent template cannot serve both, because "normal" means something
different in each. The agent must be *super-compatible* with the sector its
business operates in.

**A brain that restructures itself per business.** Each tenant's agent should
reorganise its own internal reasoning to fit the business it serves — not just
retune a threshold, but adapt what it knows and how it weighs things. In
Tejas's words, the model *"will have to structure itself as per the
business"*.

Together these are what separate the product from a competent monitoring tool.
A metric dashboard is a commodity; an agent that understands a specific
business in a specific sector is not.

> **Architectural note, agreed 2026-08-28:** the way to deliver this is
> retrieval over a sector-aware knowledge base, plus a business-level reasoning
> graph, plus the per-tenant calibration already built — *not* a neural network
> per tenant. An SME produces on the order of 52 readings per domain per year;
> that is enough for trend and seasonality and nowhere near enough to train a
> network. Thirty tenants times a dozen domains would also mean hundreds of
> models to train, version and debug. The retrieval-and-graph route delivers
> the same outcome on the data that actually exists. See `DECISIONS.md`.

---

## Deployment, as specified

Hybrid, two modes:

1. **Direct integration** with the business's own systems and data.
2. **A standalone web or desktop application** the business uses on its own.

---

## What the product must cover

The full operating surface of a business, not one corner of it:

finance · sales · marketing · HR · operations · inventory · compliance ·
customer health

And within that: monitoring, insight, observability, **forward-looking
precaution**, risk management, and strategy — not only what has happened, but
what is coming and what to do about it.

---

## Standards Tejas set

- **Production level, complete and robust.** Explicitly: *"I don't want to
  make basic changes in future and don't need a 'jugad' thing."*
- **Taking another year to eighteen months is acceptable** if the result is
  right. Speed is not the constraint; durability is.
- **Free tooling for now.** No paid tiers or subscriptions yet. A separate
  reference of the best paid options is wanted eventually, not now.
- **Security first**, throughout, not retrofitted.

---

## How to read this when deciding something

When a design choice is ambiguous, these are the tie-breakers, in order:

1. **Does it keep one business's data unreachable from another's?** If not,
   it is wrong regardless of its other merits.
2. **Would this need rebuilding at 30 clients?** If yes, build it properly now.
   That is what the eighteen-month allowance is for.
3. **Does it speak the business's language or the system's?** A finance lead
   reading "drift" or "model" is a defect.
4. **Is it honest when uncertain?** The product's value rests on being
   trusted; a confident wrong answer costs more than an admitted unknown.
