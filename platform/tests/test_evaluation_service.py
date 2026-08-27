"""The shared decision-loop service, against live Postgres.

This is the exact code path the autonomous Temporal worker executes, tested
without needing Temporal itself: activities are thin shells around this.
"""

import datetime
import uuid

import pytest
import sqlalchemy
from sqlalchemy import select, text

from aether.core.db import get_engine, tenant_session
from aether.core.models import AuditLog, PendingApproval, PolicyConfig
from aether.services.evaluation import (
    evaluate_domain,
    record_observation,
)

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


def test_no_data_outcome(tenant):
    out = evaluate_domain(tenant, "churn", triggered_by="test")
    assert out.status == "no_data"
    assert out.decision is None


def test_autonomous_run_uses_latest_observation_and_gates_high_risk(tenant):
    record_observation(tenant, "churn", drift_fraction=0.1, performance=0.95, source="old")
    obs_id = record_observation(tenant, "churn", drift_fraction=0.7, performance=0.4)

    out = evaluate_domain(tenant, "churn", triggered_by="nano-monitor:churn")
    assert out.status == "evaluated"
    assert out.observation_id == obs_id  # newest wins
    assert out.decision is not None
    # No pack for this domain, so the generic vocabulary applies.
    assert out.decision["action"] == "INTERVENE"
    assert out.decision["slot"] == "intervene"
    assert out.approval_id is not None

    with tenant_session(tenant) as db:
        approval = db.get(PendingApproval, out.approval_id)
        assert approval is not None and approval.status.value == "pending"
        log = db.scalars(select(AuditLog).where(AuditLog.domain == "churn")).all()
        assert len(log) == 1
        assert log[0].triggered_by == "nano-monitor:churn"
        assert log[0].status == "pending"


def test_stale_observation_refused(tenant):
    old = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=3)
    record_observation(tenant, "churn", drift_fraction=0.9, performance=0.2, observed_at=old)
    out = evaluate_domain(tenant, "churn", triggered_by="nano-monitor:churn")
    assert out.status == "stale_data"
    assert out.decision is None  # no decision, no audit spam on dead telemetry


def test_tenant_policy_changes_autonomous_decision(tenant):
    record_observation(tenant, "sales", drift_fraction=0.7, performance=0.4)
    with tenant_session(tenant) as db:
        db.add(
            PolicyConfig(
                tenant_id=tenant,
                domain="sales",
                params={"perf_threshold": 0.3, "drift_threshold": 0.9},
            )
        )
    out = evaluate_domain(tenant, "sales", triggered_by="test")
    assert out.status == "evaluated"
    assert out.decision is not None
    assert out.decision["action"] == "NO_ACTION"  # lenient policy, same inputs


def test_explicit_values_bypass_observations(tenant):
    out = evaluate_domain(tenant, "fresh", triggered_by="test", drift_fraction=0.2, performance=0.9)
    assert out.status == "evaluated"
    assert out.observation_id is None
