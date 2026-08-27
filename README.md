# Aether

Aether watches the operating numbers of a small or mid-sized business, decides
when something is worth the owner's attention, and explains why in the
language of the business rather than the language of the system watching it.

One isolated agent per customer. A central brain that can operate the fleet
without being able to read inside it — except deliberately, temporarily, and
visibly to the customer.

**Status:** pre-release. Two business domains, no connectors, nothing
deployed. Everything below runs locally.

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

Needs Docker and Python 3.12+.

```bash
cd platform
docker compose up -d db
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/alembic upgrade head
```

Then the services, each in its own shell:

```bash
.venv/Scripts/uvicorn aether.control_plane.app:app --port 8100 --reload
```

```bash
.venv/Scripts/uvicorn aether.agent_runtime.app:app --port 8200 --reload
```

The customer dashboard, at http://localhost:3000:

```bash
cd platform/web && npm install && npm run dev
```

`platform/README.md` covers the rest — the staff console, the monitor worker,
domain packs, and what needs configuring before any of it is real.

---

## Reading the code

| Where | What |
|---|---|
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

160 tests. Tenant isolation is proven by test rather than asserted by design,
and the break-glass gate is mutation-checked — stubbing it to always pass
fails five tests, so they are load-bearing rather than decorative.
