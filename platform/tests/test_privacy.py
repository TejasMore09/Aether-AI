"""Export and erasure, and the thing that stops them quietly going stale.

Requires the dev database.

The endpoints are the easy part. What makes this worth having is
`test_every_table_in_the_schema_is_classified`: an export that was complete
when it was written stops being complete the first time a migration adds a
table, and nothing about it looks broken — the file still downloads and the
endpoint still returns 200. That test fails the build instead.

The other one that matters is
`test_erasing_a_person_removes_every_copy_of_their_address`. Email addresses
are in six tables, not one, so `DELETE FROM users` would look like compliance
and leave five copies behind.
"""

import uuid

import pytest
import sqlalchemy
from fastapi.testclient import TestClient
from sqlalchemy import text

from aether.core import privacy
from aether.core.db import get_engine, tenant_session
from aether.core.db import session as plain_session

pytestmark = pytest.mark.postgres

PASSWORD = "long-enough-password"


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


def new_org(cp) -> tuple[uuid.UUID, str, dict]:
    slug = f"gdpr-{uuid.uuid4().hex[:10]}"
    email = f"owner-{slug}@aethertest.io"
    response = cp.post(
        "/v1/auth/signup",
        json={"org_name": "Privacy Co", "org_slug": slug, "email": email, "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return (
        uuid.UUID(body["tenant_id"]),
        email,
        {"Authorization": f"Bearer {body['access_token']}"},
    )


def user_id_of(email: str) -> uuid.UUID:
    with plain_session() as db:
        return db.execute(text("SELECT id FROM users WHERE email = :e"), {"e": email}).scalar_one()


# ── The registry, which is the point ──────────────────────────────────────────


def test_every_table_in_the_schema_is_classified(clients):
    """**The test this feature exists around.**

    An export is complete on the day it is written and silently incomplete
    from the next migration onwards. Nothing about that failure is visible:
    the endpoint still answers, the file still downloads, and the missing
    table is only noticed by whoever asked for their data and did not get it.

    So the schema and the registry have to disagree loudly. Adding a table
    fails here until somebody has decided what it holds.
    """
    missing = privacy.unclassified()
    assert missing == set(), (
        f"these tables exist and nobody has said what they hold: {sorted(missing)}. "
        "Add them to privacy.REGISTRY — an export cannot include a table it does "
        "not know about."
    )


def test_the_registry_does_not_describe_tables_that_are_gone(clients):
    """The other direction. A registry full of dropped tables is a registry
    nobody has read recently."""
    assert privacy.stale_entries() == set()


def test_every_classification_is_one_of_the_four(clients):
    allowed = {privacy.DELETE, privacy.ANONYMISE, privacy.NOT_PERSONAL, privacy.STAFF}
    for table, holding in privacy.REGISTRY.items():
        assert holding.on_erasure in allowed, table
        assert holding.holds, f"{table} has no description of what it holds"


def test_the_tables_carrying_an_email_are_the_ones_erasure_rewrites(clients):
    """A guard on the registry against the schema rather than against itself:
    every table the registry says carries an email really has that column."""
    with plain_session() as db:
        for table, holding in privacy.REGISTRY.items():
            if not holding.email_column:
                continue
            found = db.execute(
                text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = :c"
                ),
                {"t": table, "c": holding.email_column},
            ).scalar_one()
            assert found == 1, f"{table}.{holding.email_column} does not exist"


# ── Access and portability ────────────────────────────────────────────────────


def test_a_person_can_take_their_own_data(clients):
    cp, _ = clients
    _, email, headers = new_org(cp)

    response = cp.get("/v1/me/export", headers=headers)
    assert response.status_code == 200
    body = response.json()

    assert body["profile"]["email"] == email
    assert body["organisations"][0]["role"] == "owner"
    assert body["sessions"], "the session they are asking from, at least"
    assert "exported_at" in body


def test_the_export_never_contains_a_credential(clients):
    """A portability export is a file that ends up in a downloads folder and
    an email attachment. Anything in it that could be used to sign in has been
    handed to whoever finds it."""
    cp, _ = clients
    _, email, headers = new_org(cp)

    # Give them something of each kind to leak.
    cp.post("/v1/auth/mfa/enrol", headers=headers)
    cp.post("/v1/auth/forgot", json={"email": email})

    raw = cp.get("/v1/me/export", headers=headers).text
    assert PASSWORD not in raw
    assert "$2b$" not in raw, "no bcrypt hash"

    with plain_session() as db:
        secret = db.execute(text("SELECT secret FROM mfa_enrolments LIMIT 1")).scalar()
        token_hash = db.execute(text("SELECT token_hash FROM password_resets LIMIT 1")).scalar()
    if secret:
        assert secret not in raw
    if token_hash:
        assert token_hash not in raw

    assert "not_included" in cp.get("/v1/me/export", headers=headers).json()


def test_an_owner_can_take_the_organisations_data(clients):
    cp, runtime = clients
    tenant_id, _, headers = new_org(cp)
    runtime.post(
        "/v1/domains/receivables/observations",
        headers=headers,
        json={"drift_fraction": 0.6, "performance": 0.4, "source": "pytest"},
    )

    body = cp.get("/v1/tenant/export", headers=headers).json()
    assert body["organisation"]["id"] == str(tenant_id)
    assert body["people"], "who is in it"
    assert body["readings"], "what it reported"


def test_one_organisations_export_never_contains_another(clients):
    """The isolation the whole product rests on, checked at the one endpoint
    whose job is to hand over everything."""
    cp, runtime = clients
    _, _, mine = new_org(cp)
    other_tenant, other_email, theirs = new_org(cp)
    runtime.post(
        "/v1/domains/receivables/observations",
        headers=theirs,
        json={"drift_fraction": 0.77, "performance": 0.13, "source": "their-private-source"},
    )

    raw = cp.get("/v1/tenant/export", headers=mine).text
    assert other_email not in raw
    assert "their-private-source" not in raw
    assert str(other_tenant) not in raw


def test_a_viewer_cannot_export_the_organisation(clients):
    """It carries every member's address and every decision the business has
    made, which is not a viewer's to take away."""
    cp, _ = clients
    tenant_id, _, _ = new_org(cp)

    from aether.core import sessions
    from aether.core.models import Membership, Role, User
    from aether.core.security import hash_password, issue_token

    with plain_session() as db:
        user = User(
            email=f"viewer-{uuid.uuid4().hex[:8]}@aethertest.io",
            password_hash=hash_password("x" * 12),
        )
        db.add(user)
        db.flush()
        db.add(Membership(user_id=user.id, tenant_id=tenant_id, role=Role.viewer))
        person, address = user.id, user.email

    session_id, expires_at = sessions.begin(person, tenant_id)
    token = issue_token(
        person, address, tenant_id, Role.viewer, session_id=session_id, expires_at=expires_at
    )
    viewer = {"Authorization": f"Bearer {token}"}

    assert cp.get("/v1/tenant/export", headers=viewer).status_code == 403
    assert cp.get("/v1/me/export", headers=viewer).status_code == 200, "their own, though"


# ── Erasure ───────────────────────────────────────────────────────────────────


def test_erasing_a_person_removes_every_copy_of_their_address(clients):
    """**The one a delete-the-row implementation fails.**

    Six tables hold an email, not one. `DELETE FROM users` looks like
    compliance and leaves five copies behind, and nothing about the result
    looks wrong.
    """
    cp, runtime = clients
    tenant_id, email, headers = new_org(cp)

    # Leave a trace in as many of the six as possible.
    cp.post("/v1/auth/forgot", json={"email": email})
    cp.post("/v1/keys", headers=headers, json={"name": "ingest"})
    runtime.post(
        "/v1/domains/receivables/observations",
        headers=headers,
        json={"drift_fraction": 0.6, "performance": 0.4, "source": "pytest"},
    )
    runtime.post("/v1/domains/receivables/evaluate", headers=headers, json={})
    cp.post("/v1/auth/login", json={"email": email, "password": "wrong-on-purpose"})

    # A second owner, so erasure is not refused for stranding the organisation.
    _add_second_owner(tenant_id)

    report = privacy.erase_user(user_id_of(email))
    assert report["pseudonym"].startswith("erased-")

    # Split by whether row-level security scopes the table, because reading
    # the scoped ones from a plain session is not "no rows" — it is an error,
    # and a check that mistook one for the other would pass on nothing.
    with plain_session() as db:
        for table, column in (("users", "email"), ("login_throttle", "identifier")):
            left = db.execute(
                text(f"SELECT count(*) FROM {table} WHERE {column} = :e"), {"e": email}
            ).scalar_one()
            assert left == 0, f"{table}.{column} still holds the address"

    with tenant_session(tenant_id) as db:
        for table, column in (
            ("audit_logs", "triggered_by"),
            ("pending_approvals", "resolved_by"),
            ("notifications", "recipient"),
            ("api_keys", "created_by"),
        ):
            left = db.execute(
                text(f"SELECT count(*) FROM {table} WHERE {column} = :e"), {"e": email}
            ).scalar_one()
            assert left == 0, f"{table}.{column} still holds the address"

    # And the rewrite really happened rather than the rows having never
    # existed — otherwise this test passes against a product that records
    # nothing at all.
    assert sum(report["rows"][t] for t in ("audit_logs", "notifications", "api_keys")) > 0


def _add_second_owner(tenant_id: uuid.UUID) -> str:
    from aether.core.models import Membership, Role, User
    from aether.core.security import hash_password

    with plain_session() as db:
        user = User(
            email=f"co-owner-{uuid.uuid4().hex[:8]}@aethertest.io",
            password_hash=hash_password("x" * 12),
        )
        db.add(user)
        db.flush()
        db.add(Membership(user_id=user.id, tenant_id=tenant_id, role=Role.owner))
        return user.email


def test_the_record_of_what_happened_survives_the_person(clients):
    """Art. 17(3): the business's account of its own operations is not the
    person's to erase. The decision stays and the actor becomes a pseudonym."""
    cp, runtime = clients
    tenant_id, email, headers = new_org(cp)
    runtime.post(
        "/v1/domains/receivables/observations",
        headers=headers,
        json={"drift_fraction": 0.6, "performance": 0.4, "source": "pytest"},
    )
    runtime.post("/v1/domains/receivables/evaluate", headers=headers, json={})
    _add_second_owner(tenant_id)

    with tenant_session(tenant_id) as db:
        before = db.execute(text("SELECT count(*) FROM audit_logs")).scalar_one()
    assert before > 0

    report = privacy.erase_user(user_id_of(email))

    with tenant_session(tenant_id) as db:
        after = db.execute(text("SELECT count(*) FROM audit_logs")).scalar_one()
        actors = set(db.execute(text("SELECT DISTINCT triggered_by FROM audit_logs")).scalars())

    assert after == before, "the decisions must not vanish with the person"
    assert report["pseudonym"] in actors


def test_the_pseudonym_cannot_be_turned_back_into_the_address(clients):
    """A hash of the email would be reversible by anyone who can guess an
    address, which for an email is everyone."""
    seen = {privacy._pseudonym() for _ in range(50)}
    assert len(seen) == 50, "random, not derived"


def test_erasing_the_only_owner_is_refused(clients):
    """Otherwise a business is left that nobody can administer, and the data
    of everyone else in it is stranded with it."""
    cp, _ = clients
    _, email, _ = new_org(cp)

    with pytest.raises(privacy.PrivacyError) as caught:
        privacy.erase_user(user_id_of(email))
    assert "only owner" in str(caught.value)


def test_the_account_becomes_a_tombstone_rather_than_disappearing(clients):
    """Rows elsewhere point at the id, and a dangling foreign key is a worse
    outcome than a blanked row."""
    cp, _ = clients
    tenant_id, email, _ = new_org(cp)
    _add_second_owner(tenant_id)
    person = user_id_of(email)

    privacy.erase_user(person)

    with plain_session() as db:
        row = db.execute(
            text("SELECT email, display_name, is_active FROM users WHERE id = :id"), {"id": person}
        ).one()
    assert row.email.endswith("@aether.invalid"), "RFC 2606: can never be delivered to"
    assert row.display_name == ""
    assert row.is_active is False


def test_an_erased_person_cannot_sign_in(clients):
    cp, _ = clients
    tenant_id, email, headers = new_org(cp)
    _add_second_owner(tenant_id)

    privacy.erase_user(user_id_of(email))

    assert cp.post("/v1/auth/login", json={"email": email, "password": PASSWORD}).status_code == 401
    assert cp.get("/v1/tenant", headers=headers).status_code == 401, "and their session is gone"


def test_erasure_is_recorded_without_recording_who(clients):
    """A regulator may ask whether the mechanism runs. Keeping the erased
    address to prove it would make this table the one place it survived."""
    cp, _ = clients
    tenant_id, email, _ = new_org(cp)
    _add_second_owner(tenant_id)

    report = privacy.erase_user(user_id_of(email))

    with plain_session() as db:
        row = (
            db.execute(
                text("SELECT * FROM erasure_log WHERE pseudonym = :p"), {"p": report["pseudonym"]}
            )
            .mappings()
            .one()
        )
    assert row["subject_kind"] == "user"
    assert row["counts"]["users"] == 1
    assert email not in str(dict(row))


def test_erasing_through_the_endpoint_needs_the_password_and_the_word(clients):
    cp, _ = clients
    tenant_id, email, headers = new_org(cp)
    _add_second_owner(tenant_id)

    assert (
        cp.post(
            "/v1/me/erase", json={"password": PASSWORD, "confirm": "yes"}, headers=headers
        ).status_code
        == 400
    )
    assert (
        cp.post(
            "/v1/me/erase", json={"password": "wrong", "confirm": "DELETE"}, headers=headers
        ).status_code
        == 401
    )

    done = cp.post(
        "/v1/me/erase", json={"password": PASSWORD, "confirm": "DELETE"}, headers=headers
    )
    assert done.status_code == 200, done.text
    assert done.json()["erased"] is True
    assert "backup" in done.json()["note"].lower(), "and it says what it cannot reach"


# ── Erasing an organisation ───────────────────────────────────────────────────


def test_erasing_an_organisation_removes_its_data_and_keeps_its_people(clients):
    """A person may belong to more than one organisation. Their identity is
    not this organisation's to delete."""
    cp, runtime = clients
    tenant_id, email, headers = new_org(cp)
    runtime.post(
        "/v1/domains/receivables/observations",
        headers=headers,
        json={"drift_fraction": 0.6, "performance": 0.4, "source": "pytest"},
    )

    report = privacy.erase_tenant(tenant_id)
    assert report["rows"]["observations"] >= 1
    assert report["rows"]["tenants"] == 1

    with plain_session() as db:
        assert (
            db.execute(
                text("SELECT count(*) FROM tenants WHERE id = :id"), {"id": tenant_id}
            ).scalar_one()
            == 0
        )
        assert (
            db.execute(
                text("SELECT count(*) FROM users WHERE email = :e"), {"e": email}
            ).scalar_one()
            == 1
        ), "the person survives their organisation"


def test_erasing_an_organisation_needs_its_name_typed_out(clients):
    """A generic "DELETE" is too easy to type into the wrong window. The name
    of the thing being destroyed is not."""
    cp, _ = clients
    _, _, headers = new_org(cp)

    wrong = cp.post(
        "/v1/tenant/erase", json={"password": PASSWORD, "confirm_slug": "DELETE"}, headers=headers
    )
    assert wrong.status_code == 400
    assert "Type" in wrong.json()["detail"]

    slug = cp.get("/v1/tenant", headers=headers).json()["slug"]
    done = cp.post(
        "/v1/tenant/erase", json={"password": PASSWORD, "confirm_slug": slug}, headers=headers
    )
    assert done.status_code == 200, done.text


def test_erasing_an_organisation_does_not_touch_another(clients):
    cp, runtime = clients
    mine_tenant, _, mine = new_org(cp)
    theirs_tenant, _, theirs = new_org(cp)
    for headers in (mine, theirs):
        runtime.post(
            "/v1/domains/receivables/observations",
            headers=headers,
            json={"drift_fraction": 0.6, "performance": 0.4, "source": "pytest"},
        )

    privacy.erase_tenant(mine_tenant)

    with tenant_session(theirs_tenant) as db:
        assert db.execute(text("SELECT count(*) FROM observations")).scalar_one() >= 1
    assert cp.get("/v1/tenant", headers=theirs).status_code == 200


def test_the_backup_note_says_how_long_and_is_not_a_guess(clients):
    """The one thing erasure cannot reach. A person asking deserves a number,
    and the number has to come from the settings that produce it."""
    from aether.core.config import get_settings

    note = privacy.backup_retention_note()
    settings = get_settings()
    expected = settings.backup_keep * settings.backup_interval_hours / 24
    assert f"{expected:.0f} days" in note
