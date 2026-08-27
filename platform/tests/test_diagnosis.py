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
