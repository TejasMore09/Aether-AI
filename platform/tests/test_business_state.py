"""How a business snapshot describes itself — without a database.

`load()` needs Postgres and is tested in test_business_state_db.py. Everything
else here is reasoning over an object, and reasoning should not need
infrastructure to verify: these run in milliseconds, on every machine, whether
or not Docker happens to be up.

That split matters more than it looks. The rules below are what cross-domain
findings will be built on, so they are the part most likely to be changed
later by someone who cannot easily run the database tests.
"""

import datetime
import uuid

from aether.business.state import BusinessState, DomainSnapshot, utcnow


def snapshot(
    domain: str = "receivables",
    *,
    performance: float = 0.9,
    perf_threshold: float = 0.72,
    age_hours: float = 1.0,
    max_age_hours: float = 192.0,
    metrics: dict | None = None,
    drift: float = 0.0,
) -> DomainSnapshot:
    return DomainSnapshot(
        domain=domain,
        label=domain.replace("_", " ").title(),
        observed_at=utcnow() - datetime.timedelta(hours=age_hours),
        performance=performance,
        drift_fraction=drift,
        metrics=metrics or {},
        stale=age_hours > max_age_hours,
        max_age_hours=max_age_hours,
        perf_threshold=perf_threshold,
    )


def state(*snapshots: DomainSnapshot, silent: tuple[str, ...] = ()) -> BusinessState:
    return BusinessState(
        tenant_id=uuid.uuid4(),
        captured_at=utcnow(),
        domains={s.domain: s for s in snapshots},
        silent=silent,
    )


# ── One domain ────────────────────────────────────────────────────────────────


def test_healthy_is_at_or_above_the_floor():
    assert snapshot(performance=0.80, perf_threshold=0.72).impaired is False
    assert snapshot(performance=0.72, perf_threshold=0.72).impaired is False
    assert snapshot(performance=0.71, perf_threshold=0.72).impaired is True


def test_severity_is_zero_while_healthy():
    """Not a small number — zero. A healthy domain contributes nothing to a
    ranking, and a faint non-zero score would let several healthy domains
    outrank one genuinely sick one."""
    assert snapshot(performance=0.95, perf_threshold=0.72).severity == 0.0
    assert snapshot(performance=0.72, perf_threshold=0.72).severity == 0.0


def test_severity_is_comparable_across_domains_with_different_floors():
    """The reason severity exists at all.

    Raw performance is not comparable: 0.74 is comfortable against a floor of
    0.72 and a real problem against one of 0.92. Ranking domains by
    performance would put the cash domain last precisely when it matters most.
    """
    receivables = snapshot("receivables", performance=0.74, perf_threshold=0.72)
    cash = snapshot("cash_runway", performance=0.74, perf_threshold=0.92)

    assert receivables.impaired is False
    assert cash.impaired is True
    assert cash.severity > receivables.severity


def test_severity_saturates_rather_than_running_away():
    """Zero performance is as bad as the scale goes. Letting it exceed 1 would
    let one collapsed domain dominate every ranking forever."""
    assert snapshot(performance=0.0, perf_threshold=0.72).severity == 1.0


def test_a_nonsense_floor_does_not_divide_by_zero():
    assert snapshot(performance=0.5, perf_threshold=0.0).severity == 0.0


def test_age_is_measured_from_when_it_was_observed():
    assert 5.9 < snapshot(age_hours=6.0).age_hours < 6.1


def test_metrics_are_reachable_and_absence_is_none_not_zero():
    """Zero is a legitimate reading. Conflating it with 'not reported' would
    make a business that owes nothing look identical to one that never said."""
    s = snapshot(metrics={"dso_days": 41.0, "ar_total": 0.0})
    assert s.metric("dso_days") == 41.0
    assert s.metric("ar_total") == 0.0
    assert s.metric("never_reported") is None


# ── The business ──────────────────────────────────────────────────────────────


def test_an_empty_business_answers_calmly():
    empty = state()
    assert empty.impaired == []
    assert empty.worst is None
    assert empty.fresh == {}


def test_impaired_domains_come_back_worst_first():
    mild = snapshot("receivables", performance=0.68, perf_threshold=0.72)
    severe = snapshot("cash_runway", performance=0.20, perf_threshold=0.92)
    fine = snapshot("sales_pipeline", performance=0.99, perf_threshold=0.92)

    ordering = [s.domain for s in state(mild, severe, fine).impaired]
    assert ordering == ["cash_runway", "receivables"]


def test_the_worst_domain_is_the_head_of_that_ordering():
    mild = snapshot("receivables", performance=0.68, perf_threshold=0.72)
    severe = snapshot("cash_runway", performance=0.20, perf_threshold=0.92)
    assert state(mild, severe).worst.domain == "cash_runway"


def test_a_stale_domain_is_excluded_from_impairment():
    """A reading too old to decide on is too old to call impaired. Counting it
    would manufacture a problem out of missing data — and the business would
    be told it is sick on the strength of a number from six weeks ago."""
    stale = snapshot("receivables", performance=0.10, age_hours=2000.0, max_age_hours=192.0)
    assert stale.stale is True
    assert stale.impaired is True, "unhealthy on its face"

    whole = state(stale)
    assert whole.impaired == [], "but not counted"
    assert whole.worst is None
    assert whole.fresh == {}


def test_staleness_is_judged_per_domain_not_globally():
    """Each pack sets its own window; a single global age would either nag the
    slow-reporting domain or trust the fast-moving one far too long."""
    recent_cash = snapshot("cash_runway", age_hours=200.0, max_age_hours=336.0)
    old_receivables = snapshot("receivables", age_hours=200.0, max_age_hours=192.0)

    whole = state(recent_cash, old_receivables)
    assert set(whole.fresh) == {"cash_runway"}


def test_metric_lookup_spans_domains_without_guarding_first():
    """What makes a cross-domain rule readable: ask for a metric from a domain
    the tenant may not even report, and get None rather than an exception."""
    whole = state(snapshot("receivables", metrics={"dso_days": 41.0}))

    assert whole.metric("receivables", "dso_days") == 41.0
    assert whole.metric("cash_runway", "runway_months") is None
    assert whole.metric("receivables", "not_a_metric") is None


def test_membership_and_lookup_read_naturally():
    whole = state(snapshot("receivables"))
    assert "receivables" in whole
    assert "cash_runway" not in whole
    assert whole.get("cash_runway") is None


def test_a_configured_but_silent_domain_is_named_separately():
    """Configured and silent is a setup failure, and it is indistinguishable
    from healthy unless something says so out loud."""
    whole = state(snapshot("receivables"), silent=("cash_runway",))
    assert "cash_runway" not in whole.domains
    assert whole.silent == ("cash_runway",)


def test_serialisation_carries_what_a_prompt_or_an_api_needs():
    whole = state(
        snapshot("receivables", performance=0.4, metrics={"dso_days": 88.0}),
        snapshot("cash_runway", performance=0.99, perf_threshold=0.92),
        silent=("sales_pipeline",),
    )
    payload = whole.as_dict()

    assert payload["impaired"] == ["receivables"]
    assert payload["silent"] == ["sales_pipeline"]
    assert payload["domains"]["receivables"]["metrics"]["dso_days"] == 88.0
    assert payload["domains"]["receivables"]["severity"] > 0
    assert payload["domains"]["cash_runway"]["impaired"] is False
