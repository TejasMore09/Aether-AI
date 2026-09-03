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


# How far a value may sit from the median and still be described by it, and
# how much of the group must be that close. See `for_industries`.
_AGREEMENT_TOLERANCE = 0.25


def _represents(values: list[float]) -> bool:
    """Whether the median actually describes this group, or merely sits in it.

    Found the hard way. The construction sector names Engineering/Construction
    and Homebuilding, whose collection periods are 100 and 7 days — a
    contractor bills clients and waits, a homebuilder sells houses for cash.
    Their median is 54 days, which describes neither of them, and Aether
    shipped it as "what is normal in construction".

    Averaging opposites is a different failure from a single distorted
    industry, and the median does not protect against it: with two values the
    median is exactly between them, and between two opposites is nowhere. So
    the group has to agree before its middle is treated as evidence.

    The rule is that at least half the values sit within a quarter of the
    median. That admits a group where most agree and one differs — three
    building-supply industries where a retail outlier is correctly ignored —
    and refuses one where nothing is near the middle.
    """
    if len(values) < 2:
        return True

    middle = _median(values)
    if middle == 0:
        return all(v == 0 for v in values)

    close = sum(1 for v in values if abs(v - middle) / abs(middle) <= _AGREEMENT_TOLERANCE)
    return close * 2 >= len(values)


def for_industries(names: tuple[str, ...] | list[str], column: str) -> float | None:
    """The reference figure for a group of industries, or None if there is none.

    The median, for the reasons in the module docstring — and only when the
    industries agree closely enough for a middle to mean anything.

    None rather than a default, so a caller can tell "no evidence" from "the
    evidence says zero". Those are different situations and only one of them
    should ever reach a customer as a band.
    """
    values = [v for name in names if (v := figure(name, column)) is not None]
    if not values or not _represents(values):
        return None
    return _median(values)
