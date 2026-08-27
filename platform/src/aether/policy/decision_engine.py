"""Cost-aware decision kernel — ported from the prototype's
api/services/decision_engine.py with every constant lifted into PolicyParams,
so each tenant (and each domain within a tenant) runs its own numbers.

The logic is intentionally unchanged: risk from drift + performance
degradation, dollar impact from tenant-supplied business values, act only when
expected loss outweighs action cost, and HIGH-risk actions route to human
approval (the Nano/Mega gate) instead of executing directly.
"""

from dataclasses import dataclass, field
from enum import StrEnum


class Action(StrEnum):
    no_action = "NO_ACTION"
    monitor = "MONITOR"
    flag_anomaly = "FLAG_ANOMALY"
    retrain = "RETRAIN"


class RiskLevel(StrEnum):
    low = "LOW"
    medium = "MEDIUM"
    high = "HIGH"


@dataclass(frozen=True)
class PolicyParams:
    """Per-tenant, per-domain policy. Stored in PolicyConfig.params (JSONB)."""

    retrain_cost_usd: float = 50.0
    impact_per_error_usd: float = 1000.0  # business cost of one bad decision
    daily_decision_volume: int = 1000
    drift_threshold: float = 0.15  # fraction of features drifted before risk accrues
    perf_threshold: float = 0.85  # minimum acceptable primary metric (e.g. F1)
    drift_weight: float = 0.4
    perf_weight: float = 0.6
    high_risk_score: float = 0.4
    medium_risk_score: float = 0.15
    error_rate_translation: float = 0.1  # degradation → added error rate

    @classmethod
    def from_dict(cls, raw: dict | None) -> "PolicyParams":
        if not raw:
            return cls()
        known = {f: raw[f] for f in cls.__dataclass_fields__ if f in raw}
        return cls(**known)


@dataclass(frozen=True)
class Decision:
    action: Action
    risk_level: RiskLevel
    risk_score: float
    expected_daily_loss_usd: float
    action_cost_usd: float
    reason: str
    requires_approval: bool = False
    inputs: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "action": self.action.value,
            "risk_level": self.risk_level.value,
            "risk_score": round(self.risk_score, 4),
            "expected_daily_loss_usd": round(self.expected_daily_loss_usd, 2),
            "action_cost_usd": self.action_cost_usd,
            "reason": self.reason,
            "requires_approval": self.requires_approval,
            "inputs": self.inputs,
        }


def evaluate(
    drift_fraction: float,
    performance: float,
    params: PolicyParams,
) -> Decision:
    """Evaluate one domain's state against a tenant's policy.

    drift_fraction: share of monitored features drifted, in [0, 1]
    performance:    primary quality metric, in [0, 1] (higher is better)
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

    error_rate_increase = perf_degradation * params.error_rate_translation
    expected_loss = (
        params.daily_decision_volume * error_rate_increase * params.impact_per_error_usd
    )

    action = Action.no_action
    reason = "System operating within acceptable bounds."
    requires_approval = False

    if risk_level is RiskLevel.high:
        if expected_loss > params.retrain_cost_usd:
            action = Action.retrain
            requires_approval = True  # HIGH-risk retrain always gates on a human
            reason = (
                f"High risk: expected daily loss (${expected_loss:,.2f}) outweighs "
                f"retraining cost (${params.retrain_cost_usd:,.2f})."
            )
        else:
            action = Action.flag_anomaly
            reason = (
                f"High risk, but expected loss (${expected_loss:,.2f}) does not justify "
                f"retraining cost."
            )
    elif risk_level is RiskLevel.medium:
        action = Action.monitor
        reason = "Medium risk: placing model under elevated observation."

    return Decision(
        action=action,
        risk_level=risk_level,
        risk_score=risk_score,
        expected_daily_loss_usd=expected_loss,
        action_cost_usd=params.retrain_cost_usd,
        reason=reason,
        requires_approval=requires_approval,
        inputs={"drift_fraction": drift_fraction, "performance": performance},
    )
