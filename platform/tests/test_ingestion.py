"""Ingestion end to end: gate, quarantine, baseline, and the decision that follows.

Requires the dev database (docker compose up -d db + alembic upgrade head).
"""

import datetime
import uuid

import pytest
import sqlalchemy
from sqlalchemy import select, text

from aether.core.db import get_engine, tenant_session
from aether.core.models import Observation
from aether.services.evaluation import evaluate_domain
from aether.services.ingestion import ingest_reading

pytestmark = pytest.mark.postgres


HEALTHY = {
    "dso_days": 36.0,
    "overdue_ratio": 0.11,
    "avg_days_past_due": 8.0,
    "collection_effectiveness": 0.88,
    "top5_concentration": 0.35,
    "disputed_ratio": 0.01,
    "ar_total": 260_000.0,
    "invoice_count": 190,
}


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


def test_clean_reading_is_accepted_and_derived(tenant):
    result = ingest_reading(tenant, "receivables", HEALTHY, source="pytest")
    assert result.accepted
    assert result.performance is not None and result.performance > 0.9
    assert result.drift_fraction == 0.0  # no baseline yet
    assert result.baseline_used is False

    with tenant_session(tenant) as db:
        obs = db.get(Observation, result.observation_id)
        assert obs.status == "accepted"
        assert obs.metrics["dso_days"] == 36.0  # raw values retained


def test_bad_reading_is_quarantined_not_dropped(tenant):
    """A rejected reading must stay visible with its reason attached."""
    result = ingest_reading(tenant, "receivables", {**HEALTHY, "overdue_ratio": 45.0})
    assert not result.accepted
    assert any(i.code == "above_maximum" for i in result.quality.errors)

    with tenant_session(tenant) as db:
        obs = db.get(Observation, result.observation_id)
        assert obs is not None, "quarantined readings must be kept, not discarded"
        assert obs.status == "quarantined"
        assert obs.issues["issues"]


def test_quarantined_reading_never_reaches_a_decision(tenant):
    ingest_reading(tenant, "receivables", HEALTHY)
    # A wildly bad reading that fails the gate must not influence anything.
    ingest_reading(
        tenant,
        "receivables",
        {**HEALTHY, "dso_days": 5000.0, "overdue_ratio": 0.99},
        observed_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=5),
    )

    outcome = evaluate_domain(tenant, "receivables", triggered_by="pytest")
    assert outcome.status == "evaluated"
    assert outcome.decision is not None
    # The healthy reading is the newest *accepted* one, so no action.
    assert outcome.decision["action"] == "NO_ACTION"


def test_baseline_forms_from_accepted_history_then_detects_drift(tenant):
    base = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=40)
    for i in range(6):
        ingest_reading(
            tenant,
            "receivables",
            HEALTHY,
            observed_at=base + datetime.timedelta(days=i),
        )

    slipped = {**HEALTHY, "dso_days": 78.0}
    result = ingest_reading(
        tenant, "receivables", slipped, observed_at=base + datetime.timedelta(days=7)
    )

    assert result.accepted
    assert result.baseline_used is True
    assert result.drift_fraction and result.drift_fraction > 0


def test_decision_uses_business_economics(tenant):
    """Exposure comes from the actual book, so the dollar figure is real."""
    deteriorated = {
        **HEALTHY,
        "dso_days": 96.0,
        "overdue_ratio": 0.46,
        "avg_days_past_due": 62.0,
        "collection_effectiveness": 0.5,
        "ar_total": 800_000.0,
    }
    ingest_reading(tenant, "receivables", deteriorated)

    outcome = evaluate_domain(tenant, "receivables", triggered_by="pytest")
    assert outcome.status == "evaluated"
    decision = outcome.decision
    assert decision is not None
    assert decision["action"] == "ESCALATE_COLLECTIONS"
    assert decision["requires_approval"] is True
    assert outcome.approval_id is not None

    expected = 800_000.0 * 0.46 * 0.0004
    assert decision["expected_daily_loss"] == pytest.approx(expected, rel=0.01)
    assert "outstanding" in decision["inputs"]["loss_basis"]


def test_receivables_tolerates_a_week_old_reading(tenant):
    """Domain freshness beats the global default: AR is reported weekly."""
    five_days_ago = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=5)
    ingest_reading(tenant, "receivables", HEALTHY, observed_at=five_days_ago)

    outcome = evaluate_domain(tenant, "receivables", triggered_by="pytest")
    assert outcome.status == "evaluated"  # would be stale_data under the 24h default


def test_reading_for_domain_without_a_pack_is_refused(tenant):
    with pytest.raises(ValueError, match="No domain pack"):
        ingest_reading(tenant, "no-such-domain", {"anything": 1.0})


def test_readings_are_tenant_isolated(db_available):
    a, b = uuid.uuid4(), uuid.uuid4()
    ingest_reading(a, "receivables", HEALTHY, source="tenant-a")

    with tenant_session(b) as db:
        rows = db.scalars(select(Observation).where(Observation.domain == "receivables")).all()
        assert all(r.source != "tenant-a" for r in rows)


def test_quarantined_readings_are_absent_from_the_diagnosis(tenant):
    """A rejected reading must not distort the explanation either.

    Quarantined rows are stored with placeholder zeros. If the diagnosis reads
    them, the reported trend silently includes data the decision excluded —
    which breaks the guarantee the quarantine exists to make.
    """
    from aether.services.diagnosis import diagnose_approval

    ingest_reading(tenant, "receivables", HEALTHY)
    ingest_reading(tenant, "receivables", {**HEALTHY, "overdue_ratio": 42.0})  # rejected

    deteriorated = {
        **HEALTHY,
        "dso_days": 96.0,
        "overdue_ratio": 0.46,
        "avg_days_past_due": 62.0,
        "collection_effectiveness": 0.5,
        "ar_total": 800_000.0,
    }
    ingest_reading(
        tenant,
        "receivables",
        deteriorated,
        observed_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=1),
    )

    outcome = evaluate_domain(tenant, "receivables", triggered_by="pytest")
    assert outcome.approval_id is not None

    diagnose_approval(tenant, outcome.approval_id)

    with tenant_session(tenant) as db:
        from aether.core.models import PendingApproval

        approval = db.get(PendingApproval, outcome.approval_id)
        assert approval.diagnosis

        # Two accepted readings exist; the quarantined one must not be counted.
        if "readings, drift moved" in approval.diagnosis:
            assert "last 2 readings" in approval.diagnosis, approval.diagnosis
