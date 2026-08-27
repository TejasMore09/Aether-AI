"""Domain packs: what the platform knows about a business function.

A pack is curated configuration, not code and not a trained model. It declares
which metrics a domain reports, what healthy looks like, how raw metrics become
the risk signals the decision engine consumes, what actions exist, and how an
explanation for this domain should read.

Adding a business function to the product means writing a pack. It must never
mean editing agent code — that constraint is what keeps expansion cheap.

Packs ship as YAML under packs/ and are loaded once into a process-level
registry. Tenants override thresholds through PolicyConfig; the pack supplies
the defaults and the vocabulary.
"""

from __future__ import annotations

import functools
import pathlib
from dataclasses import dataclass, field
from enum import StrEnum

import yaml

_PACK_DIR = pathlib.Path(__file__).parent / "packs"


class Direction(StrEnum):
    """Which way is good for a metric."""

    lower_better = "lower_better"
    higher_better = "higher_better"
    neutral = "neutral"  # carried for context and prompts, never scored


class ActionSlot(StrEnum):
    """Domain-independent decision outcomes.

    The engine reasons in slots; the pack supplies each slot's label and
    meaning for its domain. This is why the engine has no idea what
    'receivables' is, and why 'RETRAIN' does not leak into a finance product.
    """

    none = "none"
    monitor = "monitor"
    investigate = "investigate"  # serious, but not worth the cost of acting
    intervene = "intervene"  # serious and worth acting on — gated on a human


class EconomicsModel(StrEnum):
    """How a domain turns an unhealthy reading into money per day.

    Three models rather than one because business functions genuinely fail in
    different shapes. Forcing cash-runway into the receivables model would
    mean inventing an "at risk fraction" the customer never reports.
    """

    exposure_scaled = "exposure_scaled"  # money at risk × rate
    degradation_scaled = "degradation_scaled"  # volume × error rate × unit cost
    # Obligations that must be met, minus what is available to meet them. The
    # shortfall is derived rather than reported: nobody records "percentage of
    # my bills I cannot pay", they record cash and they record what is due.
    shortfall_scaled = "shortfall_scaled"


@dataclass(frozen=True)
class MetricSpec:
    key: str
    label: str
    unit: str
    direction: Direction
    required: bool = False
    minimum: float | None = None
    maximum: float | None = None
    healthy_min: float | None = None
    healthy_max: float | None = None
    critical_min: float | None = None
    critical_max: float | None = None
    weight: float = 1.0
    description: str = ""
    # Some breaches are not cost-benefit decisions. Missing payroll is not a
    # daily carrying charge that can be weighed against the cost of acting —
    # it is terminal, and the loss model has no way to express that because a
    # linear rate cannot represent a non-linear downside. A metric marked
    # existential escalates on its own once past its critical bound, and the
    # payback test is skipped rather than quietly producing a wrong answer.
    #
    # Use sparingly. Marking everything existential turns the economics engine
    # off, which is the failure this flag exists to avoid in the other
    # direction.
    existential: bool = False

    def breached_critically(self, value: float) -> bool:
        """Past the pack's critical bound. Never the calibrated one — critical
        is the absolute line and does not move per tenant."""
        if self.direction is Direction.lower_better:
            return self.critical_max is not None and value >= self.critical_max
        if self.direction is Direction.higher_better:
            return self.critical_min is not None and value <= self.critical_min
        return False

    @property
    def scored(self) -> bool:
        return self.direction is not Direction.neutral

    def health_score(self, value: float) -> float | None:
        """Map a raw value onto 0..1, where 1 is healthy and 0 is critical.

        Returns None for unscored metrics. Values beyond the critical bound
        clamp to 0 rather than going negative: 'twice as bad as critical' is
        not twice as informative, and letting it run negative would let one
        metric swamp the composite.
        """
        if not self.scored:
            return None
        if self.direction is Direction.lower_better:
            good, bad = self.healthy_max, self.critical_max
        else:
            good, bad = self.healthy_min, self.critical_min
        if good is None or bad is None or good == bad:
            return None
        # Linear between the healthy bound (1.0) and the critical bound (0.0).
        span = bad - good
        score = 1.0 - ((value - good) / span)
        return max(0.0, min(1.0, score))


@dataclass(frozen=True)
class ActionSpec:
    slot: ActionSlot
    label: str
    description: str
    requires_approval: bool = False


@dataclass(frozen=True)
class Economics:
    model: EconomicsModel = EconomicsModel.degradation_scaled
    intervention_cost_usd: float = 250.0
    # exposure_scaled / shortfall_scaled
    exposure_metric: str | None = None
    at_risk_metric: str | None = None
    # shortfall_scaled only: what is available to meet the exposure.
    cover_metric: str | None = None
    daily_rate: float = 0.0004  # ~15%/yr cost of capital, per day
    payback_days: int = 7
    # What the exposure *is*, in the domain's own words. Without this the
    # engine's explanation of a marketing decision would talk about money
    # "outstanding", which is receivables vocabulary leaking through the one
    # abstraction that exists to keep domains apart.
    exposure_noun: str = "outstanding"
    # degradation_scaled
    daily_decision_volume: int = 1000
    impact_per_error_usd: float = 1000.0
    error_rate_translation: float = 0.1


@dataclass(frozen=True)
class Narrative:
    audience: str = ""
    must_cover: tuple[str, ...] = ()
    avoid: tuple[str, ...] = ()


@dataclass(frozen=True)
class DomainPack:
    key: str
    version: int
    label: str
    summary: str
    metrics: tuple[MetricSpec, ...]
    actions: dict[ActionSlot, ActionSpec]
    economics: Economics
    narrative: Narrative
    max_age_hours: float = 24.0
    drift_tolerance: float = 0.25  # relative move before a metric counts as drifted
    severity_bias: float = 0.4  # how much the worst single metric pulls the composite
    baseline_window: int = 12  # readings used to form the tenant's own baseline

    # Per-tenant calibration of the healthy bound. See domains/calibration.py
    # for why these are bounded rather than free: an unanchored band lets a
    # chronically unhealthy business learn that its dysfunction is normal.
    # Both limits are fractions of the pack's own healthy-to-critical span.
    calibration_min_readings: int = 8
    calibration_max_loosen: float = 0.6  # at most 60% of the way toward critical
    calibration_max_tighten: float = 0.6
    policy_defaults: dict = field(default_factory=dict)

    def metric(self, key: str) -> MetricSpec | None:
        return next((m for m in self.metrics if m.key == key), None)

    @property
    def required_metrics(self) -> tuple[str, ...]:
        return tuple(m.key for m in self.metrics if m.required)

    @property
    def scored_metrics(self) -> tuple[MetricSpec, ...]:
        return tuple(m for m in self.metrics if m.scored)

    def action(self, slot: ActionSlot) -> ActionSpec:
        return self.actions.get(slot, _GENERIC_ACTIONS[slot])


# Fallback vocabulary for a domain with no pack — deliberately generic, so an
# unpacked domain still works rather than failing.
_GENERIC_ACTIONS: dict[ActionSlot, ActionSpec] = {
    ActionSlot.none: ActionSpec(ActionSlot.none, "NO_ACTION", "Operating within bounds."),
    ActionSlot.monitor: ActionSpec(
        ActionSlot.monitor, "MONITOR", "Elevated observation; no action yet."
    ),
    ActionSlot.investigate: ActionSpec(
        ActionSlot.investigate,
        "FLAG_FOR_REVIEW",
        "Serious, but the cost of acting is not justified by the exposure.",
    ),
    ActionSlot.intervene: ActionSpec(
        ActionSlot.intervene,
        "INTERVENE",
        "Serious and economically justified; requires human approval.",
        requires_approval=True,
    ),
}


def _spec_from_dict(raw: dict) -> MetricSpec:
    return MetricSpec(
        key=raw["key"],
        label=raw["label"],
        unit=raw.get("unit", ""),
        direction=Direction(raw.get("direction", "neutral")),
        required=bool(raw.get("required", False)),
        minimum=raw.get("min"),
        maximum=raw.get("max"),
        healthy_min=raw.get("healthy_min"),
        healthy_max=raw.get("healthy_max"),
        critical_min=raw.get("critical_min"),
        critical_max=raw.get("critical_max"),
        weight=float(raw.get("weight", 1.0)),
        description=raw.get("description", ""),
        existential=bool(raw.get("existential", False)),
    )


def _pack_from_dict(raw: dict) -> DomainPack:
    actions: dict[ActionSlot, ActionSpec] = {}
    for slot_name, spec in (raw.get("actions") or {}).items():
        slot = ActionSlot(slot_name)
        actions[slot] = ActionSpec(
            slot=slot,
            label=spec["label"],
            description=spec.get("description", ""),
            requires_approval=bool(spec.get("requires_approval", False)),
        )

    econ_raw = raw.get("economics") or {}
    economics = Economics(
        model=EconomicsModel(econ_raw.get("model", "degradation_scaled")),
        intervention_cost_usd=float(econ_raw.get("intervention_cost_usd", 250.0)),
        exposure_metric=econ_raw.get("exposure_metric"),
        at_risk_metric=econ_raw.get("at_risk_metric"),
        cover_metric=econ_raw.get("cover_metric"),
        daily_rate=float(econ_raw.get("daily_rate", 0.0004)),
        payback_days=int(econ_raw.get("payback_days", 7)),
        exposure_noun=str(econ_raw.get("exposure_noun", "outstanding")),
        daily_decision_volume=int(econ_raw.get("daily_decision_volume", 1000)),
        impact_per_error_usd=float(econ_raw.get("impact_per_error_usd", 1000.0)),
        error_rate_translation=float(econ_raw.get("error_rate_translation", 0.1)),
    )

    narr_raw = raw.get("narrative") or {}
    narrative = Narrative(
        audience=narr_raw.get("audience", ""),
        must_cover=tuple(narr_raw.get("must_cover", ())),
        avoid=tuple(narr_raw.get("avoid", ())),
    )

    return DomainPack(
        key=raw["key"],
        version=int(raw.get("version", 1)),
        label=raw["label"],
        summary=raw.get("summary", "").strip(),
        metrics=tuple(_spec_from_dict(m) for m in raw.get("metrics", [])),
        actions=actions,
        economics=economics,
        narrative=narrative,
        max_age_hours=float(raw.get("max_age_hours", 24.0)),
        drift_tolerance=float(raw.get("drift_tolerance", 0.25)),
        severity_bias=float(raw.get("severity_bias", 0.4)),
        baseline_window=int(raw.get("baseline_window", 12)),
        calibration_min_readings=int(raw.get("calibration_min_readings", 8)),
        calibration_max_loosen=float(raw.get("calibration_max_loosen", 0.6)),
        calibration_max_tighten=float(raw.get("calibration_max_tighten", 0.6)),
        policy_defaults=dict(raw.get("policy_defaults") or {}),
    )


@functools.lru_cache(maxsize=1)
def _registry() -> dict[str, DomainPack]:
    packs: dict[str, DomainPack] = {}
    for path in sorted(_PACK_DIR.glob("*.yaml")):
        with path.open(encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        pack = _pack_from_dict(raw)
        packs[pack.key] = pack
    return packs


def get_pack(domain: str) -> DomainPack | None:
    """The pack for a domain, or None for a domain with no pack yet.

    A missing pack is not an error: a tenant may push raw signals for a domain
    the catalogue does not cover, and the generic path still works.
    """
    return _registry().get(domain)


def list_packs() -> list[DomainPack]:
    return list(_registry().values())
