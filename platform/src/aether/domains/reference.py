"""What normal looks like in an industry, from a citable source.

Reads `reference/damodaran-working-capital-2026-01.csv`, which is committed
and reviewable — see D38 for why the CSV rather than the workbook it came
from, and `reference/README.md` for the provenance and the checks.

**These are US public companies, and that limit must survive into the
product.** An SME's DSO is not a listed company's DSO: small firms have worse
terms and less leverage over customers. What transfers is the *ordering*
across sectors — grocery retail collects in days, engineering firms in months
— rather than the levels. So a figure from here is a starting point that a
tenant's own history is expected to move (3.3, 3.6), never a verdict.

**A sector's figure is the median of its industries, not the mean.** Sectors
name two to four industries each, and a single distorted one would drag a mean
badly. Advertising is the known case: agencies report commission revenue while
carrying gross client billings, which puts their apparent DSO near 173 days.
The median resists that; with two to four values it otherwise differs from the
mean hardly at all, so the robustness is close to free.

**Firm counts are deliberately not used as weights.** They record how many
*listed* companies an industry has, which is a fact about capital markets
rather than about the businesses Aether serves. Weighting by them would let
the number of public software companies decide what a bakery is judged
against.
"""

from __future__ import annotations

import csv
import functools
import pathlib

# reference/ sits beside platform/, at the repository root.
_REFERENCE_DIR = pathlib.Path(__file__).resolve().parents[4] / "reference"
_TABLE = _REFERENCE_DIR / "damodaran-working-capital-2026-01.csv"

# Columns a pack metric may name. Anything else is a typo, and saying so is
# better than seeding nothing and looking correct.
COLUMNS = (
    "implied_dso_days",
    "implied_dio_days",
    "implied_dpo_days",
    "ar_over_sales",
    "inventory_over_sales",
    "ap_over_sales",
    "noncash_wc_over_sales",
)


class ReferenceUnavailable(RuntimeError):
    """The reference table is missing or unreadable."""


@functools.lru_cache(maxsize=1)
def table() -> dict[str, dict[str, float]]:
    """Industry name -> column -> value, skipping blanks.

    Blanks are real and meaningful: the financial industries carry them
    exactly where a working-capital figure belongs, because what they report
    as revenue is not comparable to what they are owed. A blank is absence of
    evidence and is left absent rather than filled with a zero, which would
    read as "they collect instantly".
    """
    if not _TABLE.exists():
        raise ReferenceUnavailable(f"reference table missing at {_TABLE}")

    with _TABLE.open(encoding="utf-8") as fh:
        rows = [r for r in csv.reader(fh) if r and not r[0].startswith("#")]
    if not rows:
        raise ReferenceUnavailable(f"reference table at {_TABLE} has no rows")

    header, *body = rows
    out: dict[str, dict[str, float]] = {}
    for row in body:
        record = dict(zip(header, row, strict=True))
        figures = {}
        for column in COLUMNS:
            raw = (record.get(column) or "").strip()
            if raw:
                figures[column] = float(raw)
        out[record["industry"]] = figures
    return out


def industries() -> tuple[str, ...]:
    return tuple(table())


def figure(industry: str, column: str) -> float | None:
    """One industry's value for one column, or None if it has none."""
    if column not in COLUMNS:
        raise ValueError(f"unknown reference column {column!r}; known: {', '.join(COLUMNS)}")
    return table().get(industry, {}).get(column)


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def for_industries(names: tuple[str, ...] | list[str], column: str) -> float | None:
    """The reference figure for a group of industries, or None if none have it.

    The median, for the reasons in the module docstring. Returns None rather
    than a default so a caller can tell "no evidence" from "the evidence says
    zero" — those are different situations and only one of them should reach a
    customer as a band.
    """
    values = [v for name in names if (v := figure(name, column)) is not None]
    return _median(values) if values else None
