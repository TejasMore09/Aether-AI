"""Per-tenant healthy bands, anchored to the pack's published defaults.

A pack ships one band per metric — 45 days DSO is healthy, 90 is critical.
Those numbers are a reasonable starting point and a bad permanent answer. A
construction supplier on 60-day terms is not unhealthy; a SaaS business at 60
days is in trouble. Judged against a single fixed band, the first gets alarmed
at forever and learns to ignore us, which is the worse of the two failures.

So the band moves with the tenant. The hard part is that it must not move
freely, because the obvious version of this idea is broken: a business that has
*always* run 40% of its book overdue would learn that 40% is normal and go
quiet exactly when it should not. Pure "learn what's normal" anomaly detection
normalises dysfunction, and on business metrics dysfunction is often stable.

The resolution is anchoring. The tenant's own history proposes a band; the
pack's published band constrains how far that proposal may travel, expressed
as a fraction of the distance between healthy and critical. A tenant can say
"our normal is looser than your default" and be believed up to a point. They
cannot say "our normal is critical".

Two further properties, both deliberate:

  - The critical bound never moves. It is the absolute line, not a negotiable
    preference, and a tenant whose healthy band drifts toward it gets a
    steeper scoring curve as a result — which is correct. Their normal really
    is closer to trouble.

  - The result is always explainable. Every score carries the band it used,
    where that band came from, and how many readings produced it, so a
    customer asking "why is this amber?" gets an answer rather than a number.
"""

from __future__ import annotations

from dataclasses import dataclass

from aether.domains.pack import Direction, DomainPack, MetricSpec


@dataclass(frozen=True)
class Band:
    """The bounds actually used to score one metric, and their provenance."""

    good: float
    bad: float
    source: str  # "pack" | "tenant"
    readings: int = 0

    def as_dict(self) -> dict:
        return {
            "good": round(self.good, 4),
            "bad": round(self.bad, 4),
            "source": self.source,
            "readings": self.readings,
        }


def _quantile(values: list[float], q: float) -> float:
    """Linear-interpolated quantile.

    Written out rather than reaching for numpy: the platform has no array
    dependency, and this runs over a dozen readings, not a million.
    """
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = q * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def pack_band(spec: MetricSpec) -> Band | None:
    """The pack's published band, or None if this metric is not scored."""
    if not spec.scored:
        return None
    if spec.direction is Direction.lower_better:
        good, bad = spec.healthy_max, spec.critical_max
    else:
        good, bad = spec.healthy_min, spec.critical_min
    if good is None or bad is None or good == bad:
        return None
    return Band(good=good, bad=bad, source="pack")


def calibrate(
    spec: MetricSpec,
    past: list[float],
    pack: DomainPack,
) -> Band | None:
    """The band this tenant should actually be judged against.

    Falls back to the pack's band whenever there is not enough history to say
    anything honest. An unknown is not a signal, and a band inferred from three
    readings is an unknown wearing a number.
    """
    base = pack_band(spec)
    if base is None:
        return None

    usable = [v for v in past if v is not None]
    if len(usable) < pack.calibration_min_readings:
        return base

    span = abs(base.bad - base.good)
    if span == 0:
        return base

    if spec.direction is Direction.lower_better:
        # Their own upper edge of routine. p75 rather than the median: the
        # healthy bound should sit at the top of normal, not the middle of it,
        # or three quarters of ordinary weeks would score as unhealthy.
        proposed = _quantile(usable, 0.75)
        loosest = base.good + pack.calibration_max_loosen * span
        tightest = base.good - pack.calibration_max_tighten * span
        good = min(max(proposed, tightest), loosest)
        if spec.minimum is not None:
            good = max(good, spec.minimum)
    else:
        proposed = _quantile(usable, 0.25)
        loosest = base.good - pack.calibration_max_loosen * span
        tightest = base.good + pack.calibration_max_tighten * span
        good = max(min(proposed, tightest), loosest)
        if spec.maximum is not None:
            good = min(good, spec.maximum)

    return Band(good=good, bad=base.bad, source="tenant", readings=len(usable))


def score_against(spec: MetricSpec, value: float, band: Band) -> float:
    """Map a value onto 0..1 against a specific band.

    The same linear interpolation MetricSpec.health_score performs, against
    supplied bounds rather than the pack's own — so calibration changes which
    band is used and nothing about how scoring works.
    """
    span = band.bad - band.good
    if span == 0:
        return 0.0
    score = 1.0 - ((value - band.good) / span)
    return max(0.0, min(1.0, score))


def history_for(key: str, history: list[dict[str, float]]) -> list[float]:
    """Past values of one metric, skipping readings that omitted it."""
    return [h[key] for h in history if h and key in h and h[key] is not None]
