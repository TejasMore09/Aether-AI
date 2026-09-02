"""Diagnosis layer against live Postgres, with the LLM provider stubbed —
tests must be deterministic and never spend real tokens."""

import uuid
from types import SimpleNamespace

import pytest
import sqlalchemy
from sqlalchemy import select, text

from aether.core.db import get_engine, tenant_session
from aether.core.models import LLMUsage, PendingApproval
from aether.llm import gateway
from aether.services.diagnosis import diagnose_approval
from aether.services.evaluation import evaluate_domain, record_observation

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def db_available():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except sqlalchemy.exc.OperationalError:
        pytest.skip("Postgres not reachable — start it with: docker compose up -d db")


@pytest.fixture
def tenant(db_available):
    return uuid.uuid4()


@pytest.fixture
def gated_approval(tenant):
    """A HIGH-risk decision with its approval, produced by the real loop."""
    record_observation(tenant, "revenue", drift_fraction=0.3, performance=0.8)
    record_observation(tenant, "revenue", drift_fraction=0.7, performance=0.45)
    out = evaluate_domain(tenant, "revenue", triggered_by="test")
    assert out.approval_id is not None
    return out.approval_id


def _fake_litellm_response(text_out: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text_out))],
        usage=SimpleNamespace(prompt_tokens=120, completion_tokens=80),
    )


def test_llm_diagnosis_attached_and_metered(tenant, gated_approval, monkeypatch):
    import litellm

    captured: dict = {}

    def fake_completion(**kwargs):
        captured["messages"] = kwargs["messages"]
        return _fake_litellm_response("**Drift doubled while performance fell.** Verify pipeline.")

    monkeypatch.setattr(litellm, "completion", fake_completion)
    monkeypatch.setattr(litellm, "completion_cost", lambda completion_response: 0.0021)

    source = diagnose_approval(tenant, gated_approval)
    assert source == "llm"

    # Prompt was grounded in the tenant's real observations
    user_msg = captured["messages"][1]["content"]
    assert "drift=0.700" in user_msg and "drift=0.300" in user_msg

    with tenant_session(tenant) as db:
        approval = db.get(PendingApproval, gated_approval)
        assert approval.diagnosis_source == "llm"
        assert "Drift doubled" in approval.diagnosis
        usage = db.scalars(select(LLMUsage)).all()
        assert len(usage) == 1
        assert usage[0].purpose == "diagnosis"
        assert usage[0].cost_usd == pytest.approx(0.0021)


def test_diagnosis_idempotent_no_double_spend(tenant, gated_approval, monkeypatch):
    import litellm

    monkeypatch.setattr(litellm, "completion", lambda **kw: _fake_litellm_response("analysis"))
    monkeypatch.setattr(litellm, "completion_cost", lambda completion_response: 0.001)

    assert diagnose_approval(tenant, gated_approval) == "llm"
    assert diagnose_approval(tenant, gated_approval) == "skipped"  # retry-safe

    with tenant_session(tenant) as db:
        assert len(db.scalars(select(LLMUsage)).all()) == 1


def test_provider_failure_falls_back_deterministically(tenant, gated_approval, monkeypatch):
    import litellm

    def boom(**kwargs):
        raise ConnectionError("provider down")

    monkeypatch.setattr(litellm, "completion", boom)

    source = diagnose_approval(tenant, gated_approval)
    assert source == "fallback"

    with tenant_session(tenant) as db:
        approval = db.get(PendingApproval, gated_approval)
        assert approval.diagnosis_source == "fallback"
        assert "Automated summary" in approval.diagnosis
        assert f"${approval.expected_loss_usd:,.2f}" in approval.diagnosis
        assert db.scalars(select(LLMUsage)).all() == []  # failure costs nothing


def test_budget_exhaustion_denies_llm_and_falls_back(tenant, gated_approval, monkeypatch):
    import litellm

    with tenant_session(tenant) as db:
        db.add(
            LLMUsage(
                tenant_id=tenant,
                purpose="diagnosis",
                model="test",
                cost_usd=99.0,  # over any sane budget
            )
        )

    def must_not_be_called(**kwargs):
        raise AssertionError("provider called despite exhausted budget")

    monkeypatch.setattr(litellm, "completion", must_not_be_called)

    source = diagnose_approval(tenant, gated_approval)
    assert source == "fallback"


def test_budget_is_per_tenant(tenant, monkeypatch):
    """Another tenant's spend must not count against this tenant (RLS scope)."""
    other = uuid.uuid4()
    with tenant_session(other) as db:
        db.add(LLMUsage(tenant_id=other, purpose="diagnosis", model="t", cost_usd=99.0))
    assert gateway.month_spend_usd(tenant) == 0.0


def test_a_truncated_answer_falls_back_rather_than_being_shown(tenant, gated_approval, monkeypatch):
    """The failure a stub cannot produce, found the first time a real model ran.

    Reasoning models spend the output budget thinking before they write
    anything visible. At the old cap of 700, gemini-3.6-flash used 668 tokens
    on reasoning and emitted 116 characters before being cut off mid-number —
    and nothing raised, `text` was not empty, so it was stored and shown. A
    plain explanation that finishes beats an eloquent one that stops.
    """
    import litellm

    def truncated(**kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="**Connected Problem** With $62,000"),
                    finish_reason="length",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=900, completion_tokens=700),
        )

    monkeypatch.setattr(litellm, "completion", truncated)
    monkeypatch.setattr(litellm, "completion_cost", lambda completion_response: 0.0004)

    assert diagnose_approval(tenant, gated_approval) == "fallback"

    with tenant_session(tenant) as db:
        approval = db.get(PendingApproval, gated_approval)
        assert "Automated summary" in approval.diagnosis
        assert "With $62,000" not in approval.diagnosis
        # Metered regardless: the tokens were spent whether or not we used them.
        assert db.scalars(select(LLMUsage)).all()


def test_the_prompt_carries_what_this_business_decided_last_time(
    tenant, gated_approval, monkeypatch
):
    """The point of Phase 2: an approver should be reminded that this has come
    up before, rather than left to remember it themselves.

    The knowledge base is stubbed here — whether retrieval finds the right
    memory is settled in the knowledge tests, and what matters at this seam is
    that a found memory reaches the model, labelled as this business's own
    past and fenced against claims about how it turned out.
    """
    import litellm

    from aether.knowledge import briefing as knowledge_briefing

    remembered = "September 2025, Cash & Receivables: the agent recommended escalate collections."
    monkeypatch.setattr(
        knowledge_briefing,
        "prior_decisions",
        lambda *a, **k: [
            SimpleNamespace(body=remembered, standout=True),
        ],
    )

    captured: dict = {}

    def fake_completion(**kwargs):
        captured["messages"] = kwargs["messages"]
        return _fake_litellm_response("Explanation.")

    monkeypatch.setattr(litellm, "completion", fake_completion)
    monkeypatch.setattr(litellm, "completion_cost", lambda completion_response: 0.0)

    assert diagnose_approval(tenant, gated_approval) == "llm"

    user_msg = captured["messages"][1]["content"]
    assert remembered in user_msg
    assert "its own past decisions" in user_msg
    assert "Do NOT" in user_msg


def test_a_failing_knowledge_base_does_not_cost_the_approver_an_explanation(
    tenant, gated_approval, monkeypatch
):
    import litellm

    from aether.knowledge import briefing as knowledge_briefing

    def boom(*_a, **_k):
        raise RuntimeError("vector search down")

    monkeypatch.setattr(knowledge_briefing, "prior_decisions", boom)
    monkeypatch.setattr(litellm, "completion", lambda **kw: _fake_litellm_response("Explanation."))
    monkeypatch.setattr(litellm, "completion_cost", lambda completion_response: 0.0)

    assert diagnose_approval(tenant, gated_approval) == "llm"
