"""Measuring how wrong the forecasts are, and publishing it.

A forecast that is never scored is a claim, not a measurement. This walks
forward through a metric's history, forecasts each point using only what was
known before it, and compares the answer to what actually happened.

**Coverage is the number that matters, not error size.** Average error tells
you how far off a projection was; coverage tells you whether the *interval*
was honest. The product says "80% confidence" on every projection, and if only
half the readings land inside, that sentence is a lie being told at scale. A
wide interval that is honest is worth more than a narrow one that is not,
because a customer can act on the first and is misled by the second.

**Nothing here knows whether its input is real.** The harness scores whatever
series it is given, which is correct for a tool and dangerous for a claim.
Scored against invented data it measures how well the forecast predicts a
series someone made up — a number that looks exactly like evidence and is
worth nothing. So `measure_fleet` reports how many tenants and readings a
figure came from and refuses to summarise below a floor, and the tests here
score synthetic data on purpose, to check the *arithmetic* rather than to
claim anything about accuracy.

Walk-forward, never in-sample. A model scored on the points it was fitted to
flatters itself, and the whole question is what happens to a reading it has
not seen.

**What this harness found, and it is not good news.** Measured coverage
against a stated 80%:

    line plus independent noise      0.78   honest
    random walk                      0.52   badly overconfident
    accelerating curve               0.12   uselessly overconfident

The intervals are trustworthy only where a metric behaves the way the model
assumes. Both failure shapes are ordinary in business data: a cash balance
wanders like a random walk, and a book that is deteriorating often accelerates
rather than sliding in a straight line. See D53 — this is a limitation of the
product, not of the harness, and it is why the horizon cap exists.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field

from aether.domains.forecast import (
    DEFAULT_CONFIDENCE,
    MIN_POINTS,
    NoForecast,
    Season,
    fit,
    project,
    seasonality,
)

# Below this a coverage figure is noise. Ten forecasts at 80% confidence means
# an expected two misses, and one either way moves the number by ten points.
MIN_FORECASTS = 20


@dataclass(frozen=True)
class Backtest:
    """How a metric's forecasts actually performed."""

    forecasts: int
    mean_absolute_error: float
    median_absolute_error: float
    # Fraction of actual readings that fell inside the stated interval. Should
    # land near `confidence` if the intervals are honest.
    coverage: float
    confidence: float
    horizon_days: float
    # Average width of the intervals quoted. This, rather than the error, is
    # what grows with the horizon on a correctly specified model: the point
    # estimate of a true line stays good, and it is the honesty about
    # uncertainty that has to widen.
    mean_interval_width: float = 0.0
    # Why forecasts could not be made, so a low count is explainable rather
    # than mysterious.
    skipped: dict[str, int] = field(default_factory=dict)

    @property
    def calibrated(self) -> bool:
        """Whether the interval means what it says, within sampling error.

        Ten points of slack: at these sample sizes coverage bounces around,
        and demanding exactness would fail honest intervals as often as
        dishonest ones.
        """
        return abs(self.coverage - self.confidence) <= 0.10

    def as_dict(self) -> dict:
        return {
            "forecasts": self.forecasts,
            "mean_absolute_error": round(self.mean_absolute_error, 4),
            "median_absolute_error": round(self.median_absolute_error, 4),
            "coverage": round(self.coverage, 4),
            "confidence": self.confidence,
            "horizon_days": self.horizon_days,
            "mean_interval_width": round(self.mean_interval_width, 4),
            "calibrated": self.calibrated,
            "skipped": dict(self.skipped),
        }


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def backtest(
    points: list[tuple[datetime.datetime, float]],
    *,
    horizon_days: float,
    confidence: float = DEFAULT_CONFIDENCE,
    use_seasonality: bool = True,
) -> Backtest | NoForecast:
    """Score every forecast this history could have made.

    For each reading, the model is fitted on everything at least
    `horizon_days` older and asked to project forward to it. Nothing after the
    reading is visible, so this is what the product would actually have said
    at the time.
    """
    if len(points) < MIN_POINTS + 1:
        return NoForecast.too_few_readings

    ordered = sorted(points, key=lambda p: p[0])
    errors: list[float] = []
    widths: list[float] = []
    inside = 0
    skipped: dict[str, int] = {}

    for index, (when, actual) in enumerate(ordered):
        cutoff = when - datetime.timedelta(days=horizon_days)
        history = [(t, v) for t, v in ordered[:index] if t <= cutoff]
        if len(history) < MIN_POINTS:
            skipped[NoForecast.too_few_readings.value] = (
                skipped.get(NoForecast.too_few_readings.value, 0) + 1
            )
            continue

        season: Season | None = None
        if use_seasonality:
            found = seasonality(history, confidence=confidence)
            season = found if isinstance(found, Season) else None

        trend = fit(history, confidence=confidence, season=season)
        if isinstance(trend, NoForecast):
            skipped[trend.value] = skipped.get(trend.value, 0) + 1
            continue

        # Days from the last *known* reading to the one being predicted.
        ahead = (when - history[-1][0]).total_seconds() / 86_400
        projected = project(trend, ahead)
        if isinstance(projected, NoForecast):
            skipped[projected.value] = skipped.get(projected.value, 0) + 1
            continue

        # The season was removed to fit; put it back to compare against a real
        # reading, or every forecast would be judged against a value the
        # business never saw.
        expected = projected.value
        lower, upper = projected.lower, projected.upper
        if season is not None:
            origin = history[0][0]
            offset = season.offsets[season.phase_of((when - origin).total_seconds() / 86_400)]
            expected += offset
            lower += offset
            upper += offset

        errors.append(abs(actual - expected))
        widths.append(upper - lower)
        if lower <= actual <= upper:
            inside += 1

    if len(errors) < MIN_FORECASTS:
        return NoForecast.too_few_readings

    return Backtest(
        forecasts=len(errors),
        mean_absolute_error=sum(errors) / len(errors),
        median_absolute_error=_median(errors),
        coverage=inside / len(errors),
        confidence=confidence,
        horizon_days=horizon_days,
        mean_interval_width=sum(widths) / len(widths),
        skipped=skipped,
    )


@dataclass(frozen=True)
class FleetAccuracy:
    """What the platform can honestly claim about its forecasts.

    Carries what it was measured on, because an accuracy figure without a
    sample size is a number in search of a decimal point.
    """

    tenants: int
    series: int
    forecasts: int
    coverage: float
    confidence: float
    mean_absolute_error: float
    calibrated: bool

    def as_dict(self) -> dict:
        return {
            "tenants": self.tenants,
            "series": self.series,
            "forecasts": self.forecasts,
            "coverage": round(self.coverage, 4),
            "confidence": self.confidence,
            "mean_absolute_error": round(self.mean_absolute_error, 4),
            "calibrated": self.calibrated,
        }


def measure_fleet(
    tenant_ids: list[uuid.UUID],
    *,
    horizon_days: float = 28.0,
    confidence: float = DEFAULT_CONFIDENCE,
) -> FleetAccuracy | None:
    """Score the platform's forecasts against every tenant's real history.

    Returns None when there is not enough real history to say anything, which
    is the honest answer today and will be for a while. **No real business has
    used this system**, so a figure produced now would describe how well the
    forecast predicts invented test data — which looks exactly like evidence
    and is worth nothing.

    Kept in the product rather than left as a script so that the day real
    history exists, measuring is one call rather than a project.
    """
    from aether.business.correlation import load_series

    every: list[Backtest] = []
    tenants_with_data = 0

    for tenant_id in tenant_ids:
        try:
            series = load_series(tenant_id)
        except Exception:  # noqa: BLE001 - one unreadable tenant must not stop the measurement
            continue

        scored_here = 0
        for points in series.values():
            result = backtest(list(points.points), horizon_days=horizon_days, confidence=confidence)
            if isinstance(result, Backtest):
                every.append(result)
                scored_here += 1
        if scored_here:
            tenants_with_data += 1

    if not every:
        return None

    total = sum(b.forecasts for b in every)
    weighted_coverage = sum(b.coverage * b.forecasts for b in every) / total
    weighted_error = sum(b.mean_absolute_error * b.forecasts for b in every) / total

    return FleetAccuracy(
        tenants=tenants_with_data,
        series=len(every),
        forecasts=total,
        coverage=weighted_coverage,
        confidence=confidence,
        mean_absolute_error=weighted_error,
        calibrated=abs(weighted_coverage - confidence) <= 0.10,
    )
