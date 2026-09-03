"""What is normal in this industry, as something the agent knows.

Phase 3.2 made a builders' merchant judged against 50 days rather than 45.
Phase 3.3 told them so while they were choosing. This is the third piece and
the one that closes the loop: the *explanation* has to know it too, or a
customer reads "your collection period is above the healthy threshold" against
a threshold nobody accounted for.

**Every sentence here is derived from the committed reference table.** Nothing
is written from general knowledge about industries, however plausible it would
sound. "Construction businesses have long payment cycles because of retentions
and milestone billing" is probably true and I cannot cite it, and a knowledge
base that mixes citable figures with confident-sounding invention is worse
than one with fewer facts — because nothing downstream can tell which is
which. When Phase 7 brings document ingest, a business can add their own
industry material and that will be attributable to them.

**This is a lookup, not a search, and saying so matters.** A tenant has
exactly one sector. Asking a vector index which sector they are in would
return the only candidate and call it a match — theatre, and the kind that
looks like sophistication in a demo. Similarity earns its place where there
are many memories and the question is which few are relevant; here the answer
is "the one". It is still written into the knowledge base rather than computed
on demand, because it is genuinely part of what this agent knows, it must be
visible in the chunk counts the fleet view reports (2.6), and the corpus is
where real industry documents will land later.

**A tenant holds one sector memory at a time.** Changing sector replaces it
rather than adding to it: an agent that remembered being both a retailer and a
builders' merchant would have two contradictory normals and no way to choose.

Note for whoever adds a second reference source: nothing here needs currency
handling because every figure in the table is a ratio or a number of days. A
source carrying actual amounts would be in *its* currency, and this platform
does not convert (D33), so those must not be quoted to a business counting in
something else.
"""

from __future__ import annotations

import logging
import uuid

from aether.domains import reference
from aether.domains.sector import UNSPECIFIED, Sector
from aether.knowledge import store
from aether.knowledge.embedding import EmbeddingUnavailable, embed_one

logger = logging.getLogger(__name__)

KIND_SECTOR = "sector"

# What the reference table can speak to, and the words for each. Only the
# first has a pack using it today; the other two are already true and become
# useful when Phase 5 adds payables and inventory.
_FIGURES = (
    ("implied_dso_days", "collect from customers in about {value} days"),
    ("implied_dio_days", "hold about {value} days of stock"),
    ("implied_dpo_days", "pay their own suppliers in about {value} days"),
)


def describe(sector: Sector) -> str | None:
    """One paragraph about this industry, or None when there is nothing to say.

    None is a real and common answer: three sectors have no reference figures
    at all. Returning a paragraph that says nothing would put an empty claim
    into the agent's memory and into its prompts.
    """
    if sector.key == UNSPECIFIED:
        return None

    clauses = []
    for column, phrasing in _FIGURES:
        value = reference.for_industries(sector.damodaran, column)
        if value is not None:
            clauses.append(phrasing.format(value=f"{value:.0f}"))

    if not clauses:
        # The sector is known and the evidence is not. Worth remembering
        # precisely because it stops the agent implying it knows.
        return (
            f"This business is in {sector.label.lower()}. "
            f"Aether has no reference figures for what is normal in this industry: "
            f"{sector.bands_note} "
            f"Do not state industry norms for this business; there are none to state."
        )

    listed = clauses[0] if len(clauses) == 1 else ", ".join(clauses[:-1]) + f" and {clauses[-1]}"
    return (
        f"This business is in {sector.label.lower()}. Published accounts of US companies "
        f"in this industry show that they {listed}. These are large listed companies, so "
        f"this business's own figures will differ — the comparison worth drawing is with "
        f"other industries, not with the exact number."
    )


def _meta(sector: Sector) -> dict:
    return {
        "sector": sector.key,
        "label": sector.label,
        "has_bands": sector.has_bands,
        "industries": list(sector.damodaran),
        "source": "reference/damodaran-working-capital-2026-01.csv",
    }


def index_sector(tenant_id: uuid.UUID, sector: Sector) -> uuid.UUID | None:
    """Record what this business's industry looks like. Safe to run repeatedly.

    Any previous sector memory is dropped first, because a tenant that changed
    from retail to construction must not keep remembering both.

    Returns None when there is nothing to record or embedding is unavailable.
    Never raises: the sector is already saved by the time this runs, and
    failing to remember it must not fail the change itself.
    """
    try:
        store.forget(tenant_id, kind=KIND_SECTOR)

        body = describe(sector)
        if body is None:
            return None

        return store.remember(
            tenant_id,
            kind=KIND_SECTOR,
            body=body,
            embedding=embed_one(body),
            meta=_meta(sector),
        )
    except EmbeddingUnavailable as exc:
        logger.warning("sector knowledge not indexed for %s: %s", tenant_id, exc)
        return None
    except Exception:  # noqa: BLE001 - see the docstring
        logger.warning("sector knowledge not indexed for %s", tenant_id, exc_info=True)
        return None


def current(tenant_id: uuid.UUID) -> store.Memory | None:
    """What this agent knows about its business's industry, if anything."""
    found = store.of_kind(tenant_id, KIND_SECTOR, limit=1)
    return found[0] if found else None


def context_line(tenant_id: uuid.UUID) -> str:
    """The industry paragraph for a prompt, or "" when there is none.

    Swallows its own failures. Industry context makes an explanation better
    and its absence makes one slightly thinner; neither is worth losing the
    explanation over.
    """
    try:
        memory = current(tenant_id)
    except Exception:  # noqa: BLE001 - see the docstring
        logger.warning("sector context unavailable for %s", tenant_id, exc_info=True)
        return ""
    return f"{memory.body}\n\n" if memory else ""
