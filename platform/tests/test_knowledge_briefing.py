"""What a business decided last time, on its way into a prompt.

No database, no embedding model — this decides what to ask for and turns the
answer into a string, and both are readable without infrastructure.

The failures worth catching are all quiet ones. The query could drift out of
the shape the memories were written in, and silently match nothing. The
decision being explained could be recalled as precedent for itself. The
instructions could let the model say a past decision helped, which nothing
records and everyone would believe.
"""

import datetime
import uuid

import pytest

from aether.core.models import ApprovalStatus, PendingApproval
from aether.knowledge import briefing, history, retrieval, store

WHEN = datetime.datetime(2026, 3, 9, tzinfo=datetime.UTC)
TENANT = uuid.uuid4()


def approval(**overrides) -> PendingApproval:
    """An approval that never sees a session, so defaults are set by hand."""
    fields = {
        "id": uuid.uuid4(),
        "tenant_id": TENANT,
        "created_at": WHEN,
        "domain": "receivables",
        "action": "ESCALATE_COLLECTIONS",
        "reason": "34% of 400,000 outstanding, carried at 15% a year.",
        "risk_level": "HIGH",
        "expected_loss_usd": 147.0,
        "status": ApprovalStatus.pending,
    }
    fields.update(overrides)
    return PendingApproval(**fields)


def recollection(body: str, *, when: datetime.datetime = WHEN) -> retrieval.Recollection:
    return retrieval.Recollection(
        memory=store.Memory(
            id=uuid.uuid4(),
            kind=history.KIND_DECISION,
            body=body,
            occurred_at=when,
            domain="receivables",
            distance=0.31,
        ),
        standout=True,
    )


REMEMBERED = [
    recollection(
        "September 2025, Cash & Receivables: the agent recommended escalate "
        "collections at HIGH risk, with $132.00 a day at risk, and it was approved."
    ),
    recollection(
        "January 2026, Cash & Runway: the agent recommended defer discretionary "
        "spend at HIGH risk, with $95.00 a day at risk, and it was declined."
    ),
]


@pytest.fixture
def asked(monkeypatch) -> dict:
    """Capture what gets asked of the knowledge base, and answer with nothing."""
    captured: dict = {}

    def fake(tenant_id, question, **kwargs):
        captured.update(tenant_id=tenant_id, question=question, **kwargs)
        return []

    monkeypatch.setattr(briefing.retrieval, "worth_quoting", fake)
    return captured


# ── What gets asked ───────────────────────────────────────────────────────────


def test_the_question_is_written_in_the_same_shape_as_the_memories(asked):
    """This model matches near-duplicates and little else, so a free-form
    question would miss memories describing the same situation in other words.
    The query is produced by the template that produced the store."""
    a = approval()
    briefing.prior_decisions(TENANT, a)

    assert asked["question"] == history.describe(a)


def test_the_decision_being_explained_is_never_precedent_for_itself(asked):
    """A backfill indexes pending approvals too, so without this the nearest
    memory to a decision is reliably that same decision."""
    a = approval()
    briefing.prior_decisions(TENANT, a)

    assert asked["exclude_source_id"] == a.id
    assert asked["before"] == a.created_at


def test_only_past_decisions_are_recalled_not_every_kind_of_knowledge(asked):
    """Sector reference material will live in the same table (Phase 3.4).
    Quoting it as something this business decided would be a lie."""
    briefing.prior_decisions(TENANT, approval())
    assert asked["kind"] == history.KIND_DECISION


def test_enough_candidates_are_asked_for_that_standing_out_means_something(asked):
    """`standout` compares against a median. Over two or three rows that
    comparison is noise, and cheap to avoid — only standouts are rendered, so
    the extra candidates cost nothing downstream."""
    briefing.prior_decisions(TENANT, approval())
    assert asked["limit"] >= 6


# ── What comes back ───────────────────────────────────────────────────────────


def test_recalled_decisions_are_labelled_as_this_business_own_past():
    block = briefing.context_block(REMEMBERED)

    assert "its own past decisions" in block
    assert "not general advice" in block
    for r in REMEMBERED:
        assert r.body in block


def test_nothing_recalled_adds_nothing_to_the_prompt():
    assert briefing.context_block([]) == ""
    assert briefing.extra_instructions([]) == ""


def test_the_model_is_forbidden_from_claiming_the_past_worked():
    """Outcomes are not tracked (Phase 9). An explanation asserting that last
    September's escalation helped would be inventing its own best evidence."""
    said = briefing.extra_instructions(REMEMBERED)

    assert "Do NOT" in said
    for claim in ("worked", "helped", "fixed", "caused"):
        assert claim in said


def test_an_irrelevant_recollection_may_be_dropped_by_the_model():
    """Retrieval is a filter, not a judgement. The last word on relevance
    belongs to the thing that can read both."""
    assert "does not fit" in briefing.extra_instructions(REMEMBERED)


# ── Failing quietly ───────────────────────────────────────────────────────────


def test_nothing_standing_out_costs_the_prompt_nothing(asked):
    assert briefing.for_approval(TENANT, approval()) == ("", "")


def test_a_broken_knowledge_base_costs_a_sentence_not_the_diagnosis(monkeypatch):
    """Memory is an enhancement to an explanation, never a precondition for
    one. An approver waiting on a decision should not lose their explanation
    because a vector search fell over."""

    def boom(*_args, **_kwargs):
        raise RuntimeError("pgvector is having a day")

    monkeypatch.setattr(briefing.retrieval, "worth_quoting", boom)
    assert briefing.for_approval(TENANT, approval()) == ("", "")


def test_recall_is_reached_through_worth_quoting_rather_than_raw_search(monkeypatch):
    """The gate is the whole point. `search` always returns the closest thing
    this business remembers, which is always something."""

    def forbidden(*_args, **_kwargs):
        raise AssertionError("unfiltered search must never reach a customer")

    monkeypatch.setattr(briefing.retrieval, "search", forbidden)
    monkeypatch.setattr(briefing.retrieval, "worth_quoting", lambda *a, **k: REMEMBERED)

    instructions, context = briefing.for_approval(TENANT, approval())
    assert instructions and context
