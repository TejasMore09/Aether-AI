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

Since 3.2 there are three layers, not two: the pack's published band, then
the sector's reference figure, then the tenant's own history. Each anchors to
the one beneath it, so a builders' merchant's history is judged against what
is normal for builders' merchants rather than against a general default.

**The sector layer is clamped, and the clamp is the point.** Reference figures
come from US public companies, where an SME's levels are simply different —
but the *ordering* across sectors transfers: grocery retail collects in days,
engineering firms in months. Allowing the sector band to move only as far as
the pack's calibration allowance keeps that ordering while declining to bet on
the level. Where the two disagree wildly, the disagreement is far more likely
to be the reference's large-cap bias than a fact about small businesses, and
the clamp says exactly that.

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

from aether.domains import reference
from aether.domains.pack import Direction, DomainPack, MetricSpec
from aether.domains.sector import Sector


@dataclass(frozen=True)
class Band:
    """The bounds actually used to score one metric, and their provenance."""

    good: float
    bad: float
    source: str  # "pack" | "sector" | "tenant"
    readings: int = 0
    # What this band was derived from, in words a customer could be shown:
    # which sector, whether the figure was capped, how many readings. Phase
    # 3.6 turns this into the on-screen answer to "why is this amber?"
    basis: str = ""

    def as_dict(self) -> dict:
        payload = {
            "good": round(self.good, 4),
            "bad": round(self.bad, 4),
            "source": self.source,
            "readings": self.readings,
        }
        if self.basis:
            payload["basis"] = self.basis
        return payload


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


def _clamped(base: Band, proposed: float, spec: MetricSpec, pack: DomainPack) -> tuple[float, bool]:
    """Move `base.good` toward `proposed`, no further than the pack allows.

    Shared by the sector and tenant layers because they are the same kind of
    claim — "our normal is not your default" — differing only in what backs
    it. Returns the bound and whether the allowance bit, since a band that hit
    its cap is a different thing to report than one that did not.
    """
    span = abs(base.bad - base.good)
    if span == 0:
        return base.good, False

    loosest = base.good + pack.calibration_max_loosen * span
    tightest = base.good - pack.calibration_max_tighten * span
    if spec.direction is not Direction.lower_better:
        loosest, tightest = (
            base.good - pack.calibration_max_loosen * span,
            base.good + pack.calibration_max_tighten * span,
        )
        good = max(min(proposed, tightest), loosest)
        if spec.maximum is not None:
            good = min(good, spec.maximum)
    else:
        good = min(max(proposed, tightest), loosest)
        if spec.minimum is not None:
            good = max(good, spec.minimum)

    return good, good != proposed


def sector_band(spec: MetricSpec, pack: DomainPack, sector: Sector | None) -> Band | None:
    """The band for this metric in this sector, or None if there is none.

    None is the common answer and not a failure: most metrics have no
    published reference figure, several sectors have no usable one, and a
    business may not have said what it does. Each of those falls through to
    the pack's band, which is what happened for every tenant before 3.2.
    """
    base = pack_band(spec)
    if base is None or not spec.reference or sector is None or not sector.has_bands:
        return None

    proposed = reference.for_industries(sector.damodaran, spec.reference)
    if proposed is None:
        return None

    good, capped = _clamped(base, proposed, spec, pack)
    basis = f"{sector.label}, from published figures for {len(sector.damodaran)} industries"
    if capped:
        # Worth saying rather than hiding. A capped band means the reference
        # and the pack disagree by more than the pack is willing to concede,
        # which a customer looking at an unexpected verdict deserves to know.
        basis += f" (reference said {proposed:g}, capped at the pack's allowance)"
    return Band(good=good, bad=base.bad, source="sector", basis=basis)


def calibrate(
    spec: MetricSpec,
    past: list[float],
    pack: DomainPack,
    sector: Sector | None = None,
) -> Band | None:
    """The band this tenant should actually be judged against.

    Falls back to the pack's band whenever there is not enough history to say
    anything honest. An unknown is not a signal, and a band inferred from three
    readings is an unknown wearing a number.
    """
    # The tenant anchors to their sector where one exists, and to the pack
    # otherwise. A builders' merchant's own history should be read against
    # what is normal for builders' merchants, not against a general default.
    base = sector_band(spec, pack, sector) or pack_band(spec)
    if base is None:
        return None

    usable = [v for v in past if v is not None]
    if len(usable) < pack.calibration_min_readings:
        return base

    if abs(base.bad - base.good) == 0:
        return base

    # Their own edge of routine. p75 (or p25) rather than the median: the
    # healthy bound should sit at the top of normal, not the middle of it, or
    # three quarters of ordinary weeks would score as unhealthy.
    quantile = 0.75 if spec.direction is Direction.lower_better else 0.25
    good, _ = _clamped(base, _quantile(usable, quantile), spec, pack)

    anchor = f" against {base.basis}" if base.source == "sector" else ""
    return Band(
        good=good,
        bad=base.bad,
        source="tenant",
        readings=len(usable),
        basis=f"this client's own normal from {len(usable)} readings{anchor}",
    )


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
