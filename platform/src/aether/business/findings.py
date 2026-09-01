"""Turning a matched relation into one finding about the whole business.

This is where "your DSO is stretching" and "your runway is shortening" stop
being two messages.

The hard part is not detecting the pair — `relations.py` does that. It is
saying how much money is at stake without lying about it, and the obvious
answer is wrong.

Each domain already computes its own exposure: receivables might say $147 a
day, cash $26. Adding them gives $173, and $173 is not true. The whole claim
the relation makes is that these are **one problem measured twice** — the
overdue book *is* the cash shortfall. Summing would inflate every cross-domain
finding by exactly the amount that made it worth raising, and the more
strongly the domains were related, the more it would overstate.

So the combined figure is the **largest single exposure, never the sum**, and
it says so. A relation may declare `exposure: sum` when its legs genuinely
describe separate money, but nothing does today and the default is the
conservative one. Being quietly understated is a survivable flaw in a system
whose job is to be believed; being enthusiastically overstated is not.
"""

from __future__ import annotations

from dataclasses import dataclass

from aether.business.correlation import CoMovement
from aether.business.relations import ActiveRelation, Confidence, active
from aether.business.state import BusinessState, DomainSnapshot
from aether.domains.pack import get_pack
from aether.policy.decision_engine import expected_daily_loss


@dataclass(frozen=True)
class DomainExposure:
    """One domain's money at risk, and how that number was arrived at."""

    domain: str
    daily_usd: float
    basis: str


def exposure_of(snapshot: DomainSnapshot) -> DomainExposure:
    """What this domain is costing per day, using the same computation the
    single-domain decision used.

    Deliberately not an approximation. If a cross-domain finding quoted a
    different number from the per-domain one for the same reading, the
    customer would be right to trust neither.
    """
    pack = get_pack(snapshot.domain)
    loss, basis = expected_daily_loss(pack, snapshot.params, snapshot.severity, snapshot.metrics)
    return DomainExposure(domain=snapshot.domain, daily_usd=loss, basis=basis)


@dataclass(frozen=True)
class CrossDomainFinding:
    """One problem, seen in more than one part of the business."""

    relation_id: str
    label: str
    confidence: Confidence
    domains: tuple[str, ...]
    mechanism: str
    guidance: str
    lag_note: str
    readings: dict[str, float]
    per_domain: tuple[DomainExposure, ...]
    daily_usd: float
    exposure_basis: str
    severity: float
    corroborated_by: tuple[str, ...] = ()

    # Filled in by presentation.apply() when this finding takes over the
    # telling of a single-domain notice. Kept here rather than alongside,
    # because whatever renders the finding needs to know it is now speaking
    # for more than itself.
    subsumes: tuple[str, ...] = ()
    # The most urgent thing folded away. A finding that replaced a decision
    # demanding action must demand action too — see D21.
    inherited_risk_level: str = ""
    requires_approval: bool = False
    # Labels of other findings covering the same domains, folded in by
    # presentation.apply(). Their exposure is the same money seen through a
    # different mechanism, so they are named rather than repeated in full.
    also_seen: tuple[str, ...] = ()
    # Relation ids this finding now speaks for, beyond its own. A survivor
    # that absorbed a sibling must also absorb its coverage, or notices the
    # sibling would have explained fall through and get told separately —
    # reintroducing the duplication the fold was meant to remove.
    also_covers: tuple[str, ...] = ()

    @property
    def corroborated(self) -> bool:
        """Whether this tenant's own history shows the pattern too.

        Absence is not evidence against: most tenants will not have enough
        history for the correlation pass to say anything either way.
        """
        return bool(self.corroborated_by)

    def as_dict(self) -> dict:
        return {
            "relation_id": self.relation_id,
            "label": self.label,
            "confidence": self.confidence.value,
            "domains": list(self.domains),
            "mechanism": self.mechanism,
            "guidance": self.guidance,
            "lag_note": self.lag_note,
            "readings": self.readings,
            "daily_usd": round(self.daily_usd, 2),
            "exposure_basis": self.exposure_basis,
            "per_domain": [
                {"domain": e.domain, "daily_usd": round(e.daily_usd, 2), "basis": e.basis}
                for e in self.per_domain
            ],
            "severity": round(self.severity, 4),
            "corroborated": self.corroborated,
            "corroborated_by": list(self.corroborated_by),
            "subsumes": list(self.subsumes),
            "inherited_risk_level": self.inherited_risk_level,
            "requires_approval": self.requires_approval,
            "also_seen": list(self.also_seen),
            "also_covers": list(self.also_covers),
        }


def _combine(exposures: tuple[DomainExposure, ...]) -> tuple[float, str]:
    """The finding's headline figure, and the sentence explaining it.

    See the module docstring for why this is a maximum rather than a sum.
    """
    if not exposures:
        return 0.0, "no exposure could be computed for these domains"

    largest = max(exposures, key=lambda e: e.daily_usd)
    if len(exposures) == 1 or largest.daily_usd == 0:
        return largest.daily_usd, largest.basis

    others = [e for e in exposures if e is not largest and e.daily_usd > 0]
    if not others:
        return largest.daily_usd, largest.basis

    named = ", ".join(f"{e.domain} at ${e.daily_usd:,.2f}" for e in others)
    return (
        largest.daily_usd,
        f"{largest.basis} — the largest single exposure, not the sum. "
        f"{named} measures the same money from the other side, "
        f"and adding them would count it twice",
    )


def from_relation(
    matched: ActiveRelation,
    state: BusinessState,
    co_movements: tuple[CoMovement, ...] = (),
) -> CrossDomainFinding:
    exposures = tuple(
        exposure_of(snapshot)
        for domain in matched.domains
        if (snapshot := state.get(domain)) is not None
    )
    daily, basis = _combine(exposures)

    # The worst domain involved, not the average of them. A finding is as
    # serious as the most serious thing in it; averaging would let one healthy
    # leg dilute a genuine crisis in the other.
    severity = max(
        (s.severity for domain in matched.domains if (s := state.get(domain)) is not None),
        default=0.0,
    )

    supporting = tuple(
        f"{c.domain_a}.{c.metric_a} and {c.domain_b}.{c.metric_b} "
        f"moved together across {c.pairs} readings (rho {c.rho:+.2f})"
        for c in co_movements
        if c.corroborates == matched.id
    )

    relation = matched.relation
    return CrossDomainFinding(
        relation_id=relation.id,
        label=relation.label,
        confidence=relation.confidence,
        domains=matched.domains,
        mechanism=" ".join(relation.mechanism.split()),
        guidance=" ".join(relation.guidance.split()),
        lag_note=" ".join(relation.lag_note.split()),
        readings=matched.values,
        per_domain=exposures,
        daily_usd=daily,
        exposure_basis=basis,
        severity=severity,
        corroborated_by=supporting,
    )


def for_business(
    state: BusinessState, co_movements: tuple[CoMovement, ...] = ()
) -> list[CrossDomainFinding]:
    """Every cross-domain finding for one business, most serious first.

    Ordered by money at risk rather than by confidence. A merely strong claim
    about a large sum deserves attention before a mechanical certainty about a
    trivial one — the customer is deciding where to spend a morning, not
    grading the epistemology.
    """
    findings = [from_relation(m, state, co_movements) for m in active(state)]
    findings.sort(key=lambda f: (f.daily_usd, f.severity), reverse=True)
    return findings
