"""Cross-domain relations: loading, matching, and what must never fire.

No database — these run against hand-built states, which is the point of
BusinessState being inert.

The tests worth reading are the negative ones. A relation that fails to fire
costs a missed insight; a relation that fires wrongly tells a real company that
two unrelated numbers are one problem, and they believe it because the system
sounds certain. Most of what follows is about the second kind.
"""

import dataclasses
import datetime
import uuid

import pytest

from aether.business.relations import (
    Confidence,
    LegState,
    Relation,
    active,
    all_relations,
)
from aether.business.state import BusinessState, DomainSnapshot, utcnow


def snapshot(
    domain: str,
    *,
    metrics: dict[str, float] | None = None,
    drifting: tuple[str, ...] = (),
    health: dict[str, float] | None = None,
    age_hours: float = 1.0,
    max_age_hours: float = 192.0,
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
        observed_at=utcnow() - datetime.timedelta(hours=age_hours),
        performance=0.5,
        drift_fraction=0.0,
        metrics=metrics or {},
        per_metric=per_metric,
        stale=age_hours > max_age_hours,
        max_age_hours=max_age_hours,
    )


def state(*snapshots: DomainSnapshot) -> BusinessState:
    return BusinessState(
        tenant_id=uuid.uuid4(),
        captured_at=utcnow(),
        domains={s.domain: s for s in snapshots},
    )


# ── The file itself ───────────────────────────────────────────────────────────


def test_the_relations_file_loads():
    assert len(all_relations()) >= 3


def test_every_relation_explains_itself():
    """A relation nobody could explain is one nobody can audit, and being
    auditable is the entire value of that file."""
    for relation in all_relations():
        assert relation.mechanism, relation.id
        assert len(relation.mechanism.split()) > 15, f"{relation.id}: mechanism is too thin"


def test_every_relation_actually_crosses_domains():
    """A relation whose legs sit in one domain is a pack rule wearing the
    wrong hat."""
    for relation in all_relations():
        assert len(relation.domains) >= 2, relation.id


def test_relation_ids_are_unique():
    ids = [r.id for r in all_relations()]
    assert len(set(ids)) == len(ids)


def test_delayed_relations_say_so():
    """Pipeline weakness reaches cash a quarter later. A relation that treats
    a lagged link as simultaneous will keep diagnosing the wrong cause."""
    lagged = next(r for r in all_relations() if r.id == "thin_pipeline_precedes_thin_cash")
    assert lagged.lag_note, "a lagged relation must declare its lag"


def test_a_relation_without_a_mechanism_is_refused():
    from aether.business.relations import _relation_from

    with pytest.raises(ValueError, match="mechanism"):
        _relation_from(
            {
                "id": "x",
                "label": "x",
                "confidence": "strong",
                "legs": [
                    {"domain": "a", "metric": "m"},
                    {"domain": "b", "metric": "n"},
                ],
            }
        )


def test_a_one_legged_relation_is_refused():
    from aether.business.relations import _relation_from

    with pytest.raises(ValueError, match="two legs"):
        _relation_from(
            {
                "id": "x",
                "label": "x",
                "confidence": "strong",
                "mechanism": "a mechanism long enough to pass the length check here",
                "legs": [{"domain": "a", "metric": "m"}],
            }
        )


# ── Unvalidated claims stay silent ────────────────────────────────────────────


def test_a_plausible_relation_never_reaches_a_customer():
    """The property that makes it honest to write down a hypothesis before
    anyone has tested it against a real company."""
    whole = state(
        snapshot("sales_pipeline", metrics={"win_rate": 0.09}, drifting=("win_rate",)),
        snapshot("receivables", metrics={"dso_days": 74.0}, drifting=("dso_days",)),
    )

    assert active(whole) == [], "an unvalidated hypothesis spoke"

    also_silent = active(whole, include_silent=True)
    assert [a.id for a in also_silent] == ["pressure_to_close_buys_worse_terms"], (
        "and it should still be matchable, so it can be checked against real data"
    )


def test_confidence_tiers_know_whether_they_may_speak():
    assert Confidence.mechanical.speaks is True
    assert Confidence.strong.speaks is True
    assert Confidence.plausible.speaks is False


# ── Matching ──────────────────────────────────────────────────────────────────


def test_the_headline_case_fires():
    """Collections slowing while cash tightens — the case this whole phase
    exists for."""
    whole = state(
        snapshot("receivables", metrics={"dso_days": 68.0}, drifting=("dso_days",)),
        snapshot("cash_runway", metrics={"runway_months": 4.1}, drifting=("runway_months",)),
    )

    found = active(whole)
    ids = [a.id for a in found]
    assert "collections_slowing_drains_cash" in ids
    assert set(found[0].domains) == {"receivables", "cash_runway"}


def test_an_active_relation_carries_the_readings_that_triggered_it():
    """So an explanation can quote the actual numbers rather than asserting
    that something happened."""
    whole = state(
        snapshot("receivables", metrics={"dso_days": 68.0}, drifting=("dso_days",)),
        snapshot("cash_runway", metrics={"runway_months": 4.1}, drifting=("runway_months",)),
    )
    found = next(a for a in active(whole) if a.id == "collections_slowing_drains_cash")

    assert found.values["receivables.dso_days"] == 68.0
    assert found.values["cash_runway.runway_months"] == 4.1


def test_every_leg_must_hold():
    """These are conjunctions. A partial match is not a weaker version of the
    claim, it is a different claim."""
    only_one_leg = state(
        snapshot("receivables", metrics={"dso_days": 68.0}, drifting=("dso_days",)),
        snapshot("cash_runway", metrics={"runway_months": 11.0}),
    )
    assert [a.id for a in active(only_one_leg)] == []


def test_a_missing_domain_cannot_satisfy_a_relation():
    """A tenant who does not report cash cannot have a cash finding, however
    bad their receivables look."""
    receivables_only = state(
        snapshot("receivables", metrics={"dso_days": 68.0}, drifting=("dso_days",))
    )
    assert active(receivables_only) == []


def test_stale_data_cannot_join_a_relation():
    """Joining a current cash position to a six-week-old receivables reading
    would invent a story out of an absence."""
    whole = state(
        snapshot(
            "receivables",
            metrics={"dso_days": 68.0},
            drifting=("dso_days",),
            age_hours=2000.0,
            max_age_hours=192.0,
        ),
        snapshot("cash_runway", metrics={"runway_months": 4.1}, drifting=("runway_months",)),
    )
    assert active(whole) == []


def test_good_news_never_fires_a_relation():
    """Drift is asymmetric by design — a business whose DSO halves has not
    developed a problem — and a relation keyed on drift inherits that. Worth
    pinning, because the day it stops being true the product starts alarming
    people for improving."""
    improving = state(
        snapshot("receivables", metrics={"dso_days": 21.0}, health={"dso_days": 1.0}),
        snapshot("cash_runway", metrics={"runway_months": 18.0}, health={"runway_months": 1.0}),
    )
    assert active(improving) == []


# ── Leg states ────────────────────────────────────────────────────────────────


def test_an_unhealthy_leg_does_not_require_movement():
    """Chronic problems are still problems. A book 40% overdue for a year is
    not drifting, and is very much why cash is short."""
    chronic = state(
        snapshot("receivables", metrics={"overdue_ratio": 0.44}, health={"overdue_ratio": 0.1}),
        snapshot(
            "cash_runway",
            metrics={"obligation_coverage": 0.82},
            health={"obligation_coverage": 0.2},
        ),
    )
    assert "overdue_book_uncovers_obligations" in [a.id for a in active(chronic)]


def test_a_drifting_leg_is_not_satisfied_by_being_merely_unhealthy():
    """`state: drifting` asks whether something moved. A metric that has been
    bad forever has not."""
    leg_state = LegState.drifting
    chronic_but_still = snapshot(
        "receivables", metrics={"dso_days": 80.0}, health={"dso_days": 0.1}
    )
    from aether.business.relations import Leg

    assert Leg("receivables", "dso_days", leg_state).holds(chronic_but_still) is False
    assert Leg("receivables", "dso_days", LegState.unhealthy).holds(chronic_but_still) is True
    assert Leg("receivables", "dso_days", LegState.either).holds(chronic_but_still) is True


def test_a_metric_the_reading_never_carried_does_not_hold():
    from aether.business.relations import Leg

    bare = snapshot("receivables", metrics={"dso_days": 41.0})
    assert Leg("receivables", "dso_days", LegState.either).holds(bare) is False


# ── Ordering ──────────────────────────────────────────────────────────────────


def test_stronger_claims_come_first():
    """An arithmetic identity outranks a causal story, so whatever consumes
    this list leads with the thing least likely to be coincidence."""
    everything = state(
        snapshot(
            "receivables",
            metrics={"dso_days": 68.0, "overdue_ratio": 0.44},
            drifting=("dso_days",),
            health={"overdue_ratio": 0.1},
        ),
        snapshot(
            "cash_runway",
            metrics={"runway_months": 4.1, "obligation_coverage": 0.82},
            drifting=("runway_months",),
            health={"obligation_coverage": 0.2},
        ),
    )
    found = active(everything)
    assert len(found) >= 2
    assert found[0].relation.confidence is Confidence.mechanical


def test_an_empty_business_produces_nothing():
    assert active(BusinessState(tenant_id=uuid.uuid4(), captured_at=utcnow())) == []


def test_relations_serialise_for_a_prompt_or_an_api():
    whole = state(
        snapshot("receivables", metrics={"dso_days": 68.0}, drifting=("dso_days",)),
        snapshot("cash_runway", metrics={"runway_months": 4.1}, drifting=("runway_months",)),
    )
    payload = active(whole)[0].as_dict()

    assert payload["confidence"] in {"mechanical", "strong"}
    assert "mechanism" in payload and payload["mechanism"]
    assert "\n" not in payload["mechanism"], "folded YAML should arrive as one line"
    assert set(payload["domains"]) == {"receivables", "cash_runway"}


def test_relation_dataclass_is_hashable_and_frozen():
    """These are configuration, loaded once and shared. Mutating one at
    runtime would change every business's reasoning at the same time."""
    relation = all_relations()[0]
    assert isinstance(relation, Relation)
    with pytest.raises(dataclasses.FrozenInstanceError):
        relation.id = "changed"  # type: ignore[misc]
