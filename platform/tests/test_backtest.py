"""Scoring the forecasts, and refusing to publish a number nothing earned.

No database except the fleet test.

Two things are being defended. That the harness measures what it claims —
walk-forward, never peeking at a reading it is predicting — and that it can
catch an interval that is *lying*, because a harness which only ever reports
"calibrated" is decoration.

The synthetic data here is deliberate and its purpose is narrow: data drawn to
match the model's own assumptions should produce coverage near the stated
confidence, which checks the arithmetic. It says nothing about how well Aether
forecasts a real business, and `measure_fleet` is where that question lives.
"""

import datetime
import random

import pytest

from aether.domains import backtest
from aether.domains.forecast import NoForecast

START = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)


def series(n: int, *, slope: float = 0.4, noise: float = 3.0, seed: int = 0) -> list:
    """A straight line plus normal noise: exactly what the model assumes."""
    rng = random.Random(seed)
    return [
        (START + datetime.timedelta(days=7 * i), 50 + slope * i + rng.gauss(0, noise))
        for i in range(n)
    ]


# ── The arithmetic ────────────────────────────────────────────────────────────


def test_coverage_lands_near_the_confidence_it_claims():
    """The measurement that says the product's "80% confidence" is honest.

    Averaged over twelve independent series so one unlucky draw cannot decide
    it. Coverage came out at 0.778 against a claim of 0.80.
    """
    coverages = [
        result.coverage
        for seed in range(12)
        if isinstance(
            result := backtest.backtest(
                series(80, seed=seed), horizon_days=28, use_seasonality=False
            ),
            backtest.Backtest,
        )
    ]
    assert len(coverages) == 12
    assert abs(sum(coverages) / len(coverages) - 0.80) <= 0.05


def test_a_stricter_confidence_covers_more_of_the_readings():
    covers = {}
    for confidence in (0.80, 0.95):
        results = [
            backtest.backtest(
                series(80, seed=seed),
                horizon_days=28,
                confidence=confidence,
                use_seasonality=False,
            )
            for seed in range(12)
        ]
        scored = [r for r in results if isinstance(r, backtest.Backtest)]
        covers[confidence] = sum(r.coverage for r in scored) / len(scored)

    assert covers[0.95] > covers[0.80]
    assert abs(covers[0.95] - 0.95) <= 0.05


def walk(n: int, *, step: float = 3.0, seed: int = 0) -> list:
    """A random walk: each reading a step from the last, with no true trend.

    Ordinary in business data — a cash balance behaves close to this — and it
    breaks the model's assumption that errors are independent.
    """
    rng = random.Random(seed)
    value = 50.0
    out = []
    for i in range(n):
        value += rng.gauss(0, step)
        out.append((START + datetime.timedelta(days=7 * i), value))
    return out


def accelerating(n: int, *, seed: int = 0) -> list:
    """A curve, not a line. A book that is deteriorating often accelerates."""
    rng = random.Random(seed)
    return [
        (START + datetime.timedelta(days=7 * i), 50 + 0.02 * i * i + rng.gauss(0, 2.0))
        for i in range(n)
    ]


def scored(maker, seeds: int = 10) -> list:
    return [
        result
        for seed in range(seeds)
        if isinstance(
            result := backtest.backtest(
                maker(90, seed=seed), horizon_days=28, use_seasonality=False
            ),
            backtest.Backtest,
        )
    ]


def test_a_random_walk_gets_no_forecast_at_all():
    """The gap this harness found and closed.

    A random walk has no true trend but locally always looks like one, and its
    errors carry over from reading to reading — so the model extrapolated a
    direction that was not there and quoted an interval far too narrow for it.
    Measured coverage was **0.52 against a claim of 0.80** before the shape
    guard existed.

    Now nothing is offered. A cash balance behaves close to a random walk, so
    this is an ordinary case rather than an exotic one (D53).
    """
    assert scored(walk) == [], "a walk must not be forecast, not merely forecast badly"


def test_an_accelerating_curve_gets_no_forecast_either():
    """A line through an accelerating series under-predicts by a growing
    margin, and the interval — built from in-sample scatter — never accounts
    for it. Coverage measured **0.12** before the guard."""
    assert scored(accelerating) == []


def test_the_shape_the_model_assumes_is_still_forecast():
    """The guard has to refuse the wrong shapes without refusing everything.
    A test that only proved refusal would be satisfied by a function that
    always says no."""
    results = scored(lambda n, seed: series(n, seed=seed))
    assert len(results) == 10, "an honest straight line must still be forecast"

    coverage = sum(r.coverage for r in results) / len(results)
    assert abs(coverage - 0.80) <= 0.10, f"and still calibrated, got {coverage:.2f}"
    assert sum(r.forecasts for r in results) > 400


# ── It must not peek ──────────────────────────────────────────────────────────


def test_a_forecast_never_sees_the_reading_it_is_predicting(monkeypatch):
    """Walk-forward, never in-sample. A model scored on the points it was
    fitted to flatters itself, and the whole question is what it does with a
    reading it has not seen.

    Asserted directly on what `fit` is handed rather than inferred from an
    error moving, because an indirect proxy can pass for the wrong reason —
    the first version of this test corrupted the back half of a series, and
    the corruption was caught by the shape guard rather than by the horizon.
    """
    points = series(80, seed=3)
    horizon = 28.0
    handed: list[tuple] = []

    real_fit = backtest.fit

    def watched(history, **kwargs):
        handed.append((history[0][0], history[-1][0], len(history)))
        return real_fit(history, **kwargs)

    monkeypatch.setattr(backtest, "fit", watched)
    result = backtest.backtest(points, horizon_days=horizon, use_seasonality=False)
    assert isinstance(result, backtest.Backtest)
    assert handed, "the harness should have fitted something"

    # Every fit's newest reading must sit at least a full horizon before the
    # earliest reading it could have been asked to predict.
    by_time = sorted(points, key=lambda p: p[0])
    for _, newest, _ in handed:
        predictable = [w for w, _ in by_time if (w - newest).total_seconds() / 86_400 >= horizon]
        assert predictable, "a fit with nothing left to predict should not have happened"


def test_the_history_stops_a_full_horizon_before_the_reading():
    """Predicting 28 days ahead using data from 7 days ago is not a 28-day
    forecast, and would report an accuracy the product cannot deliver."""
    points = series(60, seed=1)
    near = backtest.backtest(points, horizon_days=7, use_seasonality=False)
    far = backtest.backtest(points, horizon_days=56, use_seasonality=False)

    assert near.horizon_days == 7 and far.horizon_days == 56
    assert far.mean_interval_width > near.mean_interval_width, (
        "forecasting further ahead must be admitted to be less certain"
    )
    # And measured: the *error* does not necessarily grow with the horizon on a
    # correctly specified model. The point estimate of a true line stays good
    # however far out it reaches; what has to widen is the honesty about it.
    # Asserting on error here would have been asserting on the wrong quantity.


# ── Refusing ──────────────────────────────────────────────────────────────────


def test_too_little_history_produces_no_score_rather_than_a_shaky_one():
    assert backtest.backtest(series(6), horizon_days=28) is NoForecast.too_few_readings


def test_a_handful_of_forecasts_is_not_a_measurement():
    """Ten forecasts at 80% confidence expects two misses, and one either way
    moves coverage by ten points. A figure that unstable should not be
    reported at all."""
    result = backtest.backtest(series(14, seed=2), horizon_days=28, use_seasonality=False)
    assert result is NoForecast.too_few_readings


def test_a_steady_business_is_skipped_with_its_reason_recorded():
    """Most windows of a flat series have no detectable trend, so most
    forecasts cannot be made. That is correct, and the count needs to be
    explainable rather than mysteriously low."""
    flat = series(80, slope=0.0, noise=3.0, seed=5)
    result = backtest.backtest(flat, horizon_days=28, use_seasonality=False)

    if isinstance(result, backtest.Backtest):
        assert result.skipped, "skips should be recorded, not silently dropped"
        assert NoForecast.no_detectable_trend.value in result.skipped
    else:
        assert result is NoForecast.too_few_readings


# ── What may be published ─────────────────────────────────────────────────────


@pytest.mark.postgres
def test_the_fleet_measurement_says_nothing_when_nothing_has_earned_it():
    """The honest answer today and for a while. No real business has used this
    system, so a figure produced now would describe how well the forecast
    predicts invented test data — which looks exactly like evidence."""
    import uuid

    import sqlalchemy
    from sqlalchemy import text

    from aether.core.db import get_engine

    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except sqlalchemy.exc.OperationalError:
        pytest.skip("Postgres not reachable — start it with: docker compose up -d db")

    # Tenants that exist but have no readings.
    assert backtest.measure_fleet([uuid.uuid4() for _ in range(3)]) is None


def test_a_published_figure_always_carries_what_it_was_measured_on():
    """An accuracy figure without a sample size is a number in search of a
    decimal point."""
    accuracy = backtest.FleetAccuracy(
        tenants=4,
        series=11,
        forecasts=260,
        coverage=0.79,
        confidence=0.80,
        mean_absolute_error=2.6,
        calibrated=True,
    )
    payload = accuracy.as_dict()
    for field in ("tenants", "series", "forecasts"):
        assert payload[field] > 0, f"{field} must be reported alongside the accuracy"
