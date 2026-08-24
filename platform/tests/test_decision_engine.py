from aether.policy.decision_engine import Action, PolicyParams, RiskLevel, evaluate


def test_healthy_system_no_action():
    d = evaluate(drift_fraction=0.05, performance=0.92, params=PolicyParams())
    assert d.action is Action.no_action
    assert d.risk_level is RiskLevel.low
    assert d.expected_daily_loss_usd == 0
    assert not d.requires_approval


def test_medium_risk_monitors():
    d = evaluate(drift_fraction=0.30, performance=0.80, params=PolicyParams())
    assert d.action is Action.monitor
    assert d.risk_level is RiskLevel.medium


def test_high_risk_expensive_degradation_retrains_with_approval():
    d = evaluate(drift_fraction=0.60, performance=0.50, params=PolicyParams())
    assert d.action is Action.retrain
    assert d.risk_level is RiskLevel.high
    assert d.requires_approval
    assert d.expected_daily_loss_usd > d.action_cost_usd


def test_high_risk_cheap_impact_flags_instead_of_retraining():
    params = PolicyParams(impact_per_error_usd=0.01, daily_decision_volume=10)
    d = evaluate(drift_fraction=0.9, performance=0.4, params=params)
    assert d.risk_level is RiskLevel.high
    assert d.action is Action.flag_anomaly
    assert not d.requires_approval


def test_tenant_policy_overrides_change_the_decision():
    lenient = PolicyParams(perf_threshold=0.5, drift_threshold=0.8)
    d = evaluate(drift_fraction=0.6, performance=0.6, params=lenient)
    assert d.action is Action.no_action

    strict = PolicyParams(perf_threshold=0.95, drift_threshold=0.05)
    d2 = evaluate(drift_fraction=0.6, performance=0.6, params=strict)
    assert d2.risk_level is not RiskLevel.low


def test_params_from_dict_ignores_unknown_keys():
    p = PolicyParams.from_dict({"retrain_cost_usd": 500, "not_a_field": 1})
    assert p.retrain_cost_usd == 500
    assert p.perf_threshold == 0.85  # default preserved


def test_inputs_clamped():
    d = evaluate(drift_fraction=4.0, performance=1.0, params=PolicyParams())
    assert d.inputs["drift_fraction"] == 1.0
