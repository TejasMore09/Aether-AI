"""The whole-business context handed to a diagnosis prompt.

No database, no LLM — this builds a string, and a string can be read.

Two failures matter here. The prompt could stay silent about a connection the
engine already found, which wastes the whole of Phase 1. Or it could hand the
model two exposure figures without saying they are the same money, and get an
explanation that contradicts the decision it is explaining.
"""

import datetime
import uuid

from aether.business.briefing import context_block, extra_instructions, relevant_domains
from aether.business.findings import for_business
from aether.business.state import BusinessState, DomainSnapshot, utcnow
from aether.policy.decision_engine import PolicyParams

RECEIVABLES = {
    "dso_days": 68.0,
    "overdue_ratio": 0.34,
    "ar_total": 400_000.0,
}
CASH = {
    "runway_months": 4.1,
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
    label: str | None = None,
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
        label=label or domain,
        observed_at=utcnow() - datetime.timedelta(hours=1),
        performance=performance,
        drift_fraction=0.5,
        metrics=metrics,
        per_metric=per_metric,
        params=PolicyParams(perf_threshold=perf_threshold),
    )


def slowing_business(**extra: DomainSnapshot) -> BusinessState:
    domains = {
        "receivables": snapshot(
            "receivables",
            RECEIVABLES,
            drifting=("dso_days",),
            health={"overdue_ratio": 0.1},
            label="Cash & Receivables",
        ),
        "cash_runway": snapshot(
            "cash_runway",
            CASH,
            drifting=("runway_months",),
            health={"obligation_coverage": 0.2},
            performance=0.30,
            perf_threshold=0.90,
            label="Cash & Runway",
        ),
    }
    domains.update(extra)
    return BusinessState(tenant_id=uuid.uuid4(), captured_at=utcnow(), domains=domains)


def block_for(focus: str, state: BusinessState | None = None) -> str:
    whole = state or slowing_business()
    return context_block(whole, focus, tuple(for_business(whole)))


# ── The arithmetic must be stated, not implied ────────────────────────────────


def test_the_prompt_forbids_adding_the_two_exposures():
    """A model handed two figures will add them. That would contradict the
    engine's own number inside the explanation of the engine's own decision."""
    block = block_for("receivables")

    assert "LARGEST single" in block
    assert "Never add them together" in block
    assert "same money from two sides" in block


def test_the_combined_figure_is_the_findings_own_number():
    state = slowing_business()
    finding = next(f for f in for_business(state) if "receivables" in f.domains)
    block = context_block(state, "receivables", tuple(for_business(state)))

    assert f"${finding.daily_amount:,.2f}" in block


# ── The connection is actually surfaced ───────────────────────────────────────


def test_the_connected_domain_appears_with_its_readings():
    block = block_for("receivables")

    assert "cash_runway" in block
    assert "runway_months=4.1" in block


def test_the_mechanism_is_handed_over_rather_than_left_to_be_inferred():
    block = block_for("receivables")
    assert "Mechanism:" in block
    assert len(block.split("Mechanism:")[1].split("\n")[0].split()) > 10


def test_the_instructions_tell_it_to_lead_with_the_connection():
    state = slowing_business()
    instructions = extra_instructions(tuple(for_business(state)), "receivables")

    assert instructions
    assert "Lead with the connection" in instructions
    assert "separate issues" in instructions


def test_a_domain_with_no_connection_gets_no_extra_instructions():
    state = slowing_business()
    assert extra_instructions(tuple(for_business(state)), "sales_pipeline") == ""


def test_a_lagged_relation_carries_its_timing_into_the_prompt():
    """Otherwise the model presents a diagnosis as a warning, or the reverse."""
    state = slowing_business(
        sales_pipeline=snapshot(
            "sales_pipeline",
            {"pipeline_coverage": 1.6, "pipeline_value": 800_000.0, "stalled_ratio": 0.45},
            health={"pipeline_coverage": 0.2},
            perf_threshold=0.92,
        )
    )
    block = context_block(state, "cash_runway", tuple(for_business(state)))
    assert "Timing:" in block


# ── Economy ───────────────────────────────────────────────────────────────────


def test_a_healthy_unconnected_domain_is_left_out():
    """Tokens are metered against a real per-tenant budget, and a healthy
    unrelated domain teaches the model nothing."""
    state = slowing_business(
        sales_pipeline=snapshot(
            "sales_pipeline",
            {"pipeline_coverage": 4.5, "win_rate": 0.34},
            health={"pipeline_coverage": 1.0},
            performance=0.99,
            perf_threshold=0.92,
        )
    )
    assert "sales_pipeline" not in context_block(state, "receivables", tuple(for_business(state)))


def test_an_impaired_unconnected_domain_is_included():
    """Not part of the story, but an approver deciding about collections
    should know the pipeline is also struggling."""
    state = slowing_business(
        sales_pipeline=snapshot(
            "sales_pipeline",
            {"pipeline_coverage": 1.4, "win_rate": 0.05},
            health={"pipeline_coverage": 0.1},
            performance=0.12,
            perf_threshold=0.92,
        )
    )
    assert "sales_pipeline" in context_block(state, "receivables", tuple(for_business(state)))


def test_connected_domains_are_named_before_merely_impaired_ones():
    state = slowing_business(
        sales_pipeline=snapshot(
            "sales_pipeline",
            {"pipeline_coverage": 1.4},
            health={"pipeline_coverage": 0.1},
            performance=0.12,
            perf_threshold=0.92,
        )
    )
    ordering = relevant_domains(state, "receivables", tuple(for_business(state)))
    assert ordering[0] == "cash_runway"


def test_a_domain_is_never_listed_as_context_for_itself():
    assert relevant_domains(slowing_business(), "receivables", ()) == ["cash_runway"]
    state = slowing_business()
    assert "receivables" not in relevant_domains(state, "receivables", tuple(for_business(state)))


def test_a_business_with_nothing_to_add_produces_no_block():
    """Silence rather than an empty heading. A block saying nothing still
    costs tokens and still invites the model to fill it."""
    lone = BusinessState(
        tenant_id=uuid.uuid4(),
        captured_at=utcnow(),
        domains={
            "receivables": snapshot(
                "receivables", RECEIVABLES, health={"dso_days": 1.0}, performance=0.99
            )
        },
    )
    assert context_block(lone, "receivables", tuple(for_business(lone))) == ""


# ── Honesty about what is missing ─────────────────────────────────────────────


def test_silent_domains_are_named_with_a_warning_not_to_read_into_them():
    state = slowing_business()
    whole = BusinessState(
        tenant_id=state.tenant_id,
        captured_at=state.captured_at,
        domains=state.domains,
        silent=("sales_pipeline",),
    )
    block = context_block(whole, "receivables", tuple(for_business(whole)))

    assert "reporting nothing" in block
    assert "Do not infer anything" in block


def test_corroborating_history_is_offered_when_it_exists():
    from aether.business.correlation import CoMovement

    state = slowing_business()
    supported = tuple(
        for_business(
            state,
            (
                CoMovement(
                    "receivables",
                    "dso_days",
                    "cash_runway",
                    "runway_months",
                    rho=-0.84,
                    pairs=11,
                    corroborates="collections_slowing_drains_cash",
                ),
            ),
        )
    )
    block = context_block(state, "receivables", supported)
    assert "own history supports it" in block


def test_the_block_ends_cleanly_so_it_can_be_concatenated():
    assert block_for("receivables").endswith("\n\n")
