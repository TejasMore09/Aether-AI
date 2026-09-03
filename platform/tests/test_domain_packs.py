"""Domain packs, the quality gate, and signal derivation.

None of this needs a database: packs are curated data, and the gate and
derivation are pure functions over them. That is deliberate — the layer that
decides whether a business number is trustworthy should be testable without
infrastructure.
"""

import pytest

from aether.domains.derive import derive_drift, derive_performance, derive_signals
from aether.domains.pack import ActionSlot, Direction, get_pack, list_packs
from aether.domains.quality import Severity, validate_metrics
from aether.policy.decision_engine import PolicyParams, RiskLevel, evaluate


@pytest.fixture(scope="module")
def receivables():
    pack = get_pack("receivables")
    assert pack is not None, "receivables pack should ship with the platform"
    return pack


# ── Pack loading ──────────────────────────────────────────────────────────────


def test_pack_registry_loads(receivables):
    assert receivables.key == "receivables"
    assert "receivables" in {p.key for p in list_packs()}
    assert receivables.required_metrics == ("dso_days", "overdue_ratio")


def test_pack_vocabulary_is_domain_specific(receivables):
    """The finance product must not inherit ML vocabulary from the prototype."""
    labels = {spec.label for spec in receivables.actions.values()}
    assert "ESCALATE_COLLECTIONS" in labels
    assert "RETRAIN" not in labels
    assert receivables.action(ActionSlot.intervene).requires_approval is True


def test_unknown_domain_has_no_pack():
    assert get_pack("no-such-domain") is None


def test_health_score_bands(receivables):
    dso = receivables.metric("dso_days")
    assert dso.health_score(30) == 1.0  # comfortably healthy
    assert dso.health_score(45) == 1.0  # at the healthy bound
    assert dso.health_score(90) == 0.0  # at the critical bound
    assert dso.health_score(300) == 0.0  # clamped, not negative
    assert 0.0 < dso.health_score(70) < 1.0

    effectiveness = receivables.metric("collection_effectiveness")
    assert effectiveness.direction is Direction.higher_better
    assert effectiveness.health_score(0.9) == 1.0
    assert effectiveness.health_score(0.5) == 0.0


def test_context_metrics_are_not_scored(receivables):
    assert receivables.metric("ar_total").scored is False
    assert receivables.metric("ar_total").health_score(50_000) is None


# ── Quality gate ──────────────────────────────────────────────────────────────


GOOD = {
    "dso_days": 38.0,
    "overdue_ratio": 0.12,
    "avg_days_past_due": 9.0,
    "collection_effectiveness": 0.86,
    "top5_concentration": 0.38,
    "disputed_ratio": 0.02,
    "ar_total": 240_000.0,
    "invoice_count": 180,
}


def test_clean_reading_accepted(receivables):
    report = validate_metrics(receivables, GOOD)
    assert report.accepted
    assert report.errors == []
    assert report.cleaned["dso_days"] == 38.0


def test_missing_required_metric_rejected(receivables):
    payload = {k: v for k, v in GOOD.items() if k != "dso_days"}
    report = validate_metrics(receivables, payload)
    assert not report.accepted
    assert any(i.code == "required_missing" and i.metric == "dso_days" for i in report.errors)


def test_impossible_value_rejected(receivables):
    """A unit mismatch upstream is the classic silent poisoner."""
    report = validate_metrics(receivables, {**GOOD, "overdue_ratio": 45.0})
    assert not report.accepted
    assert any(i.code == "above_maximum" for i in report.errors)


def test_non_numeric_rejected(receivables):
    report = validate_metrics(receivables, {**GOOD, "dso_days": "forty"})
    assert not report.accepted
    assert any(i.code == "not_numeric" for i in report.errors)


def test_unknown_metric_warns_but_does_not_reject(receivables):
    report = validate_metrics(receivables, {**GOOD, "days_sales_outstanding": 38})
    assert report.accepted
    assert any(i.code == "unknown_metric" for i in report.warnings)
    assert "days_sales_outstanding" not in report.cleaned


def test_contradiction_between_plausible_values_rejected(receivables):
    """Each value is individually valid; together they are impossible."""
    report = validate_metrics(receivables, {**GOOD, "overdue_ratio": 0.10, "disputed_ratio": 0.30})
    assert not report.accepted
    assert any(i.code == "contradiction" for i in report.errors)


def test_zero_invoices_with_outstanding_balance_rejected(receivables):
    report = validate_metrics(receivables, {**GOOD, "invoice_count": 0, "ar_total": 90_000})
    assert not report.accepted
    assert any(i.code == "contradiction" for i in report.errors)


def test_implausible_combination_only_warns(receivables):
    report = validate_metrics(receivables, {**GOOD, "dso_days": 10, "overdue_ratio": 0.6})
    assert report.accepted  # usable, but flagged
    assert any(i.severity is Severity.warning for i in report.issues)


# ── Derivation ────────────────────────────────────────────────────────────────


def test_healthy_book_scores_high(receivables):
    performance, detail = derive_performance(receivables, GOOD)
    assert performance > 0.9
    assert detail["dso_days"]["health"] == 1.0


def test_deteriorated_book_scores_low(receivables):
    bad = {**GOOD, "dso_days": 88.0, "overdue_ratio": 0.38, "avg_days_past_due": 55.0}
    performance, _ = derive_performance(receivables, bad)
    assert performance < 0.35


def test_missing_optional_metrics_are_not_penalised(receivables):
    minimal = {"dso_days": 38.0, "overdue_ratio": 0.12}
    performance, detail = derive_performance(receivables, minimal)
    assert performance > 0.9
    assert set(detail) == {"dso_days", "overdue_ratio"}


def test_no_baseline_means_no_drift(receivables):
    """An unknown is not a signal — cold start reports zero, not a guess."""
    drift, drifted, used = derive_drift(receivables, GOOD, history=[])
    assert (drift, drifted, used) == (0.0, [], False)


def test_drift_detected_against_own_baseline(receivables):
    history = [{"dso_days": 36.0, "overdue_ratio": 0.11} for _ in range(6)]
    current = {"dso_days": 72.0, "overdue_ratio": 0.12}
    drift, drifted, used = derive_drift(receivables, current, history)
    assert used is True
    assert "dso_days" in drifted
    assert "overdue_ratio" not in drifted
    assert drift == pytest.approx(0.5)


def test_improvement_is_not_drift(receivables):
    """Collections getting dramatically better must not read as a problem."""
    history = [{"dso_days": 70.0} for _ in range(6)]
    drift, drifted, _ = derive_drift(receivables, {"dso_days": 30.0}, history)
    assert drifted == []
    assert drift == 0.0


def test_derive_signals_marks_drifted_metrics(receivables):
    history = [dict(GOOD) for _ in range(6)]
    signals = derive_signals(receivables, {**GOOD, "dso_days": 80.0}, history)
    assert signals.baseline_used
    assert signals.per_metric["dso_days"].get("drifted") is True


# ── Pack-driven decisions ─────────────────────────────────────────────────────


def test_exposure_economics_uses_real_money(receivables):
    """Expected loss comes from the book at risk, not an invented error rate."""
    params = PolicyParams.for_pack(receivables)
    bad = {**GOOD, "dso_days": 95.0, "overdue_ratio": 0.45, "avg_days_past_due": 70.0}
    performance, _ = derive_performance(receivables, bad)

    decision = evaluate(0.5, performance, params, pack=receivables, values=bad)

    expected = bad["ar_total"] * bad["overdue_ratio"] * params.daily_rate
    assert decision.expected_daily_loss == pytest.approx(expected)
    assert "outstanding" in decision.inputs["loss_basis"]


def test_high_risk_large_book_escalates_with_approval(receivables):
    params = PolicyParams.for_pack(receivables)
    bad = {**GOOD, "ar_total": 900_000.0, "overdue_ratio": 0.45, "dso_days": 95.0}
    performance, _ = derive_performance(receivables, bad)

    decision = evaluate(0.6, performance, params, pack=receivables, values=bad)

    assert decision.risk_level is RiskLevel.high
    assert decision.slot is ActionSlot.intervene
    assert decision.action == "ESCALATE_COLLECTIONS"
    assert decision.requires_approval is True


def test_same_deterioration_on_a_tiny_book_does_not_escalate(receivables):
    """Identical ratios, trivial sums: chasing it costs more than it saves."""
    params = PolicyParams.for_pack(receivables)
    bad = {**GOOD, "ar_total": 3_000.0, "overdue_ratio": 0.45, "dso_days": 95.0}
    performance, _ = derive_performance(receivables, bad)

    decision = evaluate(0.6, performance, params, pack=receivables, values=bad)

    assert decision.risk_level is RiskLevel.high
    assert decision.slot is ActionSlot.investigate
    assert decision.action == "FLAG_FOR_REVIEW"
    assert decision.requires_approval is False


def test_healthy_book_takes_no_action(receivables):
    params = PolicyParams.for_pack(receivables)
    performance, _ = derive_performance(receivables, GOOD)
    decision = evaluate(0.0, performance, params, pack=receivables, values=GOOD)
    assert decision.slot is ActionSlot.none
    assert decision.action == "NO_ACTION"


def test_tenant_override_beats_pack_default(receivables):
    strict = PolicyParams.for_pack(receivables, {"perf_threshold": 0.99})
    assert strict.perf_threshold == 0.99
    assert strict.intervention_cost == receivables.economics.intervention_cost
