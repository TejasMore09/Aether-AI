"""Turning business metrics into the two signals the engine reasons about.

The decision engine deliberately knows nothing about receivables. It consumes
a performance score and a drift fraction. This module is the translation, and
it is the only place a domain's metrics meet the generic engine.

Performance is absolute: how healthy the metrics are against the pack's bands.
Drift is relative: how far they have moved from this tenant's own recent
history. A business can be steadily unhealthy (low performance, no drift) or
suddenly worse from a healthy base (high performance, high drift) — the two
signals answer different questions and both feed the risk score.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from aether.domains.pack import DomainPack


@dataclass(frozen=True)
class DerivedSignals:
    performance: float
    drift_fraction: float
    per_metric: dict[str, dict] = field(default_factory=dict)
    baseline_used: bool = False
    contributing: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "performance": round(self.performance, 4),
            "drift_fraction": round(self.drift_fraction, 4),
            "baseline_used": self.baseline_used,
            "contributing": self.contributing,
            "per_metric": self.per_metric,
        }


def derive_performance(pack: DomainPack, values: dict[str, float]) -> tuple[float, dict]:
    """Weighted health across the pack's scored metrics.

    Missing optional metrics are skipped rather than penalised — a business
    that cannot report collection effectiveness should not look unhealthy for
    it. With no scored metrics at all, performance is 1.0 and drift carries
    the decision.
    """
    total_weight = 0.0
    total_score = 0.0
    detail: dict[str, dict] = {}

    for spec in pack.scored_metrics:
        value = values.get(spec.key)
        if value is None:
            continue
        score = spec.health_score(value)
        if score is None:
            continue
        total_weight += spec.weight
        total_score += score * spec.weight
        detail[spec.key] = {
            "value": value,
            "label": spec.label,
            "unit": spec.unit,
            "health": round(score, 4),
        }

    if not total_weight:
        return 1.0, detail

    mean = total_score / total_weight
    worst = min(v["health"] for v in detail.values())

    # A weighted mean alone lets healthy secondary metrics average away a
    # crisis in a core one: a book with DSO at 95 days and 45% overdue would
    # score middling because concentration and disputes look fine. Blending
    # the mean with the worst single metric keeps the overall picture while
    # letting one genuinely critical number pull the composite down — which
    # is how a finance lead actually reads the same page.
    bias = pack.severity_bias
    performance = (1.0 - bias) * mean + bias * worst
    return performance, detail


def derive_drift(
    pack: DomainPack,
    values: dict[str, float],
    history: list[dict[str, float]],
) -> tuple[float, list[str], bool]:
    """Fraction of scored metrics that moved beyond tolerance versus baseline.

    The baseline is the median of this tenant's recent accepted readings —
    median rather than mean because one bad month should not redefine normal.
    With too little history there is no baseline, and drift is reported as
    zero rather than guessed: an unknown is not a signal.
    """
    usable = [h for h in history if h]
    if len(usable) < 3:
        return 0.0, [], False

    drifted: list[str] = []
    considered = 0

    for spec in pack.scored_metrics:
        current = values.get(spec.key)
        if current is None:
            continue
        past = [h[spec.key] for h in usable if spec.key in h and h[spec.key] is not None]
        if len(past) < 3:
            continue

        baseline = statistics.median(past)
        considered += 1

        # Relative move, with an absolute floor so near-zero baselines do not
        # produce infinite drift.
        denominator = max(abs(baseline), 1e-6)
        move = abs(current - baseline) / denominator

        # Only movement in the unhealthy direction counts. A business whose
        # DSO halves has not "drifted" into a problem.
        if spec.direction == "lower_better" and current < baseline:
            continue
        if spec.direction == "higher_better" and current > baseline:
            continue

        if move > pack.drift_tolerance:
            drifted.append(spec.key)

    if considered == 0:
        return 0.0, [], False

    return len(drifted) / considered, drifted, True


def derive_signals(
    pack: DomainPack,
    values: dict[str, float],
    history: list[dict[str, float]] | None = None,
) -> DerivedSignals:
    performance, detail = derive_performance(pack, values)
    drift, drifted, baseline_used = derive_drift(pack, values, history or [])

    for key in drifted:
        if key in detail:
            detail[key]["drifted"] = True

    return DerivedSignals(
        performance=performance,
        drift_fraction=drift,
        per_metric=detail,
        baseline_used=baseline_used,
        contributing=drifted,
    )
