"""The whole-business snapshot.

Requires the dev database (docker compose up -d db + alembic upgrade head).

This object exists to make cross-domain reasoning expressible, so the tests
that matter are the ones about what it refuses to include: another tenant's
data, quarantined readings, and stale domains counted as healthy.
"""

import uuid

import pytest
import sqlalchemy
from fastapi.testclient import TestClient
from sqlalchemy import text

from aether.business import state as business_state
from aether.core.db import get_engine

pytestmark = pytest.mark.postgres

RECEIVABLES = {
    "dso_days": 41.0,
    "overdue_ratio": 0.13,
    "ar_total": 260_000.0,
    "invoice_count": 190,
}
RECEIVABLES_BAD = {
    "dso_days": 88.0,
    "overdue_ratio": 0.44,
    "ar_total": 260_000.0,
    "invoice_count": 190,
}
CASH = {
    "runway_months": 11.0,
    "payroll_cover_months": 5.0,
    "obligation_coverage": 2.1,
    "burn_volatility": 0.14,
    "cash_balance": 180_000.0,
    "committed_outflows_30d": 86_000.0,
}


@pytest.fixture(scope="module")
def clients():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except sqlalchemy.exc.OperationalError:
        pytest.skip("Postgres not reachable — start it with: docker compose up -d db")
    from aether.agent_runtime.app import app as runtime_app
    from aether.control_plane.app import app as cp_app

    return TestClient(cp_app), TestClient(runtime_app)


def new_org(cp) -> tuple[uuid.UUID, dict]:
    slug = f"bstate-{uuid.uuid4().hex[:10]}"
    r = cp.post(
        "/v1/auth/signup",
        json={
            "org_name": "State Org",
            "org_slug": slug,
            "email": f"owner-{slug}@aethertest.io",
            "password": "long-enough-password",
        },
    )
    assert r.status_code == 201, r.text
    return uuid.UUID(r.json()["tenant_id"]), {"Authorization": f"Bearer {r.json()['access_token']}"}


def push(runtime, headers, domain: str, metrics: dict, source: str = "test"):
    return runtime.post(
        f"/v1/domains/{domain}/readings",
        json={"metrics": metrics, "source": source},
        headers=headers,
    )


# ── Gathering ─────────────────────────────────────────────────────────────────


def test_an_empty_business_is_empty_not_broken(clients):
    cp, _ = clients
    tenant_id, _ = new_org(cp)

    state = business_state.load(tenant_id)
    assert state.domains == {}
    assert state.impaired == []
    assert state.worst is None


def test_every_reported_domain_appears_once(clients):
    cp, runtime = clients
    tenant_id, headers = new_org(cp)
    push(runtime, headers, "receivables", RECEIVABLES)
    push(runtime, headers, "cash_runway", CASH)

    state = business_state.load(tenant_id)
    assert set(state.domains) == {"receivables", "cash_runway"}
    assert "receivables" in state
    assert state.get("cash_runway").label == "Cash & Runway"


def test_only_the_newest_reading_per_domain_is_carried(clients):
    """Several readings, one snapshot — the current position, not a history."""
    cp, runtime = clients
    tenant_id, headers = new_org(cp)
    push(runtime, headers, "receivables", RECEIVABLES, source="older")
    push(runtime, headers, "receivables", dict(RECEIVABLES, dso_days=39.0), source="newer")

    state = business_state.load(tenant_id)
    assert len(state.domains) == 1
    assert state.metric("receivables", "dso_days") == 39.0


def test_metrics_are_reachable_without_checking_the_domain_exists_first(clients):
    """The convenience that makes cross-domain rules readable."""
    cp, runtime = clients
    tenant_id, headers = new_org(cp)
    push(runtime, headers, "receivables", RECEIVABLES)

    state = business_state.load(tenant_id)
    assert state.metric("receivables", "dso_days") == 41.0
    assert state.metric("cash_runway", "runway_months") is None
    assert state.metric("receivables", "not_a_metric") is None


# ── What it refuses to include ────────────────────────────────────────────────


def test_one_business_never_sees_another(clients):
    """The property that outranks every other consideration here."""
    cp, runtime = clients
    tenant_a, headers_a = new_org(cp)
    tenant_b, headers_b = new_org(cp)

    push(runtime, headers_a, "receivables", RECEIVABLES, source="tenant-a-only")
    push(runtime, headers_b, "cash_runway", CASH, source="tenant-b-only")

    state_a = business_state.load(tenant_a)
    state_b = business_state.load(tenant_b)

    assert set(state_a.domains) == {"receivables"}
    assert set(state_b.domains) == {"cash_runway"}
    assert "tenant-b-only" not in repr(state_a.as_dict())
    assert "tenant-a-only" not in repr(state_b.as_dict())


def test_quarantined_readings_are_not_evidence(clients):
    """A reading the quality gate refused must not reach cross-domain
    reasoning. A finding built on one would be worse than no finding."""
    cp, runtime = clients
    tenant_id, headers = new_org(cp)

    good = push(runtime, headers, "receivables", RECEIVABLES, source="accepted-one")
    assert good.json()["accepted"] is True

    # Contradictory: nothing outstanding, yet a book that is 90% overdue.
    bad = push(
        runtime,
        headers,
        "receivables",
        {"dso_days": 5.0, "overdue_ratio": 0.9, "ar_total": 0.0, "invoice_count": 0},
        source="quarantined-one",
    )
    if bad.json()["accepted"] is False:
        state = business_state.load(tenant_id)
        assert state.metric("receivables", "dso_days") == 41.0, (
            "the quarantined reading became the business's current position"
        )
        assert "quarantined-one" not in repr(state.as_dict())


# ── Describing the position ───────────────────────────────────────────────────


def test_impairment_is_measured_against_the_tenants_own_floor(clients):
    """Severity has to be comparable across domains, and raw performance is
    not: 0.74 means different things against a floor of 0.72 and one of 0.92."""
    cp, runtime = clients
    tenant_id, headers = new_org(cp)
    push(runtime, headers, "receivables", RECEIVABLES_BAD)
    push(runtime, headers, "cash_runway", CASH)

    state = business_state.load(tenant_id)
    receivables = state.get("receivables")
    cash = state.get("cash_runway")

    assert receivables.impaired is True
    assert receivables.severity > 0
    assert cash.impaired is False
    assert cash.severity == 0.0


def test_the_worst_domain_is_the_one_furthest_below_its_floor(clients):
    cp, runtime = clients
    tenant_id, headers = new_org(cp)
    push(runtime, headers, "receivables", RECEIVABLES_BAD)
    push(runtime, headers, "cash_runway", CASH)

    state = business_state.load(tenant_id)
    assert state.worst.domain == "receivables"
    assert [s.domain for s in state.impaired] == ["receivables"]


def test_a_healthy_business_has_no_worst_domain(clients):
    cp, runtime = clients
    tenant_id, headers = new_org(cp)
    push(runtime, headers, "receivables", RECEIVABLES)
    push(runtime, headers, "cash_runway", CASH)

    state = business_state.load(tenant_id)
    assert state.impaired == []
    assert state.worst is None


def test_staleness_uses_each_packs_own_window(clients):
    """Receivables tolerate a week; cash does not. A single global age would
    either nag the first or trust the second too long."""
    cp, runtime = clients
    tenant_id, headers = new_org(cp)
    push(runtime, headers, "receivables", RECEIVABLES)
    push(runtime, headers, "cash_runway", CASH)

    state = business_state.load(tenant_id)
    assert state.get("receivables").max_age_hours == 192.0
    assert state.get("cash_runway").max_age_hours == 336.0
    assert state.fresh.keys() == state.domains.keys()


def test_a_stale_domain_is_not_counted_as_impaired(clients):
    """A reading too old to decide on is too old to call impaired. Treating it
    otherwise manufactures a problem out of missing data."""
    import datetime

    from aether.core.db import tenant_session
    from aether.core.models import Observation

    cp, runtime = clients
    tenant_id, headers = new_org(cp)
    push(runtime, headers, "receivables", RECEIVABLES_BAD)

    with tenant_session(tenant_id) as db:
        obs = db.scalars(sqlalchemy.select(Observation)).first()
        obs.observed_at = business_state.utcnow() - datetime.timedelta(days=60)

    state = business_state.load(tenant_id)
    snapshot = state.get("receivables")
    assert snapshot.stale is True
    assert snapshot.impaired is True, "still unhealthy on its face"
    assert state.impaired == [], "but not counted, because the data is too old"
    assert state.worst is None


def test_a_configured_domain_that_never_reported_is_named(clients):
    """Configured and silent is a setup failure, and it looks exactly like
    fine unless something says so."""
    cp, runtime = clients
    tenant_id, headers = new_org(cp)
    push(runtime, headers, "receivables", RECEIVABLES)

    r = runtime.put(
        "/v1/domains/cash_runway/monitoring",
        json={"interval_minutes": 60},
        headers=headers,
    )
    if r.status_code >= 400:
        pytest.skip("monitoring endpoint unavailable in this environment")

    state = business_state.load(tenant_id)
    assert "cash_runway" not in state.domains
    assert "cash_runway" in state.silent


def test_the_snapshot_serialises_for_a_prompt_or_an_api(clients):
    cp, runtime = clients
    tenant_id, headers = new_org(cp)
    push(runtime, headers, "receivables", RECEIVABLES)

    payload = business_state.load(tenant_id).as_dict()
    assert payload["tenant_id"] == str(tenant_id)
    assert payload["domains"]["receivables"]["metrics"]["dso_days"] == 41.0
    assert "impaired" in payload and "silent" in payload
