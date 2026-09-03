"""Suppression: what the customer is told, and what must never be hidden.

No database.

Suppression is the one feature here that makes the product say *less*, which
makes its failure mode different from everything else. A missed fold costs a
redundant message. A wrong fold costs a customer the message they most needed
— folded into a calmer one, phrased as though it were covered. Almost every
test below is about the second kind.
"""

import datetime
import uuid

from aether.business.findings import for_business
from aether.business.presentation import (
    DomainNotice,
    apply,
    contributing_metrics,
    explains,
)
from aether.business.relations import Confidence
from aether.business.state import BusinessState, DomainSnapshot, utcnow
from aether.policy.decision_engine import PolicyParams

RECEIVABLES = {
    "dso_days": 68.0,
    "overdue_ratio": 0.34,
    "ar_total": 400_000.0,
    "invoice_count": 210,
}
CASH = {
    "runway_months": 4.1,
    "payroll_cover_months": 2.2,
    "obligation_coverage": 0.86,
    "cash_balance": 62_000.0,
    "committed_outflows_30d": 72_000.0,
}


def snapshot(
    domain: str,
    metrics: dict[str, float],
    *,
    drifting: tuple[str, ...] = (),
    health: dict[str, float] | None = None,
    performance: float = 0.40,
    perf_threshold: float = 0.72,
) -> DomainSnapshot:
    per_metric: dict[str, dict] = {}
    for key in set(drifting) | set(health or {}):
        entry: dict = {}
        if key in drifting:
            entry["drifted"] = True
        if health and key in health:
            entry["health"] = health[key]
        per_metric[key] = entry

    return DomainSnapshot(
        domain=domain,
        label=domain,
        observed_at=utcnow() - datetime.timedelta(hours=1),
        performance=performance,
        drift_fraction=0.5,
        metrics=metrics,
        per_metric=per_metric,
        params=PolicyParams(perf_threshold=perf_threshold),
    )


def slowing_business() -> BusinessState:
    return BusinessState(
        tenant_id=uuid.uuid4(),
        captured_at=utcnow(),
        domains={
            "receivables": snapshot(
                "receivables", RECEIVABLES, drifting=("dso_days",), health={"overdue_ratio": 0.1}
            ),
            "cash_runway": snapshot(
                "cash_runway",
                CASH,
                drifting=("runway_months",),
                health={"obligation_coverage": 0.2},
                performance=0.30,
                perf_threshold=0.90,
            ),
        },
    )


def notice(
    domain: str,
    *,
    action: str = "ESCALATE_COLLECTIONS",
    risk: str = "HIGH",
    approval: bool = True,
    contributing: tuple[str, ...] = ("dso_days",),
    existential: bool = False,
    daily: float = 147.0,
) -> DomainNotice:
    return DomainNotice(
        domain=domain,
        action=action,
        risk_level=risk,
        requires_approval=approval,
        daily_amount=daily,
        reason=f"{domain} on its own",
        contributing=contributing,
        existential=existential,
    )


# ── The point of the feature ──────────────────────────────────────────────────


def test_three_messages_about_one_problem_become_one():
    findings = tuple(for_business(slowing_business()))
    notices = (
        notice("receivables", contributing=("dso_days", "overdue_ratio")),
        notice("cash_runway", action="PROTECT_RUNWAY", contributing=("runway_months",), daily=26.0),
    )

    before = len(findings) + len(notices)
    shown = apply(findings, notices)

    assert shown.standalone == (), "both notices were explained by a finding"
    assert shown.message_count == 1, "one problem should arrive as one message"
    assert shown.message_count < before
    assert set(shown.findings[0].subsumes) == {"cash_runway", "receivables"}


def test_what_was_folded_is_recorded_rather_than_vanishing():
    """Suppression is about presentation. Nothing is deleted, and the record
    says what took over the telling."""
    findings = tuple(for_business(slowing_business()))
    shown = apply(findings, (notice("receivables"),))

    assert shown.folded, "the fold should be recorded"
    assert "receivables" in next(iter(shown.folded.values()))


# ── Urgency must survive being folded ─────────────────────────────────────────


def test_a_finding_inherits_the_urgency_of_what_it_replaced():
    """The failure that would make this feature dangerous: an urgent notice
    folded into a calm summary, phrased as though it were covered."""
    findings = tuple(for_business(slowing_business()))
    urgent = notice("receivables", risk="HIGH", approval=True)

    shown = apply(findings, (urgent,))
    carrier = next(f for f in shown.findings if "receivables" in f.subsumes)

    assert carrier.requires_approval is True
    assert carrier.inherited_risk_level == "HIGH"


def test_the_most_urgent_of_several_folded_notices_wins():
    findings = tuple(for_business(slowing_business()))
    shown = apply(
        findings,
        (
            notice("receivables", risk="HIGH", approval=True),
            notice(
                "cash_runway",
                risk="MEDIUM",
                approval=False,
                contributing=("runway_months",),
            ),
        ),
    )
    carrier = next(f for f in shown.findings if f.subsumes)
    assert carrier.inherited_risk_level == "HIGH"
    assert carrier.requires_approval is True


def test_a_finding_that_folded_nothing_claims_no_urgency():
    """It should not acquire authority it was never given."""
    findings = tuple(for_business(slowing_business()))
    shown = apply(findings, ())

    for finding in shown.findings:
        assert finding.subsumes == ()
        assert finding.requires_approval is False
        assert finding.inherited_risk_level == ""


# ── What must never be folded ─────────────────────────────────────────────────


def test_an_existential_breach_is_never_folded_into_anything():
    """Whatever else is true of a business that cannot make payroll, the
    message about it must not arrive as a subordinate clause in a summary
    about collections."""
    findings = tuple(for_business(slowing_business()))
    payroll = notice(
        "cash_runway",
        action="PROTECT_RUNWAY",
        contributing=("runway_months", "payroll_cover_months"),
        existential=True,
    )

    shown = apply(findings, (payroll,))

    assert payroll in shown.standalone
    assert all("cash_runway" not in f.subsumes for f in shown.findings)


def test_an_unrelated_problem_in_a_named_domain_still_stands():
    """A book can be slow *and* disputed. The finding is about slowness;
    folding the whole domain away would hide the disputes."""
    findings = tuple(for_business(slowing_business()))
    disputes = notice(
        "receivables",
        action="FLAG_FOR_REVIEW",
        contributing=("disputed_ratio",),
    )

    shown = apply(findings, (disputes,))
    assert disputes in shown.standalone


def test_a_notice_from_a_domain_the_finding_never_mentions_stands():
    findings = tuple(for_business(slowing_business()))
    elsewhere = notice("sales_pipeline", contributing=("stalled_ratio",))

    shown = apply(findings, (elsewhere,))
    assert elsewhere in shown.standalone


def test_a_notice_with_no_recorded_cause_is_not_assumed_covered():
    """No basis for the claim that a finding explains it, so it is left
    standing rather than folded on the strength of sharing a domain name."""
    findings = tuple(for_business(slowing_business()))
    vague = notice("receivables", contributing=())

    shown = apply(findings, (vague,))
    assert vague in shown.standalone


def test_nothing_is_folded_when_there_are_no_findings():
    notices = (notice("receivables"), notice("cash_runway"))
    shown = apply((), notices)

    assert shown.standalone == notices
    assert shown.findings == ()
    assert shown.folded == {}


# ── Mechanics ─────────────────────────────────────────────────────────────────


def test_a_notice_is_folded_into_only_one_finding():
    """Two findings can name the same domain. The notice belongs to one of
    them, or the customer reads about it twice again."""
    findings = tuple(for_business(slowing_business()))
    shown = apply(findings, (notice("receivables"),))

    owners = [f for f in shown.findings if "receivables" in f.subsumes]
    assert len(owners) == 1


def test_explains_requires_an_overlap_not_just_a_shared_domain():
    finding = for_business(slowing_business())[0]

    assert explains(finding, notice("receivables", contributing=("dso_days",))) is True
    assert explains(finding, notice("receivables", contributing=("disputed_ratio",))) is False
    assert explains(finding, notice("sales_pipeline", contributing=("dso_days",))) is False


def test_contributing_metrics_match_what_a_relation_leg_counts_as_a_hit():
    """The two must agree, or a finding will claim to explain a notice driven
    by something it never looked at."""
    snap = snapshot(
        "receivables",
        RECEIVABLES,
        drifting=("dso_days",),
        health={"overdue_ratio": 0.1, "top5_concentration": 0.95},
    )
    found = contributing_metrics(snap)

    assert "dso_days" in found, "drifting counts"
    assert "overdue_ratio" in found, "unhealthy counts"
    assert "top5_concentration" not in found, "healthy does not"


def test_presentation_serialises_with_the_folding_visible():
    findings = tuple(for_business(slowing_business()))
    payload = apply(findings, (notice("receivables"),)).as_dict()

    assert payload["message_count"] >= 1
    assert payload["folded"]
    assert isinstance(payload["standalone"], list)


# ── Two findings about the same money ─────────────────────────────────────────


def test_findings_over_the_same_domains_are_not_told_twice():
    """Two relations can fire over the same pair — an overdue book against
    obligation coverage, and a stretching DSO against runway. Because a
    finding's exposure is the largest single domain's, both quote the *same
    money*, and telling both is telling the customer about one problem twice.

    Collapsed in for_business rather than here, so no caller can route around
    it — the prompt layer did exactly that and rendered the exposure paragraph
    twice."""
    findings = tuple(for_business(slowing_business()))

    assert len(findings) == 1
    assert findings[0].also_seen, "the other mechanism is named, not discarded"

    shown = apply(findings, ())
    assert len(shown.findings) == 1


def test_the_stronger_claim_survives_and_names_the_other():
    """When both describe the same money, the useful question is which
    explanation is most likely to be true — and the other is not discarded."""
    findings = tuple(for_business(slowing_business()))
    shown = apply(findings, ())

    kept = shown.findings[0]
    assert kept.confidence is Confidence.mechanical
    assert kept.also_seen, "the other mechanism should be named, not dropped"
    assert "cash" in kept.also_seen[0].lower() or "collections" in kept.also_seen[0].lower()


def test_findings_over_different_domains_are_both_kept():
    """Deduplication is about the same money, not about tidiness."""
    state = slowing_business()
    state.domains["sales_pipeline"] = snapshot(
        "sales_pipeline",
        {"pipeline_coverage": 1.6, "pipeline_value": 900_000.0, "stalled_ratio": 0.45},
        health={"pipeline_coverage": 0.2},
        perf_threshold=0.92,
    )
    shown = apply(tuple(for_business(state)), ())

    domain_sets = {frozenset(f.domains) for f in shown.findings}
    assert len(domain_sets) == len(shown.findings), "one message per distinct problem"
    assert len(shown.findings) >= 2
