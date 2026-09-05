# Aether

Aether watches the operating numbers of a small or mid-sized business, decides
when something is worth the owner's attention, and explains why in the
language of the business rather than the language of the system watching it.

One isolated agent per customer. A central brain that can operate the fleet
without being able to read inside it — except deliberately, temporarily, and
visibly to the customer.

**Status:** pre-release. Two business domains, no connectors, and no real
business data has touched any of it. It is deployable — one compose file, a
proxy that holds its own certificates, nightly backups that are restored and
checked before they count — but it has never run on a real host.

---

## What it actually does

A business reports its numbers — days sales outstanding, cash on hand, what is
committed to go out. Its agent scores them against bands that adapt to that
business's own history, works out what the current position is costing per
day, and compares that against the cost of doing something about it.

If acting is worth it, the agent stops and asks a named human. It never acts
on a business system by itself.

Every decision, and every explanation of one, is written to an append-only
trail the customer can read.

---

## Running it

Needs Docker and Node. Two commands.

```bash
cd platform && docker compose up -d
```

Postgres, Temporal, the migrations and all three APIs. Then the dashboard at
http://localhost:3000:

```bash
cd platform/web && npm install && npm run dev
```

Nothing needs configuring first: the development secrets ship in the
repository so a checkout works with no `.env` at all, and a production process
refuses to start on them rather than quietly using them.

`platform/README.md` covers the rest — the staff console, the monitor worker,
running the tests, and what needs configuring before any of it is real.
`deploy/README.md` covers putting it on a machine, including what "free tier"
honestly means for a stack this size.

---

## Reading the code

| Where | What |
|---|---|
| [roadmap/](roadmap/) | **start here** — vision, plan, current position, decisions |
| [ARCHITECTURE.md](ARCHITECTURE.md) | how the system fits together, and why |
| [platform/README.md](platform/README.md) | running it, operating it, extending it |
| `platform/src/aether/domains/` | domain packs — the product's surface area |
| `platform/src/aether/policy/` | the decision engine |
| `platform/src/aether/main_brain/` | fleet control and break-glass access |

The interesting decisions are documented where they were made rather than
here: why isolation is enforced by Postgres and not by application code, why
healthy bands adapt but only within limits, why some breaches skip the
cost-benefit test entirely. Each has a comment next to the code that depends
on it.

---

## Tests

```bash
cd platform && .venv/Scripts/python -m pytest
```

669 tests, none skipped. Tenant isolation is proven by test rather than
asserted by design, and the break-glass gate is mutation-checked — stubbing it
to always pass fails five tests, so they are load-bearing rather than
decorative.

The tests worth reading are the ones aimed at the checkers: the backup
verifier is handed a dump containing none of anyone's rows and has to notice,
and the forecast backtest has to be able to detect an interval that is lying.
