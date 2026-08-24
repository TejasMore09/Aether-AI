"""Domain inventory endpoint — derived, tenant-scoped, no registration step."""

import uuid

import pytest
import sqlalchemy
from fastapi.testclient import TestClient
from sqlalchemy import text

from aether.core.db import get_engine, tenant_session
from aether.core.models import PolicyConfig
from aether.services.evaluation import record_observation

pytestmark = pytest.mark.postgres


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


def _new_org(cp) -> tuple[uuid.UUID, dict]:
    slug = f"dom-{uuid.uuid4().hex[:10]}"
    r = cp.post(
        "/v1/auth/signup",
        json={
            "org_name": "Domain Org",
            "org_slug": slug,
            "email": f"owner-{slug}@aethertest.io",
            "password": "long-enough-password",
        },
    )
    assert r.status_code == 201, r.text
    return uuid.UUID(r.json()["tenant_id"]), {
        "Authorization": f"Bearer {r.json()['access_token']}"
    }


def test_inventory_is_derived_from_telemetry_and_policy(clients):
    cp, rt = clients
    tenant_id, token = _new_org(cp)

    record_observation(tenant_id, "revenue", drift_fraction=0.2, performance=0.9)
    record_observation(tenant_id, "revenue", drift_fraction=0.6, performance=0.5)
    with tenant_session(tenant_id) as db:
        db.add(PolicyConfig(tenant_id=tenant_id, domain="headcount", params={}))

    rows = rt.get("/v1/domains", headers=token).json()
    by_domain = {r["domain"]: r for r in rows}

    assert set(by_domain) == {"revenue", "headcount"}
    assert by_domain["revenue"]["observation_count"] == 2
    assert by_domain["revenue"]["latest_drift_fraction"] == pytest.approx(0.6)
    assert by_domain["revenue"]["latest_performance"] == pytest.approx(0.5)
    assert by_domain["headcount"]["has_policy"] is True
    assert by_domain["headcount"]["observation_count"] == 0
    assert by_domain["headcount"]["latest_drift_fraction"] is None


def test_inventory_is_tenant_scoped(clients):
    cp, rt = clients
    tenant_a, token_a = _new_org(cp)
    _, token_b = _new_org(cp)

    record_observation(tenant_a, "secret-domain", drift_fraction=0.5, performance=0.5)

    a_domains = {r["domain"] for r in rt.get("/v1/domains", headers=token_a).json()}
    b_domains = {r["domain"] for r in rt.get("/v1/domains", headers=token_b).json()}

    assert "secret-domain" in a_domains
    assert "secret-domain" not in b_domains


def test_inventory_requires_auth(clients):
    _, rt = clients
    assert rt.get("/v1/domains").status_code == 401
