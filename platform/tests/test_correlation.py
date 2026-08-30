"""Co-movement detection, and mostly its refusals.

No database — series are built by hand.

The dangerous failure here is not missing a pattern. It is confidently
reporting one that is not there, because with a couple of hundred cross-domain
metric pairs and a dozen readings per tenant, that is what a naive
implementation does on every run for every customer. Most of what follows
pins the refusals.
"""

import datetime
import random

from aether.business.correlation import (
    MIN_PAIRS,
    STRONG_RHO,
    CoMovement,
    Series,
    align,
    candidates,
    changes,
    co_movement,
    evidence,
    spearman,
)
from aether.business.state import utcnow


def series(domain: str, metric: str, values: list[float], *, every_days: float = 7.0) -> Series:
    start = utcnow() - datetime.timedelta(days=every_days * len(values))
    points = tuple(
        (start + datetime.timedelta(days=every_days * i), v) for i, v in enumerate(values)
    )
    return Series(domain=domain, metric=metric, points=points)


RISING = [40.0, 42.0, 45.0, 47.0, 51.0, 54.0, 58.0, 61.0, 65.0, 69.0, 72.0, 77.0]
FALLING = [12.0, 11.6, 11.0, 10.7, 10.1, 9.6, 9.0, 8.6, 8.0, 7.5, 7.1, 6.5]


# ── The arithmetic ────────────────────────────────────────────────────────────


def test_spearman_finds_a_perfect_monotonic_relationship():
    assert spearman([1, 2, 3, 4, 5], [2, 4, 6, 8, 10]) == 1.0
    assert spearman([1, 2, 3, 4, 5], [10, 8, 6, 4, 2]) == -1.0


def test_spearman_is_about_order_not_shape():
    """Rank correlation, so a curved but consistently rising relationship is
    still a perfect one. Pearson would report less."""
    assert spearman([1, 2, 3, 4, 5], [1, 4, 9, 16, 25]) == 1.0


def test_spearman_is_undefined_rather_than_zero_on_flat_data():
    """No correlation *exists* between a series and a constant. Reporting 0.0
    would let flat data masquerade as evidence of independence."""
    assert spearman([1, 2, 3, 4], [5, 5, 5, 5]) is None
    assert spearman([1, 1, 1, 1], [1, 2, 3, 4]) is None


def test_spearman_refuses_series_too_short_to_mean_anything():
    assert spearman([1, 2], [3, 4]) is None
    assert spearman([1, 2, 3], [1, 2]) is None


def test_ties_are_ranked_together():
    """Common in business data — a metric that sat unchanged for three periods
    must not be given an arbitrary order."""
    assert spearman([1, 2, 2, 3], [1, 2, 2, 3]) == 1.0


def test_changes_are_one_shorter_than_the_input():
    assert changes([1.0, 3.0, 6.0]) == [2.0, 3.0]
    assert changes([5.0]) == []


# ── Alignment ─────────────────────────────────────────────────────────────────


def test_readings_from_different_schedules_are_paired_by_nearest_time():
    a = series("receivables", "dso_days", RISING, every_days=7)
    b = series("cash_runway", "runway_months", FALLING, every_days=7)
    xs, ys = align(a, b)
    assert len(xs) == len(ys) > 0


def test_one_reading_is_never_reused_for_several_pairs():
    """Otherwise a single cash reading pairs with six receivables readings and
    manufactures a correlation out of one observation repeated."""
    weekly = series("receivables", "dso_days", RISING, every_days=7)
    one_only = Series(
        domain="cash_runway",
        metric="runway_months",
        points=((utcnow() - datetime.timedelta(days=40), 6.0),),
    )
    xs, ys = align(weekly, one_only)
    assert len(xs) <= 1


def test_readings_too_far_apart_are_not_paired():
    recent = series("receivables", "dso_days", RISING, every_days=1)
    ancient = Series(
        domain="cash_runway",
        metric="runway_months",
        points=((utcnow() - datetime.timedelta(days=900), 6.0),),
    )
    xs, _ = align(recent, ancient)
    assert xs == []


# ── What it refuses to report ─────────────────────────────────────────────────


def test_a_shared_trend_alone_is_not_co_movement():
    """The single most important refusal here.

    Two metrics that both drift steadily will correlate almost perfectly on
    levels whether or not they are related. Differencing asks whether they
    move *together*, which is the real question — and independent noise on top
    of two trends should find nothing.
    """
    # Several seeds, because a single draw would prove only that one sample
    # behaved. The point is that this holds generally.
    for seed in (7, 11, 23, 41, 97):
        rng = random.Random(seed)
        drift_a = [40.0 + i * 2 + rng.uniform(-1.5, 1.5) for i in range(14)]
        drift_b = [12.0 - i * 0.4 + rng.uniform(-0.75, 0.75) for i in range(14)]

        a = series("receivables", "dso_days", drift_a)
        b = series("cash_runway", "runway_months", drift_b)

        on_levels = spearman([v for _, v in a.points], [v for _, v in b.points])
        assert on_levels is not None and abs(on_levels) > 0.9, (
            f"seed {seed}: levels do correlate strongly — which is exactly the trap"
        )
        assert co_movement(a, b) is None, (
            f"seed {seed}: differencing should refuse two independent trends"
        )


def test_thin_history_produces_nothing():
    """A correlation over five points is a coincidence with a decimal place."""
    short = [1.0, 2.0, 3.0, 4.0, 5.0]
    a = series("receivables", "dso_days", short)
    b = series("cash_runway", "runway_months", [5.0, 4.0, 3.0, 2.0, 1.0])
    assert co_movement(a, b) is None


def test_the_minimum_is_enforced_after_differencing():
    """Differencing consumes a point, so exactly MIN_PAIRS readings is one
    short of enough."""
    step = [float(i) for i in range(MIN_PAIRS)]
    a = series("receivables", "dso_days", step)
    b = series("cash_runway", "runway_months", step)
    assert co_movement(a, b) is None


def test_a_weak_relationship_is_not_reported():
    rng = random.Random(11)
    a = series("receivables", "dso_days", [rng.uniform(30, 70) for _ in range(14)])
    b = series("cash_runway", "runway_months", [rng.uniform(4, 14) for _ in range(14)])
    result = co_movement(a, b)
    assert result is None or abs(result.rho) >= STRONG_RHO


def test_two_metrics_in_the_same_domain_are_not_cross_domain():
    """Within-domain relationships belong to the pack, not here."""
    a = series("receivables", "dso_days", RISING)
    b = series("receivables", "overdue_ratio", FALLING)
    assert co_movement(a, b) is None


# ── What it does report ───────────────────────────────────────────────────────


def test_genuine_co_movement_is_found():
    """Changes that track each other, rather than two independent trends."""
    steps = [3.0, -1.0, 4.0, -2.0, 5.0, -3.0, 2.0, -1.0, 6.0, -4.0, 3.0, -2.0]
    dso, runway = [50.0], [9.0]
    for s in steps:
        dso.append(dso[-1] + s)
        runway.append(runway[-1] - s * 0.1)

    a = series("receivables", "dso_days", dso)
    b = series("cash_runway", "runway_months", runway)

    found = co_movement(a, b)
    assert found is not None
    assert found.rho <= -STRONG_RHO, "DSO up as runway down is a negative rank correlation"
    assert found.pairs >= MIN_PAIRS
    assert found.corroborates is None, "discovery on its own predicts nothing"


# ── Evidence versus dredging ──────────────────────────────────────────────────


def _paired_series() -> dict[tuple[str, str], Series]:
    steps = [3.0, -1.0, 4.0, -2.0, 5.0, -3.0, 2.0, -1.0, 6.0, -4.0, 3.0, -2.0]
    dso, runway = [50.0], [9.0]
    for s in steps:
        dso.append(dso[-1] + s)
        runway.append(runway[-1] - s * 0.1)

    return {
        ("receivables", "dso_days"): series("receivables", "dso_days", dso),
        ("cash_runway", "runway_months"): series("cash_runway", "runway_months", runway),
    }


def test_a_declared_relation_can_be_corroborated_by_history():
    """The honest half: the hypothesis was written down before the data was
    looked at, so finding it is evidence rather than a search result."""
    found = evidence(_paired_series())

    assert found, "the declared receivables/cash link should be visible here"
    supported = found[0]
    assert supported.corroborates == "collections_slowing_drains_cash"
    assert supported.predicted is True


def test_an_undeclared_pattern_is_a_candidate_not_a_finding():
    """Discovery is the output of testing every pair against a dozen readings,
    which is precisely the procedure that produces convincing nonsense."""
    data = _paired_series()
    data[("sales_pipeline", "win_rate")] = series(
        "sales_pipeline",
        "win_rate",
        [
            v / 200.0
            for v in [50.0, 53.0, 52.0, 56.0, 54.0, 59.0, 56.0, 58.0, 57.0, 63.0, 59.0, 62.0, 60.0]
        ],
    )

    for found in candidates(data):
        assert found.corroborates is None
        assert found.predicted is False


def test_a_corroborated_pair_is_not_repeated_as_a_candidate():
    data = _paired_series()
    supported = {
        frozenset({(c.domain_a, c.metric_a), (c.domain_b, c.metric_b)}) for c in evidence(data)
    }
    for found in candidates(data):
        assert (
            frozenset({(found.domain_a, found.metric_a), (found.domain_b, found.metric_b)})
            not in supported
        )


def test_no_history_yields_no_claims():
    assert evidence({}) == []
    assert candidates({}) == []


def test_serialisation_states_whether_it_was_predicted():
    payload = CoMovement(
        "receivables", "dso_days", "cash_runway", "runway_months", -0.82, 11
    ).as_dict()
    assert payload["a"] == "receivables.dso_days"
    assert payload["rho"] == -0.82
    assert payload["predicted"] is False
    assert payload["corroborates"] is None
