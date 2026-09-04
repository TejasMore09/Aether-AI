"""Where a metric is heading, and when to say nothing instead.

The system is entirely reactive: it can say a book is at 58 days, not that it
will cross 90 in five weeks. "Future precautions" is most of what an owner
wants from something watching their business, and this is the arithmetic under
it.

Ordinary least squares against elapsed time. Not a heavier method, because
weekly readings give roughly fifty points a year and fifty points support a
line and a season and nothing more. Reaching for anything larger would be
fitting noise with more parameters and calling it sophistication.

Four decisions shape this, and three of them are about refusing.

**A prediction interval, not a confidence interval.** They are different
things and the difference is not academic. A confidence interval says where
the *average* future reading probably sits; a prediction interval says where
*next Tuesday's* reading probably sits, and it is much wider. An owner asking
"where will my DSO be in six weeks" is asking the second question, and
answering with the first would make every forecast look several times more
precise than it is.

**No trend is a real answer.** If the fitted slope cannot be distinguished
from zero at the stated confidence, there is no trend to report, and saying
"your DSO is rising" because the line happens to tilt is inventing a signal
out of noise. Refusing is not a failure mode here; it is the correct output
for a business that is simply steady.

**Extrapolation has a range, and the interval cannot enforce it.** The
interval measures uncertainty given that a line is the right shape; it has no
way to say the shape itself is wrong by then, which is the assumption that
fails first. So there is a hard rule alongside it: never project further ahead
than the history reaches back.

**Thin history refuses outright.** Two points define a line exactly and tell
you nothing about whether it means anything; the residual variance that makes
an interval honest needs several more.

The t-distribution is written out rather than pulled from scipy, for the same
reason the rank correlation was: one table of constants against a dependency
that brings a compiler with it.
"""

from __future__ import annotations

import datetime
import math
from dataclasses import dataclass
from enum import StrEnum

# Below this there is nothing honest to say. Matches the calibration minimum:
# the number of readings it takes before this tenant's own history is treated
# as evidence about anything.
MIN_POINTS = 8

# We do not predict further ahead than we have been watching.
#
# This is not belt-and-braces over the interval, and the distinction matters.
# A prediction interval measures uncertainty *given that the line is the right
# shape*. It cannot express "a straight line is the wrong model by then" —
# which is the assumption that fails first on business data. Measured on
# twelve noisy weekly readings, the interval at a year out is 117 to 153 days
# DSO: arithmetically correct, and a confident-sounding claim no business
# metric earns from three months of history.
#
# So the cap covers what the interval structurally cannot. One-to-one is the
# rule because it is defensible and easy to say: twelve weeks of readings
# support a twelve-week projection, and the interval widens honestly across it.
MAX_HORIZON_RATIO = 1.0

DEFAULT_CONFIDENCE = 0.80

# Two-sided critical values, indexed by degrees of freedom. 80% is the default
# because a 95% interval on a dozen noisy weekly readings is wide enough to
# contain both "fine" and "in trouble" — true, and useless to act on. The level
# is stated on every forecast so nobody has to guess which was used.
_T_TWO_SIDED: dict[float, dict[int, float]] = {
    0.80: {
        1: 3.078,
        2: 1.886,
        3: 1.638,
        4: 1.533,
        5: 1.476,
        6: 1.440,
        7: 1.415,
        8: 1.397,
        9: 1.383,
        10: 1.372,
        11: 1.363,
        12: 1.356,
        13: 1.350,
        14: 1.345,
        15: 1.341,
        16: 1.337,
        17: 1.333,
        18: 1.330,
        19: 1.328,
        20: 1.325,
        21: 1.323,
        22: 1.321,
        23: 1.319,
        24: 1.318,
        25: 1.316,
        26: 1.315,
        27: 1.314,
        28: 1.313,
        29: 1.311,
        30: 1.310,
    },
    0.95: {
        1: 12.706,
        2: 4.303,
        3: 3.182,
        4: 2.776,
        5: 2.571,
        6: 2.447,
        7: 2.365,
        8: 2.306,
        9: 2.262,
        10: 2.228,
        11: 2.201,
        12: 2.179,
        13: 2.160,
        14: 2.145,
        15: 2.131,
        16: 2.120,
        17: 2.110,
        18: 2.101,
        19: 2.093,
        20: 2.086,
        21: 2.080,
        22: 2.074,
        23: 2.069,
        24: 2.064,
        25: 2.060,
        26: 2.056,
        27: 2.052,
        28: 2.048,
        29: 2.045,
        30: 2.042,
    },
}
# Beyond thirty degrees of freedom the t distribution is close enough to
# normal that the difference is smaller than anything this data can resolve.
_T_LARGE_SAMPLE = {0.80: 1.282, 0.95: 1.960}


class NoForecast(StrEnum):
    """Why there is nothing to say. Each is shown to a customer as a sentence.

    Kept as an enum rather than a bare None so the product can tell "we have
    not watched you long enough" from "you are steady" — the first is a matter
    of time and the second is good news, and collapsing them into silence
    would lose both.
    """

    too_few_readings = "too_few_readings"
    no_time_span = "no_time_span"
    no_detectable_trend = "no_detectable_trend"
    horizon_too_far = "horizon_too_far"
    not_within_horizon = "not_within_horizon"
    heading_away = "heading_away"


REASONS: dict[NoForecast, str] = {
    NoForecast.too_few_readings: (
        f"Fewer than {MIN_POINTS} readings. There is not enough history to tell a "
        f"direction from noise yet."
    ),
    NoForecast.no_time_span: (
        "Every reading carries the same timestamp, so there is no elapsed time to project along."
    ),
    NoForecast.no_detectable_trend: (
        "No trend that can be told apart from ordinary variation. This metric is "
        "holding steady as far as the readings can show."
    ),
    NoForecast.horizon_too_far: (
        "Further ahead than we have been watching. A projection cannot reach past "
        "the history behind it — the arithmetic would still produce a number, and "
        "it would not mean anything."
    ),
    NoForecast.not_within_horizon: (
        "Heading that way, but not soon enough to say when. The threshold sits "
        "further out than this history can speak to."
    ),
    NoForecast.heading_away: (
        "Moving away from this threshold rather than toward it. Nothing to cross."
    ),
}


@dataclass(frozen=True)
class Trend:
    """A fitted line, with everything needed to say how much to believe it."""

    slope_per_day: float
    intercept: float
    # Residual standard error: typical distance of a reading from the line.
    residual_sd: float
    points: int
    span_days: float
    # Where the fit is centred, needed for the interval at any future point.
    mean_x: float
    sum_squared_dx: float
    confidence: float
    origin: datetime.datetime

    @property
    def per_week(self) -> float:
        return self.slope_per_day * 7

    @property
    def rising(self) -> bool:
        return self.slope_per_day > 0

    def as_dict(self) -> dict:
        return {
            "per_week": round(self.per_week, 4),
            "readings": self.points,
            "span_days": round(self.span_days, 1),
            "typical_scatter": round(self.residual_sd, 4),
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class Projection:
    """Where the metric is expected to be, and how sure that is."""

    value: float
    lower: float
    upper: float
    days_ahead: float
    confidence: float
    trend: Trend

    @property
    def width(self) -> float:
        return self.upper - self.lower

    def as_dict(self) -> dict:
        return {
            "value": round(self.value, 4),
            "lower": round(self.lower, 4),
            "upper": round(self.upper, 4),
            "days_ahead": round(self.days_ahead, 1),
            "confidence": self.confidence,
        }


def _t_value(df: int, confidence: float) -> float:
    table = _T_TWO_SIDED[confidence]
    return table.get(df, _T_LARGE_SAMPLE[confidence])


def fit(
    points: list[tuple[datetime.datetime, float]],
    *,
    confidence: float = DEFAULT_CONFIDENCE,
) -> Trend | NoForecast:
    """Fit a line through a metric's history, or say why not.

    Regressed against elapsed days rather than reading number, because
    readings are not evenly spaced. Treating them as an index would let a
    fortnight's gap count the same as a day's and quietly tilt the line.
    """
    if confidence not in _T_TWO_SIDED:
        raise ValueError(f"confidence must be one of {sorted(_T_TWO_SIDED)}")
    if len(points) < MIN_POINTS:
        return NoForecast.too_few_readings

    ordered = sorted(points, key=lambda p: p[0])
    origin = ordered[0][0]
    xs = [(when - origin).total_seconds() / 86_400 for when, _ in ordered]
    ys = [value for _, value in ordered]

    span = xs[-1] - xs[0]
    if span <= 0:
        return NoForecast.no_time_span

    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sum_squared_dx = sum((x - mean_x) ** 2 for x in xs)
    if sum_squared_dx == 0:
        return NoForecast.no_time_span

    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / sum_squared_dx
    intercept = mean_y - slope * mean_x

    residuals = [y - (intercept + slope * x) for x, y in zip(xs, ys, strict=True)]
    df = n - 2
    residual_sd = math.sqrt(sum(r * r for r in residuals) / df)

    # Is the slope distinguishable from flat? A line through noise always has
    # some tilt, and reporting that tilt as a direction is how a forecast
    # invents a signal.
    if residual_sd > 0:
        slope_error = residual_sd / math.sqrt(sum_squared_dx)
        if abs(slope) < _t_value(df, confidence) * slope_error:
            return NoForecast.no_detectable_trend
    elif slope == 0:
        return NoForecast.no_detectable_trend

    return Trend(
        slope_per_day=slope,
        intercept=intercept,
        residual_sd=residual_sd,
        points=n,
        span_days=span,
        mean_x=mean_x,
        sum_squared_dx=sum_squared_dx,
        confidence=confidence,
        origin=origin,
    )


def project(trend: Trend, days_ahead: float) -> Projection | NoForecast:
    """Where the metric lands `days_ahead` from the last reading.

    The interval is a prediction interval: it covers a future *reading*, not
    the average of future readings, and is wider for it. That width is the
    honest part — a narrow-looking forecast on a dozen noisy points would be a
    stronger claim than the data can carry.
    """
    if days_ahead > trend.span_days * MAX_HORIZON_RATIO:
        return NoForecast.horizon_too_far

    x = trend.span_days + days_ahead
    value = trend.intercept + trend.slope_per_day * x

    # Standard error of a prediction: the scatter of readings about the line,
    # plus the uncertainty in where the line itself sits at this distance from
    # the data's centre. The second term is why forecasting further out is
    # less certain even when the fit is good.
    leverage = 1 + (1 / trend.points) + ((x - trend.mean_x) ** 2 / trend.sum_squared_dx)
    margin = _t_value(trend.points - 2, trend.confidence) * trend.residual_sd * math.sqrt(leverage)

    return Projection(
        value=value,
        lower=value - margin,
        upper=value + margin,
        days_ahead=days_ahead,
        confidence=trend.confidence,
        trend=trend,
    )


def explain(outcome: NoForecast) -> str:
    """The refusal, in a sentence a customer can read."""
    return REASONS[outcome]


# ── When does this cross the line? ───────────────────────────────────────────


@dataclass(frozen=True)
class Crossing:
    """When a metric is due to cross a threshold, as a range rather than a date.

    Three numbers, and the outer two are the honest ones. `earliest` and
    `latest` come from the edges of the prediction interval; `expected` is the
    line itself. A single date would be a claim the arithmetic cannot support,
    and "in six weeks" is exactly the sort of thing a person plans around.
    """

    threshold: float
    expected_days: float
    earliest_days: float
    latest_days: float | None
    trend: Trend

    @property
    def already_past(self) -> bool:
        return self.expected_days <= 0

    def as_dict(self) -> dict:
        return {
            "threshold": round(self.threshold, 4),
            "expected_days": round(self.expected_days, 1),
            "earliest_days": round(self.earliest_days, 1),
            "latest_days": None if self.latest_days is None else round(self.latest_days, 1),
            "per_week": round(self.trend.per_week, 4),
        }


def _days_until(trend: Trend, target: float, offset: float) -> float | None:
    """Days from the last reading until the line (shifted by `offset`) hits
    `target`, or None if it never does."""
    if trend.slope_per_day == 0:
        return None
    last_x = trend.span_days
    x = (target - offset - trend.intercept) / trend.slope_per_day
    return x - last_x


def crosses(
    trend: Trend,
    threshold: float,
    *,
    rising_is_bad: bool,
) -> Crossing | NoForecast:
    """When this metric is due to reach `threshold`, or why it will not.

    Answers `heading_away` when the trend runs from the threshold rather than
    toward it, which is the common and welcome case: a book that is improving
    does not "cross critical in 40 weeks" on the strength of a line pointing
    the other way, and it should read as the good news it is rather than as an
    inability to tell.

    The range comes from the prediction interval, so a metric can be due to
    cross in nine weeks and *possibly* in four. The early edge is the one worth
    acting on, and quoting only the middle would systematically understate how
    soon a business needs to move.
    """
    # "Improving" and "we cannot tell" are opposite pieces of news and were
    # briefly returning the same reason. A book getting better should read as
    # a book getting better.
    heading_toward = trend.rising if rising_is_bad else not trend.rising
    if not heading_toward:
        return NoForecast.heading_away

    expected = _days_until(trend, threshold, 0.0)
    if expected is None:
        return NoForecast.heading_away

    # "Heading there eventually" and "we cannot see that far" are different
    # answers, and only one of them is useful. A business on a slow drift
    # toward critical wants to hear that it is drifting, not a refusal that
    # reads as though nothing is happening.
    if expected > trend.span_days * MAX_HORIZON_RATIO:
        return NoForecast.not_within_horizon

    # The interval's edges, expressed as a parallel shift of the line. The
    # margin is taken at the expected crossing, which is where the question is
    # being asked.
    projected = project(trend, max(expected, 0.0))
    if isinstance(projected, NoForecast):
        return projected
    margin = projected.width / 2

    # Whichever edge reaches the threshold first is the earliest it could
    # happen; the other is the latest.
    toward = margin if rising_is_bad else -margin
    early = _days_until(trend, threshold, toward)
    late = _days_until(trend, threshold, -toward)

    if early is None:
        return NoForecast.heading_away

    return Crossing(
        threshold=threshold,
        expected_days=expected,
        earliest_days=max(0.0, early),
        latest_days=None if late is None else max(0.0, late),
        trend=trend,
    )
