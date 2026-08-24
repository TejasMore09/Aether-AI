"""THE test that matters: Postgres itself must refuse cross-tenant reads and
writes, regardless of application code.

Requires the dev database:  docker compose up -d db  +  alembic upgrade head
Run with:                   pytest -m postgres
Skipped automatically when the database is unreachable.
"""

import uuid

import pytest
import sqlalchemy
from sqlalchemy import select, text

from aether.core.db import get_engine, tenant_session
from aether.core.models import AuditLog

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def db_available():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except sqlalchemy.exc.OperationalError:
        pytest.skip("Postgres not reachable — start it with: docker compose up -d db")


@pytest.fixture
def two_tenants(db_available):
    """Two synthetic tenant ids with one audit row each, cleaned up after."""
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    marker = f"rls-test-{uuid.uuid4()}"
    for tid in (tenant_a, tenant_b):
        with tenant_session(tid) as db:
            db.add(
                AuditLog(
                    tenant_id=tid,
                    domain=marker,
                    action="TEST",
                    triggered_by="pytest",
                    risk_level="LOW",
                )
            )
    yield tenant_a, tenant_b, marker
    for tid in (tenant_a, tenant_b):
        with tenant_session(tid) as db:
            for row in db.scalars(select(AuditLog).where(AuditLog.domain == marker)):
                db.delete(row)


def test_tenant_sees_only_its_own_rows(two_tenants):
    tenant_a, tenant_b, marker = two_tenants
    with tenant_session(tenant_a) as db:
        rows = db.scalars(select(AuditLog).where(AuditLog.domain == marker)).all()
        assert len(rows) == 1
        assert rows[0].tenant_id == tenant_a  # tenant B's row is invisible


def test_cross_tenant_write_rejected_by_database(two_tenants):
    tenant_a, tenant_b, marker = two_tenants
    with pytest.raises(sqlalchemy.exc.ProgrammingError):
        # Session pinned to tenant A tries to forge a row for tenant B —
        # the RLS WITH CHECK clause must make Postgres refuse it.
        with tenant_session(tenant_a) as db:
            db.add(
                AuditLog(
                    tenant_id=tenant_b,
                    domain=marker,
                    action="FORGERY",
                    triggered_by="pytest",
                    risk_level="LOW",
                )
            )
            db.flush()


def test_no_tenant_context_sees_nothing(two_tenants):
    _, _, marker = two_tenants
    engine = get_engine()
    with engine.connect() as conn:
        # A connection that never set app.tenant_id: current_setting yields
        # an empty string whose uuid cast errors (DataError), or the policy
        # filters everything — either way, no data leaks.
        try:
            count = conn.execute(
                text("SELECT count(*) FROM audit_logs WHERE domain = :m"), {"m": marker}
            ).scalar()
            assert count == 0
        except sqlalchemy.exc.DBAPIError:
            pass  # unset GUC raising is equally acceptable — nothing leaked
