"""Choosing a sector, changing it, and being told honestly what it does.

Requires the dev database for the HTTP tests.

A dropdown that silently changes how a business is judged is worse than no
dropdown, so most of these are about what the customer is *told*: that Retail
means a stricter standard than the default, that Marketing changes nothing and
why, and that the figures behind all of it describe US public companies rather
than businesses like theirs.

The other half is that changing your mind is safe. A sector change must move
future readings only, never rewrite the band a stored reading was already
judged against.
"""

import uuid

import pytest
import sqlalchemy
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from aether.core.db import get_engine, tenant_session
from aether.core.models import AuditLog
from aether.domains import preview, sector


@pytest.fixture(scope="module")
def client():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except sqlalchemy.exc.OperationalError:
        pytest.skip("Postgres not reachable — start it with: docker compose up -d db")
    from aether.control_plane.app import app

    return TestClient(app)


def new_org(client, **extra) -> tuple[uuid.UUID, dict]:
    slug = f"on-{uuid.uuid4().hex[:10]}"
    r = client.post(
        "/v1/auth/signup",
        json={
            "org_name": "Onboarding Co",
            "org_slug": slug,
            "email": f"owner-{slug}@aethertest.io",
            "password": "long-enough-password",
            **extra,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    return uuid.UUID(body["tenant_id"]), {"Authorization": f"Bearer {body['access_token']}"}


# ── What the choice does, before it is made ───────────────────────────────────


def test_choosing_retail_says_it_means_a_stricter_standard():
    """Someone picking this is agreeing to be held to a tighter collection
    threshold than the default. That is worth knowing at the moment of
    choosing, not three weeks later from an alert."""
    summary = preview.summary_for(sector.get("retail"))
    dso = next(c for c in summary["changes"] if c["metric"] == "dso_days")

    assert dso["stricter"] is True
    assert dso["sector_good"] < dso["pack_good"]
    assert summary["changes_nothing"] is False


def test_choosing_construction_says_it_buys_room():
    summary = preview.summary_for(sector.get("construction"))
    dso = next(c for c in summary["changes"] if c["metric"] == "dso_days")
    assert dso["stricter"] is False
    assert dso["sector_good"] > dso["pack_good"]


def test_a_sector_that_changes_nothing_says_so_and_says_why():
    """The answer a vendor would bury. A customer who picks their own industry
    and gets no adjustment deserves the reason, not silence."""
    for key in ("marketing", "financial_services", sector.UNSPECIFIED):
        summary = preview.summary_for(sector.get(key))
        assert summary["changes"] == [], key
        assert summary["changes_nothing"] is True, key
        assert summary["bands_note"], f"{key} changes nothing and does not say why"


def test_the_figures_admit_where_they_came_from():
    """Only the ordering across sectors transfers from public-company data to
    an SME. Saying so is the difference between a band a customer can weigh
    and one they must simply trust."""
    note = preview.summary_for(sector.get("retail"))["source_note"]
    assert "US public companies" in note
    assert "own readings replace these" in note


def test_a_sector_with_no_effect_makes_no_claim_about_sources():
    """There is nothing to caveat, and a caveat on nothing reads as though
    something happened."""
    assert preview.summary_for(sector.get("marketing"))["source_note"] == ""


def test_the_basis_travels_with_the_change():
    """Whichever surface renders this, the sentence explaining the number
    comes with it rather than having to be reconstructed."""
    for change in preview.summary_for(sector.get("retail"))["changes"]:
        assert change["basis"]
        assert "Retail" in change["basis"]


# ── Over HTTP ─────────────────────────────────────────────────────────────────


def test_the_catalogue_carries_the_effects_so_a_signup_form_can_show_them(client):
    """Unauthenticated: a signup form needs this before anyone has an account,
    and it contains no tenant data."""
    listed = client.get("/v1/sectors").json()
    assert len(listed) == len(sector.all_sectors())

    by_key = {s["key"]: s for s in listed}
    assert by_key["retail"]["changes"], "retail should show what it moves"
    assert by_key["financial_services"]["changes_nothing"] is True
    assert by_key["financial_services"]["bands_note"]


def test_a_business_can_change_its_mind(client):
    _, auth = new_org(client, sector="retail")

    updated = client.patch("/v1/tenant", json={"sector": "construction"}, headers=auth)
    assert updated.status_code == 200, updated.text
    assert updated.json()["sector"] == "construction"
    assert updated.json()["sector_label"] == "Construction & trades"

    assert client.get("/v1/tenant", headers=auth).json()["sector"] == "construction"


def test_changing_one_field_does_not_reset_the_other(client):
    """The bug this shape of endpoint invites: a partial update silently
    zeroing whatever it did not mention."""
    _, auth = new_org(client, sector="retail", currency="INR")

    client.patch("/v1/tenant", json={"sector": "logistics"}, headers=auth)
    me = client.get("/v1/tenant", headers=auth).json()
    assert me["sector"] == "logistics"
    assert me["currency"] == "INR", "currency was not mentioned and must not have moved"


def test_a_sector_change_is_written_to_the_customers_own_audit_log(client):
    """An unexplained shift in verdicts should be traceable to the day someone
    changed this, rather than looking like the agent became erratic."""
    tenant_id, auth = new_org(client, sector="retail")
    client.patch("/v1/tenant", json={"sector": "construction"}, headers=auth)

    with tenant_session(tenant_id) as db:
        entries = db.scalars(select(AuditLog).where(AuditLog.action == "TENANT_UPDATED")).all()

    assert len(entries) == 1
    assert entries[0].details["sector"] == {"from": "retail", "to": "construction"}
    assert entries[0].domain == "organization", "not a business function, and should not pretend"


def test_changing_to_the_same_sector_records_nothing(client):
    """A no-op is not an event. Logging it would fill the customer's activity
    page with noise and make the entries that matter harder to see."""
    tenant_id, auth = new_org(client, sector="retail")
    client.patch("/v1/tenant", json={"sector": "retail"}, headers=auth)

    with tenant_session(tenant_id) as db:
        entries = db.scalars(select(AuditLog).where(AuditLog.action == "TENANT_UPDATED")).all()
    assert entries == []


def test_an_unknown_sector_is_refused_on_update_too(client):
    _, auth = new_org(client)
    assert client.patch("/v1/tenant", json={"sector": "vibes"}, headers=auth).status_code == 422


def test_only_an_owner_may_change_what_the_business_is(client):
    """It moves the bands every future reading is judged against, which is not
    a viewer's decision to make."""
    from aether.core.models import Role
    from aether.core.security import issue_token

    tenant_id, _ = new_org(client)
    viewer = {
        "Authorization": f"Bearer {issue_token(uuid.uuid4(), 'v@x.io', tenant_id, Role.viewer)}"
    }
    assert client.patch("/v1/tenant", json={"sector": "retail"}, headers=viewer).status_code == 403


# ── Changing your mind must not rewrite the past ──────────────────────────────


def test_a_stored_reading_keeps_the_band_it_was_judged_against(client):
    """The same reasoning that stamps currency onto an approval. Re-scoring
    history under a new sector would silently rewrite verdicts a customer has
    already seen and possibly acted on.
    """
    from aether.services.ingestion import ingest_reading

    tenant_id, auth = new_org(client, sector="retail")
    reading = {
        "dso_days": 40.0,
        "overdue_ratio": 0.12,
        "ar_total": 180_000.0,
        "invoice_count": 90,
    }
    first = ingest_reading(tenant_id, "receivables", reading, source="onboarding-test")
    assert first.accepted

    client.patch("/v1/tenant", json={"sector": "construction"}, headers=auth)

    from aether.core.models import Observation

    with tenant_session(tenant_id) as db:
        stored = db.get(Observation, first.observation_id)
        band = stored.details["signals"]["per_metric"]["dso_days"]["band"]
    assert "Retail" in band["basis"], "the stored reading must still say what it was judged against"

    # And the next reading uses the new sector.
    second = ingest_reading(tenant_id, "receivables", reading, source="onboarding-test")
    with tenant_session(tenant_id) as db:
        stored = db.get(Observation, second.observation_id)
        band = stored.details["signals"]["per_metric"]["dso_days"]["band"]
    assert "Construction" in band["basis"]
    assert second.performance > first.performance, "40 days is easier for a builder than a shop"
