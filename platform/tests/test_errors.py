"""Whether the platform can tell you it is broken.

Requires the dev database.

The thing being defended is not that errors get written down. It is that the
machinery survives the conditions it exists for. An error tracker is only ever
exercised during an incident, which is exactly when the database is slow, the
same fault is firing a thousand times a second, and mail is one of the things
that is down. Anything here that works only on a calm afternoon is decoration.

So: capture must not raise when the database is gone, a flood must not become
a flood of emails, ordinary 404s must not fill the table, and the tenant a
fault belongs to must survive the trip from the endpoint back to the
middleware.
"""

import datetime
import uuid

import pytest
import sqlalchemy
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text

from aether.core import errors, health, mail, scrub
from aether.core.db import get_engine
from aether.core.db import session as plain_session
from aether.core.models import StaffRole
from aether.core.staff import create_admin, issue_staff_token

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module", autouse=True)
def database():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except sqlalchemy.exc.OperationalError:
        pytest.skip("Postgres not reachable — start it with: docker compose up -d db")


@pytest.fixture(autouse=True)
def empty_table(database):
    """Start each test with no faults recorded.

    Not tidiness: the global alert ceiling counts alerts across the whole
    table, so faults left behind by an earlier test would silently suppress
    the alerts a later one is asserting on. That would make these tests pass
    or fail depending on what ran before them.
    """
    with plain_session() as db:
        db.execute(text("DELETE FROM error_events"))


@pytest.fixture
def alerts(monkeypatch) -> list[tuple[str, str, str]]:
    """Alerts that would have been emailed, with a recipient configured."""
    box: list[tuple[str, str, str]] = []
    monkeypatch.setattr(errors.get_settings(), "alert_email", "ops@aethertest.io", raising=False)
    monkeypatch.setattr(
        mail, "send", lambda r, s, b, **kw: (box.append((r, s, b)), (mail.SENT, "x"))[1]
    )
    return box


def boom(message: str = "the roof fell in") -> Exception:
    """A real exception with a real traceback, raised from a real line."""
    try:
        raise RuntimeError(message)
    except RuntimeError as exc:
        return exc


def rows() -> list[dict]:
    with plain_session() as db:
        return [dict(r) for r in db.execute(text("SELECT * FROM error_events")).mappings()]


# ── Fingerprinting: the property the whole table rests on ─────────────────────


def test_the_same_line_failing_twice_is_one_fault_however_different_the_message():
    """The dedup that makes this table survive an outage. Messages carry the
    varying part — an id, an address, a value — so fingerprinting on one would
    give every occurrence its own row and there would be nothing to read."""
    first = errors.describe(boom("failed for tenant 41"), service="x")
    second = errors.describe(boom("failed for tenant 92"), service="x")
    assert first.fingerprint == second.fingerprint


def test_two_different_lines_are_two_faults():
    def elsewhere() -> Exception:
        try:
            raise RuntimeError("the roof fell in")
        except RuntimeError as exc:
            return exc

    assert (
        errors.describe(boom(), service="x").fingerprint
        != errors.describe(elsewhere(), service="x").fingerprint
    )


def test_the_same_fault_in_two_services_is_not_merged():
    a = errors.describe(boom(), service="control_plane")
    b = errors.describe(boom(), service="agent_runtime")
    assert a.fingerprint != b.fingerprint


def test_a_location_never_carries_the_absolute_path_of_a_file_on_the_server():
    """Deployment layout is not something to store and then render in a
    console. Only reachable when no frame in the traceback is ours, which in a
    running service means never — but this table is read by people."""
    fault = errors.describe(boom(), service="x")
    assert not fault.location.startswith("C:"), fault.location
    assert ":/" not in fault.location and "/home/" not in fault.location, fault.location
    assert fault.location.startswith("test_errors.py:"), fault.location


def test_the_location_names_our_code_not_the_library_that_raised():
    """Fingerprinting on the deepest frame overall would file every unrelated
    fault that happens to end in the same psycopg line under one row.

    Provoked through a real Aether function reaching a real database with a
    value it cannot use, so the traceback genuinely has our frame near the top
    and several library frames beneath it — which is the shape this rule
    exists for and the shape a hand-built exception would not have.
    """
    from aether.knowledge import store

    with pytest.raises(sqlalchemy.exc.DataError) as caught:
        store.of_kind("not-a-uuid", kind="decision", limit=1)

    fault = errors.describe(caught.value, service="x")
    assert "site-packages" not in fault.location, fault.location
    assert "knowledge/store.py" in fault.location, fault.location
    assert " in of_kind" in fault.location, "and it names the function, not only the file"


def test_what_is_stored_has_been_scrubbed():
    fault = errors.describe(boom("could not reach founder@realcompany.com"), service="x")
    assert "founder@realcompany.com" not in fault.message
    assert "founder@realcompany.com" not in fault.traceback
    assert scrub.REDACTED in fault.message


# ── Recording ─────────────────────────────────────────────────────────────────


def test_a_thousand_identical_failures_are_one_row_with_a_count():
    for _ in range(12):
        errors.capture(boom(), service="test")

    stored = rows()
    assert len(stored) == 1
    assert stored[0]["occurrences"] == 12


def test_a_fault_records_which_tenant_hit_it_and_how_many_did():
    """One customer broken and every customer broken are different
    emergencies, and this count is the cheapest way to tell them apart."""
    for tenant in (uuid.uuid4(), uuid.uuid4(), uuid.uuid4()):
        errors.capture(boom(), service="test", tenant_id=tenant)

    assert rows()[0]["tenants_seen"] == 3


def test_capture_never_raises_when_the_database_is_gone(monkeypatch):
    """The most likely cause of a burst of errors is the database being
    unreachable, which is also what recording needs. Turning that into a
    second exception inside the handler would replace a degraded platform
    with a crashing one."""

    def unreachable(*args, **kwargs):
        raise sqlalchemy.exc.OperationalError("SELECT 1", {}, Exception("no route to host"))

    monkeypatch.setattr(errors, "plain_session", unreachable)
    reference = errors.capture(boom(), service="test")
    assert reference, "and it still returns a reference the customer can quote"


def test_a_reference_is_returned_and_stored_so_support_can_find_the_row():
    reference = errors.capture(boom(), service="test")
    assert rows()[0]["last_reference"] == reference


# ── Alerting: rationed, or worthless ──────────────────────────────────────────


def test_the_first_occurrence_alerts_and_the_second_does_not(alerts):
    """A fault firing continuously must not become the reason nobody reads
    alerts. One email, then silence for an hour."""
    errors.capture(boom(), service="test")
    assert len(alerts) == 1

    for _ in range(30):
        errors.capture(boom(), service="test")
    assert len(alerts) == 1, "a fault that keeps firing must not keep emailing"


def test_a_bad_deploy_that_breaks_nine_things_does_not_send_nine_hundred(alerts):
    """The global ceiling. Per-fault rationing alone does not help when the
    deploy broke everything at once, and that is the case where the mail is
    least useful and most voluminous."""

    def distinct_fault(n: int) -> Exception:
        try:
            raise RuntimeError(f"fault {n}")
        except RuntimeError as exc:
            return exc

    for n in range(errors.MAX_ALERTS_PER_HOUR + 8):
        # A distinct fingerprint each time, by varying the service.
        errors.capture(distinct_fault(n), service=f"svc-{n}")

    assert len(alerts) == errors.MAX_ALERTS_PER_HOUR
    assert len(rows()) == errors.MAX_ALERTS_PER_HOUR + 8, "all of them still recorded"


def test_resolving_a_fault_re_arms_its_alarm(alerts):
    """Without this a fault that was fixed keeps its old alert timestamp, and
    a recurrence weeks later is folded silently into a row that has already
    alerted. Nobody would hear about it."""
    errors.capture(boom(), service="test")
    assert len(alerts) == 1

    fingerprint = rows()[0]["fingerprint"]
    assert errors.resolve(fingerprint, by="engineer@aether.io") is True

    errors.capture(boom(), service="test")
    assert len(alerts) == 2

    back = rows()[0]
    assert back["resolved_at"] is None, "a recurrence reopens it"
    assert back["resolved_by"] == ""


def test_resolving_something_already_resolved_changes_nothing():
    errors.capture(boom(), service="test")
    fingerprint = rows()[0]["fingerprint"]
    assert errors.resolve(fingerprint, by="a@aether.io") is True
    assert errors.resolve(fingerprint, by="b@aether.io") is False


def test_an_alert_that_cannot_be_sent_does_not_become_a_second_fault(monkeypatch):
    """Otherwise: sending fails, which is a fault, which tries to alert, which
    fails to send. The recursion is the reason `_alert` swallows."""
    monkeypatch.setattr(errors.get_settings(), "alert_email", "ops@aethertest.io", raising=False)
    monkeypatch.setattr(mail, "send", lambda *a, **kw: (_ for _ in ()).throw(OSError("no mail")))

    errors.capture(boom(), service="test")  # must not raise
    assert len(rows()) == 1, "one fault, not two"


def test_nothing_is_emailed_when_no_alert_address_is_configured(monkeypatch):
    """Recorded, still visible on the ops endpoint, but nothing pushed. The
    health snapshot is what says so rather than leaving it to be discovered."""
    sent: list = []
    monkeypatch.setattr(errors.get_settings(), "alert_email", "", raising=False)
    monkeypatch.setattr(mail, "send", lambda *a, **kw: (sent.append(a), (mail.SENT, ""))[1])

    errors.capture(boom(), service="test")
    assert sent == []
    assert len(rows()) == 1


# ── The net under the services ────────────────────────────────────────────────


@pytest.fixture
def caught() -> TestClient:
    """A minimal service wired exactly as the real ones are."""
    app = FastAPI()
    errors.install(app, service="test_service")

    @app.get("/explode")
    def explode() -> dict:
        raise RuntimeError("something nobody handled")

    @app.get("/missing")
    def missing() -> dict:
        raise HTTPException(status_code=404, detail="no such thing")

    @app.get("/attributed/{tenant_id}")
    def attributed(tenant_id: uuid.UUID) -> dict:
        # Exactly what the tenancy dependency does once a request is
        # attributed, and the reason the middleware is pure ASGI.
        errors.attribute(tenant_id)
        raise RuntimeError("failed after we knew whose request this was")

    return TestClient(app, raise_server_exceptions=False)


def test_an_unhandled_exception_becomes_a_500_with_a_reference(caught):
    response = caught.get("/explode")
    assert response.status_code == 500

    reference = response.json()["reference"]
    assert reference
    assert rows()[0]["last_reference"] == reference, "the customer can quote it to support"


def test_the_response_never_carries_the_exception_to_the_customer(caught):
    """A 500 body is the one place a stack trace most often leaks to whoever
    asked for it."""
    body = caught.get("/explode").text
    assert "RuntimeError" not in body
    assert "something nobody handled" not in body
    assert "Traceback" not in body


def test_an_ordinary_404_is_not_recorded_as_a_fault(caught):
    """Client errors are not platform faults. Recording them would bury the
    real ones under every mistyped URL on the internet."""
    assert caught.get("/missing").status_code == 404
    assert rows() == []


def test_the_tenant_set_inside_the_endpoint_survives_to_the_middleware(caught):
    """The property that made this middleware pure ASGI rather than
    `BaseHTTPMiddleware`, which runs the endpoint in its own task and would
    have recorded every fault as belonging to nobody — losing exactly the
    field that separates one broken customer from all of them."""
    tenant_id = uuid.uuid4()
    assert caught.get(f"/attributed/{tenant_id}").status_code == 500
    assert rows()[0]["last_tenant_id"] == tenant_id


def test_every_response_carries_a_reference_header(caught):
    """Not only failures: a customer describing something odd that did not
    raise still needs their requests findable in the log."""
    assert caught.get("/missing").headers.get("X-Aether-Reference")


# ── Health ────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def control_plane(database) -> TestClient:
    from aether.control_plane.app import app

    return TestClient(app)


def test_readyz_says_ok_when_the_database_answers(control_plane):
    response = control_plane.get("/readyz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readyz_reports_503_when_the_database_is_gone_and_healthz_still_does_not(
    control_plane, monkeypatch
):
    """The distinction this pair exists for. `/healthz` returned a flat "ok"
    before today and would have reported a green month through a total
    outage; making it check the database instead would mean a brief blip
    kills every healthy container. So: liveness stays dumb, readiness does
    the checking, and only readiness is what you route and monitor on.
    """

    def unreachable(*args, **kwargs):
        raise sqlalchemy.exc.OperationalError("SELECT 1", {}, Exception("no route to host"))

    monkeypatch.setattr(health, "plain_session", unreachable)

    assert control_plane.get("/readyz").status_code == 503
    assert control_plane.get("/healthz").status_code == 200


def test_the_snapshot_says_when_alerting_is_not_configured(monkeypatch):
    """An alerting system nobody set up looks exactly like an alerting system
    with nothing to report."""
    monkeypatch.setattr(health.get_settings(), "alert_email", "", raising=False)
    assert health.snapshot("test")["alerts_configured"] is False
    assert health.snapshot("test")["healthy"] is False


def test_the_snapshot_does_not_report_zero_errors_while_the_database_is_down(monkeypatch):
    """ "No errors" is the most dangerous thing this endpoint could say during
    an outage, and a missing count would be read as exactly that."""

    def unreachable(*args, **kwargs):
        raise sqlalchemy.exc.OperationalError("SELECT 1", {}, Exception("no route to host"))

    monkeypatch.setattr(health, "plain_session", unreachable)
    out = health.snapshot("test")

    assert out["database"]["ok"] is False
    assert "unavailable" in out["errors"]


# ── Who may read what ─────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def brain(database) -> TestClient:
    from aether.main_brain.app import app

    return TestClient(app)


def staff(role: StaffRole) -> tuple[str, dict]:
    email = f"{role.value}-{uuid.uuid4().hex[:10]}@aether.io"
    admin = create_admin(email, "staff-password-long-enough", role)
    return email, {"Authorization": f"Bearer {issue_staff_token(admin)}"}


def test_an_observer_sees_that_something_broke_and_never_the_words(brain):
    """The fleet view's whole discipline is that staff see counts about a
    tenant and never content. A stack trace crosses that line by nature, so
    the boundary is drawn inside the payload instead (D57)."""
    errors.capture(boom("could not reach founder@realcompany.com"), service="test")
    _, headers = staff(StaffRole.observer)

    body = brain.get("/v1/ops/errors", headers=headers).json()
    assert len(body) == 1
    fault = body[0]

    assert fault["exception_type"] == "RuntimeError"
    assert fault["occurrences"] == 1
    assert fault["location"], "enough to say what is broken and where"
    assert "message" not in fault
    assert "traceback" not in fault


def test_an_engineer_sees_the_scrubbed_text_and_the_look_is_recorded(brain):
    errors.capture(boom(), service="test")
    email, headers = staff(StaffRole.engineer)

    fault = brain.get("/v1/ops/errors", headers=headers).json()[0]
    assert "the roof fell in" in fault["message"]
    assert "Traceback" in fault["traceback"]

    trail = brain.get("/v1/staff-trail", headers=headers).json()
    reads = [e for e in trail if e["action"] == "faults.read" and e["admin_email"] == email]
    assert reads, "reading something derived from customer data must be answerable"


def test_the_trail_does_not_copy_the_thing_it_is_auditing_access_to(brain):
    """A trail that recorded the message alongside the read would just be a
    second, less guarded copy of the same text."""
    errors.capture(boom("could not reach founder@realcompany.com"), service="test")
    email, headers = staff(StaffRole.engineer)
    brain.get("/v1/ops/errors", headers=headers)

    trail = brain.get("/v1/staff-trail", headers=headers).json()
    entry = next(e for e in trail if e["action"] == "faults.read" and e["admin_email"] == email)
    assert "founder@realcompany.com" not in str(entry)
    assert "roof" not in str(entry)


def test_an_observer_cannot_resolve_a_fault(brain):
    errors.capture(boom(), service="test")
    fingerprint = rows()[0]["fingerprint"]
    _, headers = staff(StaffRole.observer)

    assert brain.post(f"/v1/ops/errors/{fingerprint}/resolve", headers=headers).status_code == 403


def test_an_engineer_can_resolve_and_it_leaves_the_open_list(brain):
    errors.capture(boom(), service="test")
    fingerprint = rows()[0]["fingerprint"]
    email, headers = staff(StaffRole.engineer)

    assert brain.post(f"/v1/ops/errors/{fingerprint}/resolve", headers=headers).status_code == 200
    assert brain.get("/v1/ops/errors", headers=headers).json() == []
    assert len(brain.get("/v1/ops/errors?include_resolved=true", headers=headers).json()) == 1
    assert rows()[0]["resolved_by"] == email


def test_the_fault_endpoints_are_not_reachable_without_a_staff_token(brain):
    for path in ("/v1/ops/errors", "/v1/ops/health"):
        assert brain.get(path).status_code == 401, path


def test_ops_health_reports_the_fault_counts(brain):
    errors.capture(boom(), service="test")
    _, headers = staff(StaffRole.observer)

    body = brain.get("/v1/ops/health", headers=headers).json()
    assert body["database"]["ok"] is True
    assert body["errors"]["open"] == 1
    assert body["errors"]["active_last_hour"] == 1


def test_a_resolved_fault_stops_counting_as_open(brain):
    errors.capture(boom(), service="test")
    errors.resolve(rows()[0]["fingerprint"], by="e@aether.io")
    _, headers = staff(StaffRole.observer)

    assert brain.get("/v1/ops/health", headers=headers).json()["errors"]["open"] == 0


def test_the_summary_counts_occurrences_not_rows():
    for _ in range(7):
        errors.capture(boom(), service="test")
    assert errors.summary() == {
        "open": 1,
        "active_last_hour": 1,
        "occurrences_last_day": 7,
    }


def test_an_old_fault_is_not_counted_as_active():
    errors.capture(boom(), service="test")
    with plain_session() as db:
        db.execute(
            text("UPDATE error_events SET last_seen_at = :old"),
            {"old": datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=3)},
        )

    summary = errors.summary()
    assert summary["open"] == 1, "still unresolved"
    assert summary["active_last_hour"] == 0
    assert summary["occurrences_last_day"] == 0
