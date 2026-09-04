"""Where a metric is heading, and the many times it should say nothing.

No database. This is arithmetic, and arithmetic is checkable.

Most of these are about refusing, because that is where a forecast does harm.
A line through noise always has some tilt, and reporting that tilt as "your
collections are slowing" invents a signal a business may act on. The failures
worth catching are all of that shape: a confident number where there is no
evidence, a date where there is only a direction, and a projection reaching
further than the history behind it.
"""

import datetime
import math

import pytest

from aether.domains import forecast
from aether.domains.forecast import NoForecast

START = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)


def weekly(values: list[float]) -> list[tuple[datetime.datetime, float]]:
    return [(START + datetime.timedelta(days=7 * i), v) for i, v in enumerate(values)]


RISING = [42, 47, 44, 50, 46, 53, 49, 56, 52, 58, 55, 61]
STEEP = [44, 50, 47, 56, 52, 62, 58, 68, 64, 74, 70, 80]
IMPROVING = [61, 55, 58, 52, 56, 49, 53, 46, 50, 44, 47, 42]
STEADY = [45, 44, 46, 45, 44, 46, 45, 45, 46, 44, 45, 46]


# ── Fitting ───────────────────────────────────────────────────────────────────


def test_a_clear_rise_is_measured_in_the_units_a_person_thinks_in():
    trend = forecast.fit(weekly(RISING))
    assert isinstance(trend, forecast.Trend)
    assert trend.rising
    assert 1.0 < trend.per_week < 2.0, "about a day and a half a week"


def test_the_line_is_fitted_against_elapsed_time_not_reading_number():
    """Readings are not evenly spaced. Treating them as an index would make a
    climb over eight weeks look identical to the same climb over eight days.

    The same eight values, one series a week apart and one a day apart: the
    daily series is climbing exactly seven times faster, and a fit against the
    reading number would report both as the same trend.
    """
    values = [40.0 + i for i in range(8)]
    weekly_apart = forecast.fit(
        [(START + datetime.timedelta(days=7 * i), v) for i, v in enumerate(values)]
    )
    daily_apart = forecast.fit(
        [(START + datetime.timedelta(days=i), v) for i, v in enumerate(values)]
    )

    assert isinstance(weekly_apart, forecast.Trend) and isinstance(daily_apart, forecast.Trend)
    assert weekly_apart.slope_per_day == pytest.approx(1 / 7)
    assert daily_apart.slope_per_day == pytest.approx(1.0)


def test_a_perfect_line_is_still_a_trend():
    trend = forecast.fit(weekly([40.0 + i for i in range(10)]))
    assert isinstance(trend, forecast.Trend)
    assert trend.residual_sd == pytest.approx(0.0, abs=1e-9)


# ── Refusing ──────────────────────────────────────────────────────────────────


def test_thin_history_refuses_rather_than_fitting_two_points():
    """Two points define a line exactly and say nothing about whether it means
    anything."""
    assert forecast.fit(weekly([42, 44, 46])) is NoForecast.too_few_readings
    assert forecast.fit([]) is NoForecast.too_few_readings


def test_a_steady_metric_reports_no_trend_rather_than_a_faint_one():
    """The failure this exists to prevent. A line through noise always tilts,
    and calling that tilt a direction is inventing a signal."""
    assert forecast.fit(weekly(STEADY)) is NoForecast.no_detectable_trend


def test_readings_that_all_share_a_timestamp_have_nothing_to_project_along():
    same = [(START, v) for v in RISING]
    assert forecast.fit(same) is NoForecast.no_time_span


def test_noise_alone_does_not_produce_a_trend():
    """Alternating values with no drift. If this fitted, every steady business
    would be told it was moving."""
    assert forecast.fit(weekly([50, 54, 50, 54, 50, 54, 50, 54, 50, 54])) is (
        NoForecast.no_detectable_trend
    )


def test_a_projection_may_not_reach_further_than_the_history_behind_it():
    """The interval cannot enforce this. It measures uncertainty given that a
    line is the right shape, and has no way to say the shape itself is wrong
    by then — which is the assumption that fails first on business data."""
    trend = forecast.fit(weekly(RISING))
    assert isinstance(trend, forecast.Trend)

    assert isinstance(forecast.project(trend, trend.span_days), forecast.Projection)
    assert forecast.project(trend, trend.span_days + 1) is NoForecast.horizon_too_far


def test_every_refusal_can_be_read_by_a_person():
    for outcome in NoForecast:
        sentence = forecast.explain(outcome)
        assert sentence and sentence[0].isupper() and sentence.endswith(".")


# ── The interval ──────────────────────────────────────────────────────────────


def test_the_interval_covers_a_future_reading_not_the_average_of_them():
    """A prediction interval, not a confidence interval.

    The difference is the leading 1 in the leverage: the scatter of individual
    readings about the line, which a confidence interval for the mean leaves
    out. Measured on this series it is a factor of 1.76 — so answering the
    wrong question would present every forecast as nearly twice as precise as
    the data supports.
    """
    trend = forecast.fit(weekly(RISING))
    projected = forecast.project(trend, 14)
    assert isinstance(projected, forecast.Projection)

    x = trend.span_days + 14
    leverage = 1 / trend.points + (x - trend.mean_x) ** 2 / trend.sum_squared_dx
    mean_only = math.sqrt(leverage)
    with_scatter = math.sqrt(1 + leverage)

    assert with_scatter / mean_only == pytest.approx(1.76, abs=0.02)
    # And the interval actually reported is the wider one.
    margin = projected.width / 2
    assert margin == pytest.approx(
        forecast._t_value(trend.points - 2, trend.confidence) * trend.residual_sd * with_scatter
    )


def test_the_interval_widens_the_further_out_it_reaches():
    trend = forecast.fit(weekly(RISING))
    widths = [forecast.project(trend, d).width for d in (7, 28, 56, 77)]
    assert widths == sorted(widths)
    assert widths[-1] > widths[0]


def test_a_noisier_history_produces_a_wider_interval_for_the_same_slope():
    """The scatter is what the interval is made of. Two businesses drifting at
    the same rate are not equally predictable."""
    tidy = forecast.fit(weekly([40 + 1.5 * i for i in range(12)]))
    messy = forecast.fit(weekly([40 + 1.5 * i + (6 if i % 2 else -6) for i in range(12)]))

    assert forecast.project(messy, 14).width > forecast.project(tidy, 14).width * 3


def test_the_confidence_level_travels_with_the_answer():
    """So nobody has to guess which one was used."""
    trend = forecast.fit(weekly(RISING), confidence=0.95)
    projected = forecast.project(trend, 14)
    assert trend.confidence == 0.95
    assert projected.confidence == 0.95
    assert projected.as_dict()["confidence"] == 0.95


def test_a_stricter_confidence_is_a_wider_interval():
    eighty = forecast.project(forecast.fit(weekly(RISING), confidence=0.80), 14)
    ninety_five = forecast.project(forecast.fit(weekly(RISING), confidence=0.95), 14)
    assert ninety_five.width > eighty.width


def test_an_unsupported_confidence_is_refused_rather_than_approximated():
    with pytest.raises(ValueError, match="0.8"):
        forecast.fit(weekly(RISING), confidence=0.99)


# ── When does it cross? ───────────────────────────────────────────────────────


def test_a_steep_rise_says_when_it_will_breach_and_how_soon_it_could():
    """The answer the whole phase exists for."""
    trend = forecast.fit(weekly(STEEP))
    crossing = forecast.crosses(trend, 90.0, rising_is_bad=True)

    assert isinstance(crossing, forecast.Crossing)
    assert 0 < crossing.expected_days < trend.span_days
    assert crossing.earliest_days < crossing.expected_days < crossing.latest_days


def test_the_early_edge_is_the_one_worth_acting_on():
    """Quoting only the middle would systematically understate how soon a
    business needs to move."""
    trend = forecast.fit(weekly(STEEP))
    crossing = forecast.crosses(trend, 90.0, rising_is_bad=True)
    assert crossing.earliest_days < crossing.expected_days * 0.8


def test_a_metric_moving_away_from_the_threshold_says_so_as_good_news():
    """ "Improving" and "we cannot tell" are opposite pieces of news, and were
    briefly returning the same reason."""
    trend = forecast.fit(weekly(IMPROVING))
    outcome = forecast.crosses(trend, 90.0, rising_is_bad=True)

    assert outcome is NoForecast.heading_away
    assert "away from this threshold" in forecast.explain(outcome)


def test_a_slow_drift_says_it_is_drifting_rather_than_refusing_flatly():
    """ "Heading there eventually" and "we cannot see that far" are different
    answers, and a business on a slow drift wants to hear the first."""
    trend = forecast.fit(weekly(RISING))
    outcome = forecast.crosses(trend, 90.0, rising_is_bad=True)

    assert outcome is NoForecast.not_within_horizon
    assert "Heading that way" in forecast.explain(outcome)


def test_a_threshold_already_behind_us_is_reported_as_past_not_as_upcoming():
    trend = forecast.fit(weekly(STEEP))
    crossing = forecast.crosses(trend, 45.0, rising_is_bad=True)
    assert isinstance(crossing, forecast.Crossing)
    assert crossing.already_past


def test_direction_is_read_the_right_way_round_for_a_metric_where_higher_is_better():
    """Collection effectiveness falling toward a floor is the same shape of
    problem as DSO rising toward a ceiling, and must not be mistaken for the
    metric improving."""
    falling = forecast.fit(weekly([0.95, 0.92, 0.93, 0.89, 0.90, 0.86, 0.87, 0.83, 0.84, 0.80]))
    assert isinstance(falling, forecast.Trend)

    toward_floor = forecast.crosses(falling, 0.70, rising_is_bad=False)
    assert isinstance(toward_floor, forecast.Crossing)

    misread = forecast.crosses(falling, 0.70, rising_is_bad=True)
    assert misread is NoForecast.heading_away


# ── Reaching the decision engine ──────────────────────────────────────────────


def test_a_metric_heading_for_critical_is_found_within_the_window():
    from aether.domains.pack import get_pack

    pack = get_pack("receivables")
    series = {"dso_days": weekly(STEEP)}  # critical_max is 90

    found = forecast.approaching(pack, series, within_days=90)
    assert "dso_days" in found
    assert found["dso_days"].threshold == 90


def test_a_breach_beyond_the_window_is_not_reported():
    """Everything drifts somewhere eventually. Only a breach close enough to
    act on is worth interrupting somebody for."""
    from aether.domains.pack import get_pack

    found = forecast.approaching(
        get_pack("receivables"), {"dso_days": weekly(RISING)}, within_days=21
    )
    assert found == {}


def test_a_healthy_steady_business_has_no_trajectories():
    from aether.domains.pack import get_pack

    found = forecast.approaching(
        get_pack("receivables"), {"dso_days": weekly(STEADY)}, within_days=90
    )
    assert found == {}


def test_a_trajectory_brings_a_look_forward_without_moving_the_money():
    """The rule that keeps this honest. Today's exposure is today's money; a
    breach expected in three weeks has not cost anything yet, and folding a
    forecast into the loss figure would inflate a number the customer cannot
    reconcile with their own books."""
    from aether.domains.pack import get_pack
    from aether.policy.decision_engine import ActionSlot, PolicyParams, evaluate

    pack = get_pack("receivables")
    params = PolicyParams.for_pack(pack, None)
    healthy = {"dso_days": 40.0, "overdue_ratio": 0.08, "ar_total": 200_000.0}

    quiet = evaluate(0.1, 0.95, params, pack=pack, values=healthy)
    trajectories = forecast.approaching(pack, {"dso_days": weekly(STEEP)}, within_days=90)
    warned = evaluate(0.1, 0.95, params, pack=pack, values=healthy, trajectories=trajectories)

    assert quiet.slot is ActionSlot.none
    assert warned.slot is ActionSlot.investigate, "a look, brought forward"
    assert warned.expected_daily_loss == quiet.expected_daily_loss, (
        "the money at risk must not move because of a forecast"
    )
    assert "on the current trend" in warned.reason
    assert "no cost has been counted" in warned.reason


def test_a_trajectory_never_reaches_intervene_on_its_own():
    """That slot gates a human decision and spends money. Acting on an 80%
    interval would trade a real cost for a predicted one."""
    from aether.domains.pack import get_pack
    from aether.policy.decision_engine import ActionSlot, PolicyParams, evaluate

    pack = get_pack("receivables")
    params = PolicyParams.for_pack(pack, None)
    trajectories = forecast.approaching(pack, {"dso_days": weekly(STEEP)}, within_days=90)

    decision = evaluate(
        0.1, 0.95, params, pack=pack, values={"dso_days": 40.0}, trajectories=trajectories
    )
    assert decision.slot is not ActionSlot.intervene


def test_a_business_already_in_trouble_is_not_escalated_twice_for_it():
    """A metric that is both bad now and getting worse is one problem, not
    two. The level has already asked for attention; the trend must not raise
    the same alarm again."""
    from aether.domains.pack import get_pack
    from aether.policy.decision_engine import PolicyParams, evaluate

    pack = get_pack("receivables")
    params = PolicyParams.for_pack(pack, None)
    bad = {"dso_days": 85.0, "overdue_ratio": 0.5, "ar_total": 400_000.0}
    trajectories = forecast.approaching(pack, {"dso_days": weekly(STEEP)}, within_days=90)

    without = evaluate(0.9, 0.2, params, pack=pack, values=bad)
    with_trend = evaluate(0.9, 0.2, params, pack=pack, values=bad, trajectories=trajectories)

    assert with_trend.slot is without.slot
    assert with_trend.risk_level is without.risk_level
    assert with_trend.reason == without.reason, "the level's explanation already stands"


def test_the_trajectory_is_recorded_on_the_decision():
    """So an audit entry says why attention was asked for early, rather than
    leaving a reader to wonder what changed."""
    from aether.domains.pack import get_pack
    from aether.policy.decision_engine import PolicyParams, evaluate

    pack = get_pack("receivables")
    params = PolicyParams.for_pack(pack, None)
    trajectories = forecast.approaching(pack, {"dso_days": weekly(STEEP)}, within_days=90)

    decision = evaluate(
        0.1, 0.95, params, pack=pack, values={"dso_days": 40.0}, trajectories=trajectories
    )
    recorded = decision.as_dict()["inputs"]["trajectory"]["dso_days"]
    assert recorded["threshold"] == 90
    assert recorded["earliest_days"] < recorded["expected_days"]


# ── Seasonality ───────────────────────────────────────────────────────────────


def monthly_bump(readings: int, *, bump: float = 12.0, per_week: float = 0.0) -> list:
    """A series with a raised final quarter of each month."""
    out = []
    for i in range(readings):
        day = 7 * i
        phase = int((day % 30.44) // (30.44 / 4))
        value = 40.0 + per_week * i + (bump if phase == 3 else 0.0)
        out.append((START + datetime.timedelta(days=day), value))
    return out


def test_a_repeating_monthly_pattern_is_found():
    season = forecast.seasonality(monthly_bump(52))
    assert isinstance(season, forecast.Season)
    assert season.label == "monthly"
    assert season.amplitude == pytest.approx(12.0, abs=0.5)
    assert season.cycles >= 3


def test_a_business_with_no_pattern_is_not_given_one():
    """The failure this guards. Fitting a seasonal term to noise is inventing
    structure with more parameters, which is the same sin as reporting the
    tilt of a line through noise as a trend."""
    noisy = [(START + datetime.timedelta(days=7 * i), 50 + (1 if i % 2 else -1)) for i in range(52)]
    assert forecast.seasonality(noisy) is NoForecast.no_seasonal_effect


def test_two_cycles_is_a_coincidence_not_a_season():
    """Three is the least that distinguishes a pattern from two things
    happening to line up."""
    assert forecast.seasonality(monthly_bump(9)) is NoForecast.too_few_cycles


def test_a_steady_climb_is_not_mistaken_for_a_season():
    """Detection runs on the residuals of the trend line rather than the raw
    values. On raw values a climb would read as a season whose phases happen
    to be in ascending order."""
    climbing = [(START + datetime.timedelta(days=7 * i), 40.0 + i) for i in range(52)]
    assert forecast.seasonality(climbing) is NoForecast.no_seasonal_effect


def test_annual_seasonality_refuses_because_nobody_has_three_years():
    """Listed as a candidate because it is what people ask about, and it will
    keep refusing until a business has been watched for three years. Saying so
    beats omitting it and leaving somebody to wonder."""
    labels = [label for label, _, _ in forecast.CANDIDATE_SEASONS]
    assert "annual" in labels

    # A full year of weekly readings is one cycle, not three.
    yearly = monthly_bump(52)
    season = forecast.seasonality(yearly)
    assert isinstance(season, forecast.Season)
    assert season.label != "annual"


# ── What removing a season is actually for ────────────────────────────────────


def test_removing_a_season_mainly_buys_precision_not_accuracy():
    """Measured, because the intuition is wrong. A monthly sawtooth barely
    shifts the slope — it is being counted as *noise*, so what it wrecks is
    the interval. Here the 28-day interval goes from 14.5 wide to 0.1, and a
    projection that vague cannot say when anything crosses.
    """
    points = monthly_bump(40, per_week=0.5)
    season = forecast.seasonality(points)

    naive = forecast.fit(points)
    corrected = forecast.fit(points, season=season)
    assert isinstance(naive, forecast.Trend) and isinstance(corrected, forecast.Trend)

    assert abs(naive.per_week - 0.5) < 0.05, "the slope was never badly wrong"
    assert abs(corrected.per_week - 0.5) < 0.01, "and is now nearly exact"
    assert corrected.residual_sd < naive.residual_sd / 50, "the scatter is what collapses"

    assert forecast.project(corrected, 28).width < forecast.project(naive, 28).width / 50


def test_deseasonalising_leaves_the_readings_where_they_were_in_time():
    points = monthly_bump(52)
    season = forecast.seasonality(points)
    adjusted = forecast.deseasonalise(points, season)

    assert [when for when, _ in adjusted] == [when for when, _ in points]
    assert len(adjusted) == len(points)


def test_a_fit_with_no_season_is_unchanged():
    """Nobody's trend should move because seasonality was added to the module."""
    plain = forecast.fit(weekly(RISING))
    explicit = forecast.fit(weekly(RISING), season=None)
    assert plain.slope_per_day == explicit.slope_per_day


def test_the_engine_path_removes_a_season_before_deciding():
    """`approaching` is what the decision engine consumes, so the correction
    has to happen there rather than only being available."""
    from aether.domains.pack import get_pack

    pack = get_pack("receivables")
    # Climbing toward critical but not yet past it, under a monthly sawtooth.
    # Still short of 90 at the last reading, so this is a trajectory question
    # rather than a level one — `approaching` ignores anything already past.
    points = [
        (when, value - 40.0 + 20.0) for when, value in monthly_bump(40, bump=10.0, per_week=1.4)
    ]
    assert max(v for _, v in points) < 90, "the metric must not have breached already"

    found = forecast.approaching(pack, {"dso_days": points}, within_days=120)
    assert "dso_days" in found, "the trend under the season should still be found"
    assert found["dso_days"].earliest_days > 0
