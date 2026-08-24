"""Notification service + usage endpoint against live Postgres, SMTP stubbed."""

import uuid

import pytest
import sqlalchemy
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from aether.core.db import get_engine, tenant_session
from aether.core.models import LLMUsage, Notification
from aether.services import notifications
from aether.services.evaluation import evaluate_domain, record_observation

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def cp_client():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except sqlalchemy.exc.OperationalError:
        pytest.skip("Postgres not reachable — start it with: docker compose up -d db")
    from aether.control_plane.app import app

    return TestClient(app)


@pytest.fixture
def org(cp_client):
    """Real org with a real owner, so recipient resolution is exercised."""
    slug = f"ntf-{uuid.uuid4().hex[:10]}"
    email = f"owner-{slug}@aethertest.io"
    r = cp_client.post(
        "/v1/auth/signup",
        json={
            "org_name": "Notify Org",
            "org_slug": slug,
            "email": email,
            "password": "long-enough-password",
        },
    )
    assert r.status_code == 201, r.text
    return uuid.UUID(r.json()["tenant_id"]), email, r.json()["access_token"]


@pytest.fixture
def gated_approval(org):
    tenant_id, _, _ = org
    record_observation(tenant_id, "revenue", drift_fraction=0.7, performance=0.4)
    out = evaluate_domain(tenant_id, "revenue", triggered_by="test")
    assert out.approval_id is not None
    return out.approval_id


def test_unconfigured_smtp_records_skip_not_silence(org, gated_approval):
    tenant_id, owner_email, _ = org
    result = notifications.notify_approval_created(tenant_id, gated_approval)
    assert result["recipients"] == 1
    assert result["notified"] == 0  # nothing sent — but nothing lost either

    with tenant_session(tenant_id) as db:
        rows = db.scalars(select(Notification)).all()
        assert len(rows) == 1
        assert rows[0].recipient == owner_email
        assert rows[0].status == "skipped_unconfigured"
        assert rows[0].ref_id == gated_approval


def test_configured_smtp_sends_and_is_idempotent(org, gated_approval, monkeypatch):
    tenant_id, owner_email, _ = org
    sent: list[tuple] = []

    monkeypatch.setattr(
        notifications, "_send_email", lambda r, s, b: (sent.append((r, s, b)), ("sent", ""))[1]
    )

    result = notifications.notify_approval_created(tenant_id, gated_approval)
    assert result["notified"] == 1
    assert sent[0][0] == owner_email
    assert "awaiting approval" in sent[0][1]
    assert "revenue" in sent[0][2]

    # Second run: owner already notified — no duplicate email
    result2 = notifications.notify_approval_created(tenant_id, gated_approval)
    assert result2["recipients"] == 0
    assert len(sent) == 1


def test_missing_approval_is_contained(org):
    tenant_id, _, _ = org
    result = notifications.notify_approval_created(tenant_id, uuid.uuid4())
    assert result == {"notified": 0, "reason": "approval_not_found"}


def test_usage_endpoint_reports_spend_against_budget(org):
    tenant_id, _, token = org
    with tenant_session(tenant_id) as db:
        db.add(
            LLMUsage(
                tenant_id=tenant_id,
                purpose="diagnosis",
                model="test-model",
                prompt_tokens=100,
                completion_tokens=200,
                cost_usd=0.01,
            )
        )

    from aether.agent_runtime.app import app

    rt = TestClient(app)
    r = rt.get("/v1/usage/llm", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["month_spend_usd"] == pytest.approx(0.01)
    assert body["budget_remaining_usd"] == pytest.approx(body["monthly_budget_usd"] - 0.01)
    assert body["by_purpose"]["diagnosis"]["calls"] == 1
    assert body["by_purpose"]["diagnosis"]["tokens"] == 300
