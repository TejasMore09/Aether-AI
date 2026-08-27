"""Cost-aware decision kernel.

Two things stay true regardless of which business function is being watched:
risk comes from how unhealthy things are plus how fast they moved, and acting
is only worthwhile when the exposure outweighs the cost of acting.

Everything domain-specific — what the metrics mean, what an action is called,
how money at risk is computed — comes from the domain pack. The engine reasons
in generic action slots so a finance product never inherits vocabulary from an
ML tool, and so a new domain is a pack rather than a change here.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from aether.domains.pack import (
    _GENERIC_ACTIONS,
    ActionSlot,
    ActionSpec,
    Direction,
    DomainPack,
    EconomicsModel,
)


@dataclass(frozen=True)
class PolicyParams:
    """Per-tenant, per-domain policy. Stored in PolicyConfig.params (JSONB).

    Defaults suit a domain with no pack; a pack supplies its own starting
    values, and a tenant may override any of them.
    """

    intervention_cost_usd: float = 250.0
    drift_threshold: float = 0.15
    perf_threshold: float = 0.85
    drift_weight: float = 0.4
    perf_weight: float = 0.6
    high_risk_score: float = 0.4
    medium_risk_score: float = 0.15
    # degradation_scaled economics
    impact_per_error_usd: float = 1000.0
    daily_decision_volume: int = 1000
    error_rate_translation: float = 0.1
    # exposure_scaled economics
    daily_rate: float = 0.0004
    # Acting costs a one-off sum while the loss accrues daily, so the two are
    # only comparable across a horizon. Act when the intervention pays for
    # itself inside this many days.
    payback_days: int = 7

    @classmethod
    def from_dict(cls, raw: dict | None) -> "PolicyParams":
        if not raw:
            return cls()
        known = {f: raw[f] for f in cls.__dataclass_fields__ if f in raw}
        return cls(**known)

    @classmethod
    def for_pack(cls, pack: DomainPack | None, overrides: dict | None = None) -> "PolicyParams":
        """Pack defaults first, then the tenant's overrides on top."""
        merged: dict = {}
        if pack is not None:
            merged.update(pack.policy_defaults)
            merged["intervention_cost_usd"] = pack.economics.intervention_cost_usd
            merged["daily_rate"] = pack.economics.daily_rate
            merged["payback_days"] = pack.economics.payback_days
            merged["impact_per_error_usd"] = pack.economics.impact_per_error_usd
            merged["daily_decision_volume"] = pack.economics.daily_decision_volume
            merged["error_rate_translation"] = pack.economics.error_rate_translation
        if overrides:
            merged.update(overrides)
        return cls.from_dict(merged)


class RiskLevel(StrEnum):
    low = "LOW"
    medium = "MEDIUM"
    high = "HIGH"


@dataclass(frozen=True)
class Decision:
    slot: ActionSlot
    action: str  # the pack's label for this slot
    action_description: str
    risk_level: RiskLevel
    risk_score: float
    expected_daily_loss_usd: float
    action_cost_usd: float
    reason: str
    requires_approval: bool = False
    inputs: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "slot": self.slot.value,
            "action": self.action,
            "action_description": self.action_description,
            "risk_level": self.risk_level.value,
            "risk_score": round(self.risk_score, 4),
            "expected_daily_loss_usd": round(self.expected_daily_loss_usd, 2),
            "action_cost_usd": self.action_cost_usd,
            "reason": self.reason,
            "requires_approval": self.requires_approval,
            "inputs": self.inputs,
        }


def _expected_daily_loss(
    pack: DomainPack | None,
    params: PolicyParams,
    perf_degradation: float,
    values: dict[str, float] | None,
) -> tuple[float, str]:
    """Money at risk per day, and a plain-language basis for it.

    Two models, because 'what does this cost' has genuinely different shapes.
    Exposure-scaled asks what sum is at risk and what carrying it costs;
    degradation-scaled asks how many decisions go wrong and what each costs.
    """
    econ = pack.economics if pack else None

    if econ and econ.model is EconomicsModel.exposure_scaled and values:
        exposure = values.get(econ.exposure_metric or "", 0.0) or 0.0
        at_risk = values.get(econ.at_risk_metric or "", 0.0) or 0.0
        loss = exposure * at_risk * params.daily_rate
        basis = (
            f"{at_risk:.0%} of {exposure:,.0f} {econ.exposure_noun}, carried at "
            f"{params.daily_rate * 365:.0%} a year"
        )
        return loss, basis

    if econ and econ.model is EconomicsModel.shortfall_scaled and values:
        # Obligations that must be met, against what is available to meet
        # them. Derived rather than reported: a business records its cash and
        # records what is due, never "the fraction of my bills I cannot pay".
        exposure = values.get(econ.exposure_metric or "", 0.0) or 0.0
        cover = values.get(econ.cover_metric or "", 0.0) or 0.0
        if exposure <= 0:
            return 0.0, "no obligations reported for the period"
        uncovered = max(0.0, 1.0 - (cover / exposure))
        loss = exposure * uncovered * params.daily_rate
        if uncovered == 0:
            basis = f"{cover:,.0f} available against {exposure:,.0f} {econ.exposure_noun}"
        else:
            basis = (
                f"{exposure * uncovered:,.0f} of {exposure:,.0f} {econ.exposure_noun} "
                f"not covered by the {cover:,.0f} available"
            )
        return loss, basis

    error_rate_increase = perf_degradation * params.error_rate_translation
    loss = params.daily_decision_volume * error_rate_increase * params.impact_per_error_usd
    basis = (
        f"{error_rate_increase:.1%} of {params.daily_decision_volume:,} daily decisions "
        f"at {params.impact_per_error_usd:,.0f} each"
    )
    return loss, basis


def _existential_breaches(
    pack: DomainPack | None, values: dict[str, float] | None
) -> list[tuple[str, float, float]]:
    """Metrics whose breach is not a cost-benefit question.

    Returns (label, value, critical bound) for each. See MetricSpec.existential
    for why these bypass the payback test rather than being weighed by it.
    """
    if not pack or not values:
        return []
    breaches = []
    for spec in pack.metrics:
        if not spec.existential:
            continue
        value = values.get(spec.key)
        if value is None or not spec.breached_critically(value):
            continue
        bound = spec.critical_max if spec.direction is Direction.lower_better else spec.critical_min
        if bound is None:  # breached_critically already implies otherwise
            continue
        breaches.append((spec.label, value, bound))
    return breaches


def evaluate(
    drift_fraction: float,
    performance: float,
    params: PolicyParams,
    pack: DomainPack | None = None,
    values: dict[str, float] | None = None,
) -> Decision:
    """Evaluate one domain's state against a tenant's policy.

    drift_fraction: share of tracked metrics that moved against baseline, 0..1
    performance:    composite health, 0..1, higher is better
    values:         raw metric values, used by exposure-based economics
    """
    drift_fraction = max(0.0, min(drift_fraction, 1.0))
    perf_degradation = max(0.0, params.perf_threshold - performance) / params.perf_threshold

    risk_score = 0.0
    if drift_fraction > params.drift_threshold:
        risk_score += drift_fraction * params.drift_weight
    if perf_degradation > 0:
        risk_score += perf_degradation * params.perf_weight

    if risk_score > params.high_risk_score:
        risk_level = RiskLevel.high
    elif risk_score > params.medium_risk_score:
        risk_level = RiskLevel.medium
    else:
        risk_level = RiskLevel.low

    expected_loss, basis = _expected_daily_loss(pack, params, perf_degradation, values)
    cost = params.intervention_cost_usd

    horizon_loss = expected_loss * params.payback_days

    breaches = _existential_breaches(pack, values)

    if breaches:
        # Escalate regardless of the loss model. Weighing "payroll is covered
        # for 1.4 months" against a $1,200 cost of acting is a category error:
        # the downside is not a daily rate, so the arithmetic that works for a
        # collections push produces a confidently wrong answer here.
        risk_level = RiskLevel.high
        slot = ActionSlot.intervene
        detail = "; ".join(
            f"{label} is {value:g}, past the {bound:g} floor" for label, value, bound in breaches
        )
        reason = (
            f"{detail}. This is not a cost-benefit decision — the consequence of "
            f"breaching it is not measured in daily carrying cost — so the "
            f"payback test does not apply."
        )
    elif risk_level is RiskLevel.high:
        if horizon_loss > cost:
            slot = ActionSlot.intervene
            payback = cost / expected_loss if expected_loss > 0 else float("inf")
            reason = (
                f"${expected_loss:,.2f} a day at risk — {basis} — against a "
                f"${cost:,.2f} one-off cost to act, which pays for itself in "
                f"{payback:.1f} days."
            )
        else:
            slot = ActionSlot.investigate
            # The basis belongs here as much as in the intervene branch —
            # arguably more. This is the message that declines to act, so
            # "$26.00 a day" is exactly the figure a customer will want to
            # see the working for before they accept the conclusion.
            reason = (
                f"Conditions have deteriorated, but ${expected_loss:,.2f} a day at risk "
                f"— {basis} — would take longer than {params.payback_days} days to repay "
                f"the ${cost:,.2f} cost of acting."
            )
    elif risk_level is RiskLevel.medium:
        slot = ActionSlot.monitor
        reason = "Early deterioration. Watching through the next reporting cycle."
    else:
        slot = ActionSlot.none
        reason = "Operating within acceptable bounds."

    spec = pack.action(slot) if pack else _generic_action(slot)

    return Decision(
        slot=slot,
        action=spec.label,
        action_description=spec.description,
        risk_level=risk_level,
        risk_score=risk_score,
        expected_daily_loss_usd=expected_loss,
        action_cost_usd=cost,
        reason=reason,
        requires_approval=spec.requires_approval,
        inputs={
            "drift_fraction": drift_fraction,
            "performance": performance,
            "loss_basis": basis,
        },
    )


def _generic_action(slot: ActionSlot) -> ActionSpec:
    return _GENERIC_ACTIONS[slot]
