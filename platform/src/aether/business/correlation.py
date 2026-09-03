"""Co-movement in one business's own history.

`relations.yaml` says how businesses work in general. This module asks a
narrower and more useful question: does *this* company's history actually show
the pattern?

The statistics here are deliberately timid, because the naive version of this
feature is worse than not having it. Three domains give a couple of hundred
cross-domain metric pairs, and an SME reports perhaps a dozen times a year. At
any conventional significance threshold you will find several strong-looking
correlations in pure noise, every single run, for every single tenant. A
product that surfaced those would be generating confident nonsense at scale.

So four defences, and the last one matters most:

  - **Changes, not levels.** Two metrics that both drift upward correlate
    almost perfectly whether or not they have anything to do with each other.
    Correlating first differences asks whether they move *together*, which is
    the actual question.

  - **Rank correlation.** Spearman rather than Pearson. Business series are
    lumpy — one large invoice, one quarterly bill — and a single outlier can
    manufacture a Pearson correlation on a short series.

  - **A high bar and a real minimum.** |rho| >= 0.7 over at least 8 aligned
    pairs. Below that there is nothing honest to say.

  - **Discovery never speaks on its own.** A co-movement can corroborate a
    relation that was declared in advance, and it can be recorded as a
    candidate for a human to look at. It cannot become a finding by itself.
    That is the whole difference between evidence and data dredging, and with
    these sample sizes it is not a close call.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass

from sqlalchemy import select

from aether.business.relations import Relation, all_relations
from aether.core.db import tenant_session
from aether.core.models import Observation

# Below this many aligned pairs there is nothing honest to say. Kept high
# relative to the data available on purpose: a correlation over five points
# is a coincidence with a decimal place.
MIN_PAIRS = 8

# Deliberately far above conventional significance. With this many candidate
# pairs and this little history, a threshold that admits "interesting" results
# admits mostly noise.
STRONG_RHO = 0.7

# Two readings from different domains count as contemporaneous within this
# window. Domains report on their own schedules — receivables weekly, cash
# fortnightly — so exact timestamps never line up.
DEFAULT_TOLERANCE_HOURS = 14 * 24.0


@dataclass(frozen=True)
class Series:
    """One metric's history for one tenant, oldest first."""

    domain: str
    metric: str
    points: tuple[tuple[datetime.datetime, float], ...]

    def __len__(self) -> int:
        return len(self.points)


@dataclass(frozen=True)
class CoMovement:
    """Two metrics from different domains that moved together."""

    domain_a: str
    metric_a: str
    domain_b: str
    metric_b: str
    rho: float
    pairs: int
    # The declared relation this supports, if any. None means the pattern was
    # discovered rather than predicted — interesting, and not to be shown to
    # a customer on that basis alone.
    corroborates: str | None = None

    @property
    def predicted(self) -> bool:
        return self.corroborates is not None

    def as_dict(self) -> dict:
        return {
            "a": f"{self.domain_a}.{self.metric_a}",
            "b": f"{self.domain_b}.{self.metric_b}",
            "rho": round(self.rho, 3),
            "pairs": self.pairs,
            "corroborates": self.corroborates,
            "predicted": self.predicted,
        }


# ── Statistics, written out rather than imported ─────────────────────────────
# scipy would be a heavy dependency for two short functions over a dozen
# points, and the arithmetic is worth being able to read here.


def _ranks(values: list[float]) -> list[float]:
    """Ranks, averaging ties. Ties are common in business data — a metric
    that sat unchanged for three periods must not get an arbitrary order."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Rank correlation, or None when it is undefined.

    Returns None rather than 0.0 when either series is constant: no
    correlation *exists* there, which is a different statement from "these do
    not move together", and collapsing the two would let flat data look like
    evidence of independence.
    """
    if len(xs) != len(ys) or len(xs) < 3:
        return None

    rx, ry = _ranks(xs), _ranks(ys)
    n = len(rx)
    mean_x = sum(rx) / n
    mean_y = sum(ry) / n

    cov = sum((a - mean_x) * (b - mean_y) for a, b in zip(rx, ry, strict=True))
    var_x = sum((a - mean_x) ** 2 for a in rx)
    var_y = sum((b - mean_y) ** 2 for b in ry)

    if var_x == 0 or var_y == 0:
        return None
    return cov / ((var_x * var_y) ** 0.5)


def changes(values: list[float]) -> list[float]:
    """First differences. One shorter than the input."""
    return [b - a for a, b in zip(values, values[1:], strict=False)]


def align(
    a: Series, b: Series, tolerance_hours: float = DEFAULT_TOLERANCE_HOURS
) -> tuple[list[float], list[float]]:
    """Pair readings from two domains that describe the same moment.

    Each reading in `a` takes the nearest reading in `b` within the window, and
    no reading in `b` is used twice — otherwise a single cash reading could
    pair with six receivables readings and manufacture a correlation out of one
    observation repeated.
    """
    used: set[int] = set()
    xs: list[float] = []
    ys: list[float] = []

    for when, value in a.points:
        best: int | None = None
        best_gap = tolerance_hours
        for i, (other_when, _) in enumerate(b.points):
            if i in used:
                continue
            gap = abs((when - other_when).total_seconds()) / 3600.0
            if gap <= best_gap:
                best, best_gap = i, gap
        if best is not None:
            used.add(best)
            xs.append(value)
            ys.append(b.points[best][1])

    return xs, ys


def co_movement(
    a: Series, b: Series, tolerance_hours: float = DEFAULT_TOLERANCE_HOURS
) -> CoMovement | None:
    """Whether two series moved together, or None if there is nothing to say."""
    if a.domain == b.domain:
        return None  # within-domain relationships belong to the pack

    xs, ys = align(a, b, tolerance_hours)
    # One pair is consumed by differencing, so require the minimum *after* it.
    if len(xs) < MIN_PAIRS + 1:
        return None

    rho = spearman(changes(xs), changes(ys))
    if rho is None or abs(rho) < STRONG_RHO:
        return None

    return CoMovement(
        domain_a=a.domain,
        metric_a=a.metric,
        domain_b=b.domain,
        metric_b=b.metric,
        rho=rho,
        pairs=len(xs) - 1,
    )


# ── Against the declared relations ───────────────────────────────────────────


def _relation_pairs(relation: Relation) -> list[tuple[tuple[str, str], tuple[str, str]]]:
    """Every cross-domain leg pairing a relation asserts."""
    pairs = []
    legs = relation.legs
    for i, first in enumerate(legs):
        for second in legs[i + 1 :]:
            if first.domain != second.domain:
                pairs.append(((first.domain, first.metric), (second.domain, second.metric)))
    return pairs


def evidence(
    series: dict[tuple[str, str], Series],
    tolerance_hours: float = DEFAULT_TOLERANCE_HOURS,
) -> list[CoMovement]:
    """Co-movements that support a relation someone declared in advance.

    This is the honest half of the feature. The hypothesis was written down
    before the data was examined, so finding it in the history is evidence
    rather than a result of looking at two hundred pairs and reporting the
    ones that happened to line up.
    """
    found: list[CoMovement] = []

    for relation in all_relations():
        for (domain_a, metric_a), (domain_b, metric_b) in _relation_pairs(relation):
            a = series.get((domain_a, metric_a))
            b = series.get((domain_b, metric_b))
            if a is None or b is None:
                continue
            result = co_movement(a, b, tolerance_hours)
            if result is None:
                continue
            found.append(
                CoMovement(
                    domain_a=result.domain_a,
                    metric_a=result.metric_a,
                    domain_b=result.domain_b,
                    metric_b=result.metric_b,
                    rho=result.rho,
                    pairs=result.pairs,
                    corroborates=relation.id,
                )
            )

    found.sort(key=lambda c: abs(c.rho), reverse=True)
    return found


def candidates(
    series: dict[tuple[str, str], Series],
    tolerance_hours: float = DEFAULT_TOLERANCE_HOURS,
) -> list[CoMovement]:
    """Co-movements nobody predicted, for a human to look at.

    Never for a customer. This is the output of testing every pair against a
    dozen readings, which is precisely the procedure that produces convincing
    nonsense — the value is in a person reading the list and occasionally
    recognising a real mechanism worth adding to relations.yaml.
    """
    predicted = {
        frozenset({(c.domain_a, c.metric_a), (c.domain_b, c.metric_b)})
        for c in evidence(series, tolerance_hours)
    }

    keys = sorted(series)
    found: list[CoMovement] = []

    for i, key_a in enumerate(keys):
        for key_b in keys[i + 1 :]:
            if frozenset({key_a, key_b}) in predicted:
                continue
            result = co_movement(series[key_a], series[key_b], tolerance_hours)
            if result is not None:
                found.append(result)

    found.sort(key=lambda c: abs(c.rho), reverse=True)
    return found


# ── Loading ──────────────────────────────────────────────────────────────────


def load_series(tenant_id: uuid.UUID, limit_per_domain: int = 60) -> dict[tuple[str, str], Series]:
    """Every metric's history for one tenant, oldest first.

    Accepted readings only, for the same reason BusinessState uses them: a
    reading the quality gate refused is not evidence, and letting one into a
    correlation would be worse than a missing point.
    """
    with tenant_session(tenant_id) as db:
        rows = db.scalars(
            select(Observation)
            .where(Observation.status == "accepted")
            .order_by(Observation.observed_at.desc(), Observation.seq.desc())
            .limit(limit_per_domain * 12)
        ).all()

    buckets: dict[tuple[str, str], list[tuple[datetime.datetime, float]]] = {}
    for obs in reversed(rows):  # oldest first
        for metric, value in (obs.metrics or {}).items():
            if isinstance(value, int | float):
                buckets.setdefault((obs.domain, metric), []).append((obs.observed_at, float(value)))

    return {
        key: Series(domain=key[0], metric=key[1], points=tuple(points))
        for key, points in buckets.items()
    }
