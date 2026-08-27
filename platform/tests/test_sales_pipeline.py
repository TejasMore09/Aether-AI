"""The sales pipeline pack — domain three.

Cash was the domain that broke the engine; this is the one that had to prove
the breakage was worth it. It was added as configuration alone: no new
economics model, no new engine branch, no change to either finance pack.

It is also the hardest case for a published band. A referral-led consultancy
closing one deal in two and an outbound business closing one in twenty are
both perfectly healthy, and judged against each other either looks broken. So
several tests here are about calibration doing the work a fixed band cannot.
"""

import pytest

from aether.domains.derive import derive_signals
from aether.domains.pack import ActionSlot, EconomicsModel, get_pack, list_packs
from aether.policy.decision_engine import PolicyParams, evaluate

PACK = get_pack("sales_pipeline")

HEALTHY = {
    "pipeline_coverage": 4.1,
    "stalled_ratio": 0.12,
    "win_rate": 0.31,
    "slipped_ratio": 0.09,
    "avg_deal_age_days": 42.0,
    "pipeline_value": 480_000.0,
    "open_deal_count": 34,
    "new_pipeline_added": 120_000.0,
}
THINNING = {
    "pipeline_coverage": 2.6,
    "stalled_ratio": 0.24,
    "win_rate": 0.22,
    "slipped_ratio": 0.18,
    "avg_deal_age_days": 68.0,
    "pipeline_value": 310_000.0,
    "open_deal_count": 29,
    "new_pipeline_added": 64_000.0,
}
STALLING = {
    "pipeline_coverage": 1.9,
    "stalled_ratio": 0.44,
    "win_rate": 0.14,
    "slipped_ratio": 0.33,
    "avg_deal_age_days": 110.0,
    "pipeline_value": 240_000.0,
    "open_deal_count": 26,
    "new_pipeline_added": 31_000.0,
}
COLLAPSED = {
    "pipeline_coverage": 1.1,
    "stalled_ratio": 0.61,
    "win_rate": 0.06,
    "slipped_ratio": 0.48,
    "avg_deal_age_days": 165.0,
    "pipeline_value": 180_000.0,
    "open_deal_count": 22,
    "new_pipeline_added": 12_000.0,
}


def decide(values, history=None):
    signals = derive_signals(PACK, values, history)
    return evaluate(
        drift_fraction=signals.drift_fraction,
        performance=signals.performance,
        params=PolicyParams.for_pack(PACK),
        pack=PACK,
        values=values,
    )


# ── The abstraction held ──────────────────────────────────────────────────────


def test_this_domain_needed_nothing_new_from_the_engine():
    """The claim the pack format makes, tested rather than asserted.

    Cash forced two engine changes because its failure mode genuinely could
    not be expressed. If every new domain did that, the abstraction would be a
    fiction and expansion would not be cheap.
    """
    assert PACK.economics.model is EconomicsModel.exposure_scaled
    assert not any(m.existential for m in PACK.metrics), (
        "nothing here is terminal — a thin pipeline is a trade-off, not a cliff"
    )


def test_existential_metrics_stayed_rare():
    """The flag turns the economics engine off for a metric, so its value
    depends entirely on almost nothing carrying it."""
    carrying = {pack.key: [m.key for m in pack.metrics if m.existential] for pack in list_packs()}
    assert carrying == {
        "cash_runway": ["payroll_cover_months"],
        "receivables": [],
        "sales_pipeline": [],
    }


def test_all_three_packs_load_and_are_distinct():
    keys = sorted(p.key for p in list_packs())
    assert keys == ["cash_runway", "receivables", "sales_pipeline"]


def test_no_machine_learning_vocabulary_reaches_the_customer():
    surface = " ".join(
        [PACK.label, PACK.summary, *(a.label + " " + a.description for a in PACK.actions.values())]
    ).lower()
    for word in ("drift", "retrain", "model", "inference", "feature", "training"):
        assert word not in surface, f"{word!r} leaked into a sales product"


def test_context_metrics_are_carried_but_never_scored():
    scored = {m.key for m in PACK.scored_metrics}
    for key in ("pipeline_value", "open_deal_count", "new_pipeline_added"):
        assert PACK.metric(key) is not None
        assert key not in scored


# ── The decision ladder ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name,values,slot",
    [
        ("healthy", HEALTHY, ActionSlot.none),
        ("thinning", THINNING, ActionSlot.monitor),
        ("stalling", STALLING, ActionSlot.intervene),
        ("collapsed", COLLAPSED, ActionSlot.intervene),
    ],
)
def test_the_ladder_climbs_with_the_severity(name, values, slot):
    assert decide(values).slot is slot, name


def test_a_thinning_pipeline_is_noticed_before_it_is_a_problem():
    """Coverage 4.1 -> 2.6 with quiet pipeline doubling is exactly the trend a
    sales lead wants raised, and MONITOR costs nothing: it gates nobody and
    emails nobody."""
    decision = decide(THINNING)
    assert decision.slot is ActionSlot.monitor
    assert decision.risk_level.value == "MEDIUM"


def test_noticing_fires_earlier_than_acting():
    """The gap between the two is the whole design of this pack's thresholds.
    In a noisy domain, an agent that acts on every quiet fortnight is one
    people stop reading."""
    params = PolicyParams.for_pack(PACK)
    assert params.medium_risk_score < params.high_risk_score / 3


# ── Economics ─────────────────────────────────────────────────────────────────


def test_the_exposure_is_the_pipeline_that_has_gone_quiet():
    values = dict(STALLING)
    expected = values["pipeline_value"] * values["stalled_ratio"] * PACK.economics.daily_rate
    assert decide(values).expected_daily_loss_usd == pytest.approx(expected, rel=1e-6)


def test_the_explanation_uses_sales_words_not_finance_ones():
    reason = decide(STALLING).reason
    assert "in open pipeline" in reason
    assert "outstanding" not in reason
    assert "committed to go out" not in reason


def test_acting_is_justified_by_payback_not_by_severity_alone():
    """The engine must still show its working here, same as everywhere."""
    decision = decide(STALLING)
    assert "pays for itself" in decision.reason
    horizon = decision.expected_daily_loss_usd * PACK.economics.payback_days
    assert horizon > PACK.economics.intervention_cost_usd


# ── Calibration carries this domain more than any other ───────────────────────


def test_a_low_win_rate_business_is_not_permanently_condemned():
    """The case that motivated the whole calibration feature, at its extreme.

    Outbound businesses close a small fraction of what they touch. Against the
    published band that reads as near-critical forever.
    """
    outbound = dict(HEALTHY, win_rate=0.11)
    history = [
        {"win_rate": r} for r in (0.10, 0.12, 0.11, 0.13, 0.09, 0.12, 0.11, 0.10, 0.12, 0.11)
    ]

    cold = derive_signals(PACK, outbound).per_metric["win_rate"]["health"]
    settled = derive_signals(PACK, outbound, history).per_metric["win_rate"]["health"]

    assert cold < 0.4, "the published band should indeed dislike an 11% win rate"
    assert settled > cold, "their own history should exonerate them"


def test_but_a_collapse_from_their_own_normal_is_still_caught():
    """Calibration must not become an excuse. The same business halving its
    win rate is a real event."""
    history = [
        {"win_rate": r} for r in (0.10, 0.12, 0.11, 0.13, 0.09, 0.12, 0.11, 0.10, 0.12, 0.11)
    ]
    collapsed = dict(HEALTHY, win_rate=0.03)

    health = derive_signals(PACK, collapsed, history).per_metric["win_rate"]["health"]
    assert health < 0.5


def test_a_high_win_rate_business_gets_a_tighter_bar():
    """A referral firm closing half of what it quotes has a real problem at
    30% — comfortably inside the published healthy band."""
    history = [
        {"win_rate": r} for r in (0.52, 0.48, 0.55, 0.50, 0.47, 0.53, 0.51, 0.49, 0.54, 0.50)
    ]
    slipped = dict(HEALTHY, win_rate=0.30)

    unnoticed = derive_signals(PACK, slipped).per_metric["win_rate"]["health"]
    caught = derive_signals(PACK, slipped, history).per_metric["win_rate"]["health"]

    assert unnoticed == 1.0, "the published band cannot see this at all"
    assert caught < unnoticed


def test_calibration_reports_its_provenance_here_too():
    history = [
        {"win_rate": r} for r in (0.10, 0.12, 0.11, 0.13, 0.09, 0.12, 0.11, 0.10, 0.12, 0.11)
    ]
    detail = derive_signals(PACK, dict(HEALTHY, win_rate=0.11), history).per_metric
    assert detail["win_rate"]["band"]["source"] == "tenant"
    assert detail["pipeline_coverage"]["band"]["source"] == "pack"


# ── The other packs are untouched ─────────────────────────────────────────────


def test_the_finance_packs_are_unchanged_by_this_one():
    receivables = get_pack("receivables")
    cash = get_pack("cash_runway")
    assert receivables.economics.exposure_noun == "outstanding"
    assert cash.economics.model is EconomicsModel.shortfall_scaled
    assert PACK.economics.exposure_noun == "in open pipeline"
