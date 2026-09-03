"""The generic decision kernel, independent of any domain pack.

These cover the engine's own contract: how risk is scored, when acting is
worth its cost, and that a domain with no pack still gets sensible generic
vocabulary. Pack-driven behaviour lives in test_domain_packs.py.
"""

from aether.domains.pack import ActionSlot
from aether.policy.decision_engine import PolicyParams, RiskLevel, evaluate


def test_healthy_system_no_action():
    d = evaluate(drift_fraction=0.05, performance=0.92, params=PolicyParams())
    assert d.slot is ActionSlot.none
    assert d.action == "NO_ACTION"
    assert d.risk_level is RiskLevel.low
    assert d.expected_daily_loss == 0
    assert not d.requires_approval


def test_medium_risk_monitors():
    d = evaluate(drift_fraction=0.30, performance=0.80, params=PolicyParams())
    assert d.slot is ActionSlot.monitor
    assert d.risk_level is RiskLevel.medium


def test_high_risk_expensive_degradation_intervenes_with_approval():
    d = evaluate(drift_fraction=0.60, performance=0.50, params=PolicyParams())
    assert d.slot is ActionSlot.intervene
    assert d.risk_level is RiskLevel.high
    assert d.requires_approval
    assert d.expected_daily_loss > d.action_cost


def test_high_risk_cheap_impact_investigates_instead_of_acting():
    params = PolicyParams(impact_per_error=0.01, daily_decision_volume=10)
    d = evaluate(drift_fraction=0.9, performance=0.4, params=params)
    assert d.risk_level is RiskLevel.high
    assert d.slot is ActionSlot.investigate
    assert not d.requires_approval


def test_tenant_policy_overrides_change_the_decision():
    lenient = PolicyParams(perf_threshold=0.5, drift_threshold=0.8)
    assert evaluate(0.6, 0.6, lenient).slot is ActionSlot.none

    strict = PolicyParams(perf_threshold=0.95, drift_threshold=0.05)
    assert evaluate(0.6, 0.6, strict).risk_level is not RiskLevel.low


def test_params_from_dict_ignores_unknown_keys():
    p = PolicyParams.from_dict({"intervention_cost": 500, "not_a_field": 1})
    assert p.intervention_cost == 500
    assert p.perf_threshold == 0.85  # default preserved


def test_inputs_clamped():
    d = evaluate(drift_fraction=4.0, performance=1.0, params=PolicyParams())
    assert d.inputs["drift_fraction"] == 1.0


def test_unpacked_domain_gets_generic_vocabulary():
    """A domain with no pack still decides — it just speaks generically."""
    d = evaluate(0.6, 0.5, PolicyParams(), pack=None)
    assert d.action == "INTERVENE"
    assert d.action_description


def test_loss_basis_is_always_explained():
    d = evaluate(0.6, 0.5, PolicyParams())
    assert "daily decisions" in d.inputs["loss_basis"]
