"""The cash & runway pack, and the two engine gaps it exposed.

Adding the second domain was partly a test of the claim the pack abstraction
makes: that a new business function is configuration, never code. It very
nearly held. Two things did have to change, and both were genuine defects
rather than cash being a special case:

  - exposure_scaled requires the at-risk fraction to be a *reported* metric.
    No owner reports "the share of my bills I cannot pay"; they report cash
    and they report what is due. Hence shortfall_scaled, which derives it.

  - The payback test weighed "payroll is covered for 0.8 months" against the
    cost of acting and declined. That is a category error: the downside of
    missing payroll is not a daily carrying charge, so no daily rate can
    represent it. Hence existential metrics, which escalate on their own.

The receivables pack is unchanged by either, which is the property that
matters — a second domain should extend the engine, not bend it.
"""

import pytest

from aether.domains.derive import derive_signals
from aether.domains.pack import ActionSlot, EconomicsModel, get_pack
from aether.policy.decision_engine import PolicyParams, evaluate

PACK = get_pack("cash_runway")

COMFORTABLE = {
    "runway_months": 14.0,
    "payroll_cover_months": 7.0,
    "obligation_coverage": 2.4,
    "burn_volatility": 0.12,
    "cash_balance": 240_000.0,
    "committed_outflows_30d": 98_000.0,
    "net_burn_monthly": 17_000.0,
}
TIGHTENING = {
    "runway_months": 5.2,
    "payroll_cover_months": 2.6,
    "obligation_coverage": 1.35,
    "burn_volatility": 0.28,
    "cash_balance": 92_000.0,
    "committed_outflows_30d": 68_000.0,
    "net_burn_monthly": 18_000.0,
}
SERIOUS = {
    "runway_months": 3.1,
    "payroll_cover_months": 1.4,
    "obligation_coverage": 0.82,
    "burn_volatility": 0.40,
    "cash_balance": 61_000.0,
    "committed_outflows_30d": 74_000.0,
    "net_burn_monthly": 19_000.0,
}
PAYROLL_AT_RISK = {
    "runway_months": 2.6,
    "payroll_cover_months": 0.8,
    "obligation_coverage": 0.71,
    "burn_volatility": 0.45,
    "cash_balance": 52_000.0,
    "committed_outflows_30d": 73_000.0,
    "net_burn_monthly": 20_000.0,
}


def decide(values: dict[str, float], history: list[dict] | None = None):
    signals = derive_signals(PACK, values, history)
    return evaluate(
        drift_fraction=signals.drift_fraction,
        performance=signals.performance,
        params=PolicyParams.for_pack(PACK),
        pack=PACK,
        values=values,
    )


# ── The pack loads and speaks its own language ────────────────────────────────


def test_the_pack_loads_and_is_registered():
    assert PACK is not None
    assert PACK.key == "cash_runway"
    assert {m.key for m in PACK.scored_metrics} == {
        "runway_months",
        "payroll_cover_months",
        "obligation_coverage",
        "burn_volatility",
    }


def test_context_metrics_are_carried_but_never_scored():
    """Burn is a decision, not a fault. A business investing on purpose burns
    more and must not read as unhealthy for it."""
    scored = {m.key for m in PACK.scored_metrics}
    for key in ("net_burn_monthly", "cash_balance", "committed_outflows_30d"):
        assert PACK.metric(key) is not None
        assert key not in scored


def test_no_machine_learning_vocabulary_reaches_the_customer():
    """The reason a generic ActionSlot exists at all."""
    surface = " ".join(
        [PACK.label, PACK.summary, *(a.label + " " + a.description for a in PACK.actions.values())]
    ).lower()
    for word in ("drift", "retrain", "model", "inference", "feature", "training"):
        assert word not in surface, f"{word!r} leaked into a finance product"


# ── The decision ladder ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name,values,slot",
    [
        ("comfortable", COMFORTABLE, ActionSlot.none),
        ("tightening", TIGHTENING, ActionSlot.monitor),
        ("serious", SERIOUS, ActionSlot.investigate),
        ("payroll at risk", PAYROLL_AT_RISK, ActionSlot.intervene),
    ],
)
def test_the_ladder_climbs_with_the_severity(name, values, slot):
    assert decide(values).slot is slot, name


def test_a_tightening_position_is_not_reported_as_nothing_to_see():
    """Five months of runway with payroll covered for under three is exactly
    what an owner wants told to them early, and the receivables thresholds
    would have called it fine."""
    decision = decide(TIGHTENING)
    assert decision.slot is ActionSlot.monitor
    assert decision.risk_level.value == "MEDIUM"


# ── Existential metrics bypass the payback test ───────────────────────────────


def test_payroll_is_marked_existential_and_nothing_else_is():
    """The flag turns the economics engine off for a metric, so it earns its
    place only where the arithmetic genuinely cannot apply."""
    existential = [m.key for m in PACK.metrics if m.existential]
    assert existential == ["payroll_cover_months"]


def test_uncovered_payroll_escalates_even_though_acting_does_not_pay_back():
    """The defect this flag fixes.

    $42 a day against a $1,200 cost of acting fails the payback test by a wide
    margin, and on that basis the engine previously recommended a review. A
    business with three weeks of payroll in the bank does not need a review.
    """
    decision = decide(PAYROLL_AT_RISK)
    horizon = decision.expected_daily_loss_usd * PACK.economics.payback_days

    assert horizon < PACK.economics.intervention_cost_usd, "the payback test should fail here"
    assert decision.slot is ActionSlot.intervene, "and must be bypassed anyway"
    assert "not a cost-benefit decision" in decision.reason
    assert "Payroll covered" in decision.reason


def test_the_bypass_does_not_fire_while_payroll_is_still_covered():
    """Serious is serious, but 1.4 months of payroll is above the floor and
    still a judgement call the economics may legitimately decline."""
    decision = decide(SERIOUS)
    assert decision.slot is ActionSlot.investigate
    assert "not a cost-benefit decision" not in decision.reason


def test_receivables_is_untouched_by_the_existential_mechanism():
    """A second domain should extend the engine, not bend it."""
    receivables = get_pack("receivables")
    assert not any(m.existential for m in receivables.metrics)


# ── Shortfall economics ───────────────────────────────────────────────────────


def test_the_shortfall_is_derived_not_reported():
    """Nobody records the fraction of their bills they cannot pay."""
    assert PACK.economics.model is EconomicsModel.shortfall_scaled
    reported = {m.key for m in PACK.metrics}
    assert PACK.economics.exposure_metric in reported
    assert PACK.economics.cover_metric in reported
    assert PACK.economics.at_risk_metric is None


def test_full_cover_carries_no_daily_loss():
    assert decide(COMFORTABLE).expected_daily_loss_usd == 0.0


def test_the_loss_tracks_the_gap_between_obligations_and_cash():
    values = dict(SERIOUS)
    exposure = values["committed_outflows_30d"]
    cover = values["cash_balance"]
    expected = (exposure - cover) * PACK.economics.daily_rate

    assert decide(values).expected_daily_loss_usd == pytest.approx(expected, rel=1e-6)


def test_the_explanation_uses_the_domains_own_words_not_receivables():
    """The engine described every exposure as money 'outstanding' — the one
    abstraction that exists to keep domains apart, leaking receivables
    vocabulary into a cash decision."""
    reason = decide(SERIOUS).reason
    assert "committed to go out" in reason
    assert "outstanding" not in reason


def test_a_period_with_no_obligations_is_not_a_crisis():
    """Dividing by a zero exposure must not invent a loss."""
    values = dict(COMFORTABLE, committed_outflows_30d=0.0, cash_balance=0.0)
    decision = decide(values)
    assert decision.expected_daily_loss_usd == 0.0
    assert "no obligations reported" in decision.reason or decision.slot is ActionSlot.none


# ── Calibration applies here too ──────────────────────────────────────────────


def test_a_business_that_runs_lean_on_purpose_is_not_permanently_alarmed():
    """Same argument as receivables: some businesses genuinely operate at four
    months of runway and are not dying."""
    lean = dict(COMFORTABLE, runway_months=4.2, payroll_cover_months=2.4)
    history = [
        {"runway_months": r, "payroll_cover_months": p}
        for r, p in [
            (4.1, 2.3),
            (4.4, 2.5),
            (4.0, 2.2),
            (4.3, 2.4),
            (4.2, 2.3),
            (4.5, 2.6),
            (4.1, 2.4),
            (4.3, 2.5),
            (4.2, 2.3),
            (4.4, 2.5),
        ]
    ]
    cold = derive_signals(PACK, lean).performance
    settled = derive_signals(PACK, lean, history).performance

    assert settled > cold, "their own history should soften the judgement"
    assert (
        derive_signals(PACK, lean, history).per_metric["runway_months"]["band"]["source"]
        == "tenant"
    )


def test_calibration_still_cannot_normalise_uncovered_payroll():
    """And the existential floor is immune to it, because critical never moves."""
    history = [{"payroll_cover_months": 0.7} for _ in range(12)]
    decision = decide(PAYROLL_AT_RISK, history)
    assert decision.slot is ActionSlot.intervene
