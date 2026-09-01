"""Cross-domain findings, and the arithmetic of not overstating them.

No database.

The claim a cross-domain finding makes is that two symptoms are one problem.
That claim has an immediate consequence for the money: if the overdue book
*is* the cash shortfall, then adding the two exposures counts the same pounds
twice — and it would inflate every such finding by exactly the amount that
made it worth raising. Most of what follows pins that down.
"""

import datetime
import uuid

from aether.business.correlation import CoMovement
from aether.business.findings import (
    CrossDomainFinding,
    DomainExposure,
    _combine,
    exposure_of,
    for_business,
    from_relation,
)
from aether.business.relations import Confidence, active
from aether.business.state import BusinessState, DomainSnapshot, utcnow
from aether.policy.decision_engine import PolicyParams

# A book slowing while cash tightens — the case this phase exists for.
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
                "receivables",
                RECEIVABLES,
                drifting=("dso_days",),
                health={"overdue_ratio": 0.1},
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


# ── The exposure arithmetic ───────────────────────────────────────────────────


def test_a_finding_never_sums_exposures_across_related_domains():
    """The headline rule. These are one problem measured twice, so adding them
    counts the same money twice — and overstates most exactly where the
    relationship is strongest."""
    a = DomainExposure("receivables", 147.0, "receivables basis")
    b = DomainExposure("cash_runway", 26.0, "cash basis")

    daily, basis = _combine((a, b))

    assert daily == 147.0
    assert daily != a.daily_usd + b.daily_usd
    assert "not the sum" in basis
    assert "count it twice" in basis


def test_the_basis_names_the_other_side_rather_than_hiding_it():
    """Understating quietly would be its own dishonesty. The smaller figure is
    stated, with the reason it is not added."""
    daily, basis = _combine(
        (
            DomainExposure("receivables", 147.0, "receivables basis"),
            DomainExposure("cash_runway", 26.0, "cash basis"),
        )
    )
    assert "cash_runway at $26.00" in basis


def test_a_single_domain_keeps_its_own_basis_verbatim():
    only = DomainExposure("receivables", 147.0, "34% of 400,000 outstanding")
    daily, basis = _combine((only,))
    assert daily == 147.0
    assert basis == "34% of 400,000 outstanding"


def test_no_exposure_is_reported_honestly_rather_than_as_zero_risk():
    daily, basis = _combine(())
    assert daily == 0.0
    assert "no exposure" in basis


def test_a_zero_exposure_partner_does_not_produce_a_double_counting_note():
    """Nothing was double counted, so nothing should claim to have been."""
    daily, basis = _combine(
        (
            DomainExposure("receivables", 147.0, "receivables basis"),
            DomainExposure("cash_runway", 0.0, "cash basis"),
        )
    )
    assert daily == 147.0
    assert "not the sum" not in basis


def test_exposure_matches_what_the_single_domain_decision_would_say():
    """If the two disagreed for the same reading, the customer would be right
    to trust neither."""
    from aether.domains.pack import get_pack
    from aether.policy.decision_engine import expected_daily_loss

    snap = snapshot("receivables", RECEIVABLES, drifting=("dso_days",))
    direct, _ = expected_daily_loss(
        get_pack("receivables"), snap.params, snap.severity, snap.metrics
    )
    assert exposure_of(snap).daily_usd == direct


# ── Building a finding ────────────────────────────────────────────────────────


def test_the_headline_case_becomes_one_finding_naming_both_domains():
    findings = for_business(slowing_business())

    assert findings, "the receivables/cash link should produce a finding"
    top = findings[0]
    assert isinstance(top, CrossDomainFinding)
    assert set(top.domains) == {"receivables", "cash_runway"}
    assert top.daily_usd > 0


def test_a_finding_carries_the_mechanism_a_person_can_read():
    top = for_business(slowing_business())[0]
    assert len(top.mechanism.split()) > 15
    assert "\n" not in top.mechanism, "folded YAML should arrive as one line"
    assert top.guidance


def test_a_finding_quotes_the_readings_that_triggered_it():
    top = next(
        f
        for f in for_business(slowing_business())
        if f.relation_id == "collections_slowing_drains_cash"
    )
    assert top.readings["receivables.dso_days"] == 68.0
    assert top.readings["cash_runway.runway_months"] == 4.1


def test_severity_is_the_worst_domain_not_the_average():
    """A finding is as serious as the most serious thing in it. Averaging
    would let one healthy leg dilute a real crisis in the other."""
    state = slowing_business()
    worst = max(s.severity for s in state.domains.values())
    top = for_business(state)[0]
    assert top.severity == worst


def test_per_domain_exposures_are_kept_alongside_the_combined_one():
    """So the customer can see the working, not just the conclusion."""
    top = for_business(slowing_business())[0]
    assert len(top.per_domain) == 2
    assert {e.domain for e in top.per_domain} == {"receivables", "cash_runway"}
    assert top.daily_usd == max(e.daily_usd for e in top.per_domain)


def test_a_lagged_relation_carries_its_lag_note_into_the_finding():
    """Otherwise the delay that makes it a diagnosis rather than a warning is
    lost exactly where someone would act on it."""
    state = slowing_business()
    state.domains["sales_pipeline"] = snapshot(
        "sales_pipeline",
        {"pipeline_coverage": 1.6, "pipeline_value": 200_000.0, "stalled_ratio": 0.4},
        health={"pipeline_coverage": 0.2},
        perf_threshold=0.92,
    )
    lagged = next(
        (f for f in for_business(state) if f.relation_id == "thin_pipeline_precedes_thin_cash"),
        None,
    )
    assert lagged is not None
    assert "quarter" in lagged.lag_note or "cycle" in lagged.lag_note


# ── Corroboration ─────────────────────────────────────────────────────────────


def test_history_that_supports_the_relation_is_recorded_on_the_finding():
    supporting = CoMovement(
        "receivables",
        "dso_days",
        "cash_runway",
        "runway_months",
        rho=-0.84,
        pairs=11,
        corroborates="collections_slowing_drains_cash",
    )
    state = slowing_business()
    matched = next(m for m in active(state) if m.id == "collections_slowing_drains_cash")

    finding = from_relation(matched, state, (supporting,))
    assert finding.corroborated is True
    assert "11 readings" in finding.corroborated_by[0]
    assert "-0.84" in finding.corroborated_by[0]


def test_corroboration_from_a_different_relation_is_not_borrowed():
    unrelated = CoMovement(
        "sales_pipeline",
        "win_rate",
        "receivables",
        "dso_days",
        rho=-0.9,
        pairs=12,
        corroborates="pressure_to_close_buys_worse_terms",
    )
    state = slowing_business()
    matched = next(m for m in active(state) if m.id == "collections_slowing_drains_cash")

    assert from_relation(matched, state, (unrelated,)).corroborated is False


def test_no_history_leaves_a_finding_uncorroborated_not_weakened():
    """Most tenants will never have enough history for the correlation pass to
    say anything either way. Absence is not evidence against."""
    top = for_business(slowing_business())[0]
    assert top.corroborated is False
    assert top.daily_usd > 0, "and it still stands on the declared mechanism"


# ── Ordering and refusals ─────────────────────────────────────────────────────


def test_findings_are_ordered_by_money_not_by_confidence():
    """The customer is deciding where to spend a morning, not grading the
    epistemology."""
    findings = for_business(slowing_business())
    if len(findings) > 1:
        assert findings[0].daily_usd >= findings[1].daily_usd


def test_a_healthy_business_produces_no_findings():
    healthy = BusinessState(
        tenant_id=uuid.uuid4(),
        captured_at=utcnow(),
        domains={
            "receivables": snapshot(
                "receivables",
                {"dso_days": 31.0, "overdue_ratio": 0.08, "ar_total": 400_000.0},
                health={"dso_days": 1.0},
                performance=0.98,
            ),
            "cash_runway": snapshot(
                "cash_runway",
                {
                    "runway_months": 16.0,
                    "cash_balance": 300_000.0,
                    "committed_outflows_30d": 40_000.0,
                },
                health={"runway_months": 1.0},
                performance=0.99,
                perf_threshold=0.90,
            ),
        },
    )
    assert for_business(healthy) == []


def test_an_empty_business_produces_no_findings():
    empty = BusinessState(tenant_id=uuid.uuid4(), captured_at=utcnow())
    assert for_business(empty) == []


def test_an_unvalidated_relation_still_never_reaches_a_finding():
    """The silence rule from D18 has to survive this layer too — a finding is
    exactly the thing a customer reads."""
    state = BusinessState(
        tenant_id=uuid.uuid4(),
        captured_at=utcnow(),
        domains={
            "sales_pipeline": snapshot(
                "sales_pipeline", {"win_rate": 0.06}, drifting=("win_rate",)
            ),
            "receivables": snapshot("receivables", RECEIVABLES, drifting=("dso_days",)),
        },
    )
    assert all(f.confidence is not Confidence.plausible for f in for_business(state))


def test_serialisation_carries_the_working_not_just_the_answer():
    payload = for_business(slowing_business())[0].as_dict()

    assert payload["confidence"] in {"mechanical", "strong"}
    assert payload["daily_usd"] > 0
    assert payload["exposure_basis"]
    assert len(payload["per_domain"]) == 2
    assert payload["corroborated"] is False
