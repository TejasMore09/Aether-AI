# Start here

This folder is the project's memory. It exists because the sessions building
Aether do not persist — each one starts cold — so anything not written down is
lost when a conversation ends.

**If you are a fresh session picking this up, read these four files in order
before writing any code.**

| File | What it holds |
|---|---|
| [VISION.md](VISION.md) | What Tejas is building and why. The thing being aimed at. |
| [PLAN.md](PLAN.md) | Ten phases, with tasks. **Carries the current position marker.** |
| [DECISIONS.md](DECISIONS.md) | Choices already made, with reasons. Do not re-litigate these. |
| [PROGRESS.md](PROGRESS.md) | Dated log of what actually shipped. |
| [DATA.md](DATA.md) | Where the real numbers come from. The largest open risk. |
| [../System_Requirements_fromTejas.md](../System_Requirements_fromTejas.md) | Everything needed from Tejas: data, keys, services, decisions. |

Then read `/ARCHITECTURE.md` for how the system is built, and
`/platform/README.md` for how to run it.

---

## Current position

> **Phase 3 — Sector awareness.** Phases 0, 1 and 2 are complete.
>
> 478 tests, none skipped. An agent now remembers its own business: pgvector
> under RLS, local embeddings, tenant-scoped retrieval, and past decisions
> recalled into the explanation an approver reads. Staff can see how much an
> agent remembers and never what.
>
> **6.4 was pulled forward** out of Phase 6: password endpoints accepted
> unlimited guesses, which was a live hole rather than a missing feature.
>
> **Phase 3 is underway.** `3.0`–`3.4` done: money is the tenant's own
> currency throughout, **a bakery and a builders' merchant reporting the same
> 50-day DSO get different verdicts**, a business picks its sector while seeing
> exactly what that changes, and its agent knows what is normal in its
> industry. Next is 3.5, sector-specific metrics.
>
> Next: Phase 3, where a stock brokerage and a bakery stop receiving
> byte-identical packs. The code is days; the defensible numbers are not,
> and need Tejas's domain access.
>
> **Worth a human read:** `platform/src/aether/business/relations.yaml` holds
> claims about how businesses work, and
> `platform/src/aether/knowledge/embedding.py` records what the embedding
> model can and cannot actually distinguish. No test can tell you whether
> either is right.

That block is the pointer. Update it whenever a phase starts or finishes, and
never let it disagree with the checkboxes in `PLAN.md`.

---

## Working rules

These are not bureaucracy; each exists because losing it costs real time.

**Update `PROGRESS.md` after every meaningful piece of work.** Not every
commit — every thing a person would call "done". One entry, dated, with what
changed and what it cost.

**Move the pointer above when a phase boundary is crossed.** A fresh session
reads that block first and trusts it.

**Add to `DECISIONS.md` whenever a choice is made that a later session might
reverse by accident.** The test is: would someone reasonable, arriving cold,
plausibly do the opposite? If yes, write down why we did not.

**Update `/ARCHITECTURE.md` when the system's shape changes** — a new service,
a new table, a new boundary. Not for ordinary features.

**Keep the honesty.** These documents are useful only while they describe what
is actually true. A plan that overstates progress is worse than no plan,
because it removes the thing that would have prompted a correction. If
something is half-built, say half-built. If a number was guessed, say guessed.

---

## What this project is not, yet

Written here because it is the fastest way for a new session to avoid claiming
too much:

- **No real business data has ever touched this.** Every threshold, band and
  economic constant is a considered guess, tuned against invented scenarios.
  This is the single largest source of risk in the product.
- **No machine learning.** There are no models. The system is curated
  economics, per-tenant statistical calibration, and an LLM writing prose.
- **Nothing is deployed.** It runs on a laptop.
- **Mega does not exist.** It is an enum value and an API that refuses.

None of that is a defect to hide. It is the map of what is left.
