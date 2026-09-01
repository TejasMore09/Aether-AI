"""Deciding what the customer is actually told.

Cross-domain findings create a problem the moment they work. A business whose
collections slow and cash tightens now generates three things: a receivables
decision, a cash decision, and a finding saying they are the same problem.
Sending all three is worse than before any of this existed — the product has
learned to connect two symptoms and responded by talking more.

So a finding can subsume the single-domain notices it explains. Two rules make
that safe rather than merely quieter:

**Nothing is deleted.** Suppression is about presentation, never about the
record. Every domain decision still happens, still lands in the audit trail,
still gates a human where it should. What changes is that the customer reads
one message instead of three. A system that hid a decision would be trading
the customer's understanding for its own tidiness.

**A finding inherits the urgency of everything it subsumes.** If receivables
alone would have demanded action, the finding that replaces it demands action
too. Folding an urgent notice into a calm summary is the one failure that
would make this feature actively dangerous, and it is the thing most of the
tests here exist to prevent.

There is also a narrower rule that matters in practice: a notice is only
subsumed when the finding actually explains it. A domain can have two problems
at once — a book that is slow *and* disputed — and only one of them may be
part of the cross-domain story. Suppressing the whole domain would hide the
other, so the metrics must overlap before anything is folded away.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

from aether.business.findings import CrossDomainFinding
from aether.business.relations import Confidence, all_relations
from aether.business.state import DomainSnapshot

# Risk levels, most serious first, for comparing what a finding inherits.
_RISK_ORDER = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "": 0}

_CONFIDENCE_ORDER = {Confidence.mechanical: 0, Confidence.strong: 1, Confidence.plausible: 2}


@dataclass(frozen=True)
class DomainNotice:
    """What one domain would have told the customer on its own."""

    domain: str
    action: str
    risk_level: str
    requires_approval: bool
    daily_usd: float
    reason: str
    # Which metrics actually drove it. Needed to tell whether a finding
    # explains this notice or merely happens to mention the same domain.
    contributing: tuple[str, ...] = ()
    # Set when a metric past its critical bound forced the decision on its
    # own. Such a notice is never folded into anything.
    existential: bool = False

    @property
    def urgency(self) -> int:
        return _RISK_ORDER.get(self.risk_level.upper(), 0)


def contributing_metrics(snapshot: DomainSnapshot) -> tuple[str, ...]:
    """Metrics that are drifting or unhealthy in this domain.

    Mirrors what a relation leg considers a hit, so the two agree about
    whether a finding covers a notice.
    """
    return tuple(
        sorted(
            key
            for key in snapshot.per_metric
            if snapshot.is_drifting(key) or ((h := snapshot.health_of(key)) is not None and h < 0.5)
        )
    )


def _legs_for(relation_ids: tuple[str, ...], domain: str) -> set[str]:
    """Every metric the named relations touch in this domain.

    Takes several ids because a finding that absorbed a sibling speaks for it
    too, and must be able to explain the notices the sibling covered.
    """
    wanted = set(relation_ids)
    legs: set[str] = set()
    for relation in all_relations():
        if relation.id in wanted:
            legs |= {leg.metric for leg in relation.legs if leg.domain == domain}
    return legs


def explains(finding: CrossDomainFinding, notice: DomainNotice) -> bool:
    """Whether this finding actually accounts for this notice.

    Naming the domain is not enough. A receivables book can be slow *and*
    disputed; if the finding is about the slowness, the disputes are a separate
    problem and folding them away would hide something nobody explained.
    """
    if notice.domain not in finding.domains:
        return False

    legs = _legs_for((finding.relation_id, *finding.also_covers), notice.domain)
    if not legs:
        return False
    if not notice.contributing:
        # Nothing recorded about what drove the notice, so there is no basis
        # for claiming it is covered. Leave it standing.
        return False
    return bool(legs & set(notice.contributing))


@dataclass(frozen=True)
class Presentation:
    """What to show, and what was folded into what."""

    findings: tuple[CrossDomainFinding, ...] = ()
    standalone: tuple[DomainNotice, ...] = ()
    folded: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def message_count(self) -> int:
        return len(self.findings) + len(self.standalone)

    def as_dict(self) -> dict:
        return {
            "findings": [f.as_dict() for f in self.findings],
            "standalone": [
                {
                    "domain": n.domain,
                    "action": n.action,
                    "risk_level": n.risk_level,
                    "requires_approval": n.requires_approval,
                    "daily_usd": round(n.daily_usd, 2),
                    "reason": n.reason,
                }
                for n in self.standalone
            ],
            "folded": {k: list(v) for k, v in self.folded.items()},
            "message_count": self.message_count,
        }


def _dedupe(
    findings: tuple[CrossDomainFinding, ...],
) -> list[CrossDomainFinding]:
    """Collapse findings that cover the same set of domains.

    Two relations can both fire over the same pair — an overdue book against
    obligation coverage, and a stretching DSO against runway. Those are two
    lenses on one situation, and because a finding's exposure is the largest
    single domain's, both arrive quoting the *same money*. Sending both means
    telling the customer about one problem twice, which is the exact
    redundancy this module exists to remove.

    The strongest claim survives and names the others rather than repeating
    them. Confidence decides, because when both describe the same money the
    useful question is which explanation is most likely to be true.
    """
    by_domains: dict[frozenset[str], list[CrossDomainFinding]] = {}
    for finding in findings:
        by_domains.setdefault(frozenset(finding.domains), []).append(finding)

    kept: list[CrossDomainFinding] = []
    for group in by_domains.values():
        if len(group) == 1:
            kept.append(group[0])
            continue
        group.sort(key=lambda f: (_CONFIDENCE_ORDER[f.confidence], -f.daily_usd, f.relation_id))
        primary, *rest = group
        kept.append(
            dataclasses.replace(
                primary,
                also_seen=tuple(f.label for f in rest),
                also_covers=tuple(f.relation_id for f in rest),
            )
        )

    # Preserve the caller's ordering, which is by money at risk.
    order = {f.relation_id: i for i, f in enumerate(findings)}
    kept.sort(key=lambda f: order[f.relation_id])
    return kept


def apply(
    findings: tuple[CrossDomainFinding, ...],
    notices: tuple[DomainNotice, ...],
) -> Presentation:
    """Fold domain notices into the findings that explain them.

    Findings are considered in the order given — `findings.for_business`
    already sorts them by money at risk — so the largest claim gets first call
    on anything it explains, and a notice is never folded twice.
    """
    findings = tuple(_dedupe(findings))

    claimed: dict[str, list[DomainNotice]] = {}
    remaining: list[DomainNotice] = []

    for notice in notices:
        # An existential breach is never folded into anything. Whatever else
        # is true of a business that cannot make payroll, the message about it
        # should not arrive as a subordinate clause in a summary about
        # collections.
        if notice.existential:
            remaining.append(notice)
            continue

        owner = next((f for f in findings if explains(f, notice)), None)
        if owner is None:
            remaining.append(notice)
        else:
            claimed.setdefault(owner.relation_id, []).append(notice)

    enriched: list[CrossDomainFinding] = []
    folded: dict[str, tuple[str, ...]] = {}

    for finding in findings:
        taken = claimed.get(finding.relation_id, [])
        if not taken:
            enriched.append(finding)
            continue

        # Inherit the most urgent thing folded away. A finding that replaced a
        # decision demanding action must demand action too, or suppression
        # would quietly downgrade the very thing it hid.
        inherited_risk = max((n.risk_level for n in taken), key=lambda r: _RISK_ORDER.get(r, 0))
        gates = any(n.requires_approval for n in taken)

        enriched.append(
            dataclasses.replace(
                finding,
                subsumes=tuple(sorted(n.domain for n in taken)),
                inherited_risk_level=inherited_risk,
                requires_approval=gates,
            )
        )
        folded[finding.relation_id] = tuple(sorted(n.domain for n in taken))

    return Presentation(
        findings=tuple(enriched),
        standalone=tuple(remaining),
        folded=folded,
    )
