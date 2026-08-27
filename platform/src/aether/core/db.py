"""Database access with tenant-scoped sessions.

Row-Level Security model: every tenant-owned table carries a tenant_id column
and a Postgres RLS policy of the form

    USING (tenant_id = current_setting('app.tenant_id')::uuid)

The application connects as a NON-superuser role, so policies are enforced by
the database itself — a bug in application code cannot read another tenant's
rows. tenant_session() sets the GUC for the transaction; plain session() is
for control-plane tables (tenants, users) that are not tenant-scoped.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from aether.core.config import get_settings

_engine = None
_SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        # connect_timeout: an unreachable database must fail fast (seconds),
        # never hang a request or a test run waiting on TCP.
        _engine = create_engine(
            get_settings().database_url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 5},
        )
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def _session_factory() -> sessionmaker:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


@contextmanager
def session() -> Iterator[Session]:
    """Un-scoped session for control-plane (non-tenant) tables."""
    db = _session_factory()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def tenant_session(tenant_id: uuid.UUID) -> Iterator[Session]:
    """Session whose transaction is pinned to one tenant via the RLS GUC.

    SET LOCAL scopes the setting to the transaction, so pooled connections
    never leak a tenant id to the next borrower.
    """
    db = _session_factory()()
    try:
        db.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"),
            {"tid": str(tenant_id)},
        )
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
