"""Finding out that the platform is broken.

Before this, an unhandled exception returned a 500 to a customer and went to
stdout, which nobody reads. Every request could have been failing for a day
and the first anyone would have known is a customer saying so — which for a
product whose whole promise is *noticing things* would be an unusually
pointed way to fail.

Four decisions.

**Faults are stored in our own Postgres, not shipped to a third party.** The
usual answer here is Sentry, and for most products it is the right one. Not
for this one: a stack trace from a multi-tenant platform carries other
companies' operating data, so the ordinary configuration would mean every
customer's data can arrive in a third-party account on any exception. That
also happens to satisfy the no-paid-subscription constraint, but the reason is
the first one (D57).

**One row per distinct fault.** An outage produces thousands of identical
errors. Recording each would make the incident's first casualty the table
meant to explain it, and would send a thousand emails about one broken line.
Rows are keyed by a fingerprint built from the exception type and the deepest
frame in *our* code — never the message, because messages carry varying data
and fingerprinting on one would make every occurrence unique.

**Capturing must never make things worse.** Everything here is wrapped: a
failure to record a failure is logged and swallowed. This matters more than it
sounds, because the most likely cause of a burst of errors is the database
being unavailable, which is also what recording needs. When that happens the
log is the fallback, and it is the only one there is.

**Alerts are rationed twice.** Once per fault — a given fingerprint alerts at
most once an hour — and once globally, so a bad deploy that breaks nine
different things sends a handful of emails rather than nine hundred. The
ceiling is deliberately low. An alert that arrives at 3am must be worth
waking for, and the fastest way to make alerts worthless is to send too many.

**The circular dependency, stated rather than discovered.** Alerts go out
through `core.mail`. If mail is what is broken, the alert about mail being
broken cannot be delivered, and nothing here can fix that. The mitigation is
that mail failures still land in this table and on the ops health endpoint, so
a pull-based check sees what a push-based one structurally cannot. Anyone
relying on alerts alone is relying on the thing most likely to be down.
"""

from __future__ import annotations

import contextvars
import datetime
import hashlib
import logging
import secrets
import traceback as tb
import uuid
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text as sql
from starlette.datastructures import MutableHeaders

from aether.core import mail, scrub
from aether.core.config import get_settings
from aether.core.db import session as plain_session

logger = logging.getLogger(__name__)

# The reference shown to a customer in a 500 and written into every log line
# for that request, so "it said error a3f9c1" is answerable.
current_reference: contextvars.ContextVar[str] = contextvars.ContextVar("reference", default="")

# Which tenant the current unit of work belongs to, set by the tenancy
# dependency once a request is attributed. Not read from the token here: this
# has to work for failures that happen before, during, or instead of
# authentication.
#
# **A mutable holder rather than the id itself, and a test is the only reason
# this is known.** Every endpoint in this platform is a sync `def`, which
# Starlette runs in a threadpool — and a thread gets a *copy* of the context,
# so `ContextVar.set()` inside an endpoint or a dependency is invisible to the
# middleware that will handle the exception. The obvious version of this
# recorded every single fault as belonging to nobody, losing exactly the field
# that separates one broken customer from all of them. The copied context
# still points at the same dict, so mutating one crosses the boundary that
# rebinding cannot (D58).
_holder: contextvars.ContextVar[dict | None] = contextvars.ContextVar("tenant", default=None)


def begin_unit_of_work() -> None:
    """Start a fresh attribution scope. Called once per request."""
    _holder.set({})


def attribute(tenant_id: uuid.UUID | None) -> None:
    """Say whose work this is, so a fault raised later can be attributed."""
    holder = _holder.get()
    if holder is None:
        holder = {}
        _holder.set(holder)
    holder["tenant_id"] = tenant_id


def attributed_tenant() -> uuid.UUID | None:
    holder = _holder.get()
    return holder.get("tenant_id") if holder else None


# How long a given fault stays quiet after alerting. Long enough that a fault
# firing continuously does not become the reason nobody reads alerts.
ALERT_INTERVAL = datetime.timedelta(hours=1)

# Alerts of any kind allowed in one hour, across every fault. A bad deploy
# breaks several things at once, and the useful signal is "the platform is on
# fire", which does not need nine hundred emails to convey.
MAX_ALERTS_PER_HOUR = 6

_PACKAGE = "aether"


def new_reference() -> str:
    """Short, unguessable, and pronounceable over a support call."""
    return secrets.token_hex(6)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


@dataclass(frozen=True)
class Fault:
    """What was worked out about one exception, before storing it."""

    fingerprint: str
    exception_type: str
    message: str
    traceback: str
    location: str


def _our_frame(exc: BaseException) -> str:
    """The deepest frame inside Aether itself.

    The deepest frame overall is nearly always somebody else's library, which
    groups every unrelated fault that happens to end in the same SQLAlchemy
    line under one fingerprint. What identifies a fault is the last line of
    *our* code that was running.
    """
    frames = tb.extract_tb(exc.__traceback__)
    if not frames:
        return "unknown"
    marker = f"/{_PACKAGE}/"
    ours = [f for f in frames if marker in f.filename.replace("\\", "/")]
    chosen = (ours or frames)[-1]

    path = chosen.filename.replace("\\", "/")
    if marker in path:
        where = path.rsplit(marker, 1)[-1]
    else:
        # A frame from outside the package — only reachable when nothing in
        # the traceback is ours, which in a running service means never. Cut
        # to the basename anyway: the absolute path of a file on the server is
        # deployment layout, and it would otherwise be stored and then shown
        # in the staff console.
        where = path.rsplit("/", 1)[-1]
    return f"{where}:{chosen.lineno} in {chosen.name}"


def describe(exc: BaseException, *, service: str) -> Fault:
    """Work out what this fault is, scrubbing as it goes."""
    location = _our_frame(exc)
    exception_type = type(exc).__name__
    # Not the message. Messages carry the varying part — an email address, an
    # id, a value — so fingerprinting on one gives every occurrence its own
    # row and the deduplication that makes this table usable never happens.
    seed = f"{service}|{exception_type}|{location}"
    return Fault(
        fingerprint=hashlib.sha256(seed.encode()).hexdigest(),
        exception_type=exception_type[:200],
        message=scrub.text(str(exc), limit=2000),
        traceback=scrub.text(
            "".join(tb.format_exception(type(exc), exc, exc.__traceback__)), limit=8000
        ),
        location=location[:300],
    )


def capture(
    exc: BaseException,
    *,
    service: str,
    tenant_id: uuid.UUID | None = None,
    reference: str = "",
) -> str:
    """Record one fault and alert if it has earned one. Returns the reference.

    Never raises. A failure inside this function must not become a second
    failure on top of the one being reported.
    """
    reference = reference or current_reference.get() or new_reference()
    if tenant_id is None:
        tenant_id = attributed_tenant()

    try:
        fault = describe(exc, service=service)
    except Exception:  # noqa: BLE001
        logger.exception("could not describe an exception; reference=%s", reference)
        return reference

    # Logged first and unconditionally. If the database is what is broken —
    # the most likely cause of a burst — this line is the only record there
    # will be, and it must not depend on the store below succeeding.
    logger.error(
        "fault reference=%s service=%s type=%s at=%s: %s",
        reference,
        service,
        fault.exception_type,
        fault.location,
        fault.message,
    )

    try:
        should_alert, occurrences = _store(fault, service, tenant_id, reference)
    except Exception:  # noqa: BLE001
        logger.exception("could not record fault %s; it exists only in this log", reference)
        return reference

    if should_alert:
        _alert(fault, service=service, occurrences=occurrences, reference=reference)
    return reference


def _store(
    fault: Fault, service: str, tenant_id: uuid.UUID | None, reference: str
) -> tuple[bool, int]:
    """Upsert the fault. Returns (alert is due, how many times it has happened).

    A single statement rather than select-then-write: two processes hitting the
    same fault at the same moment is the normal case during an incident, not
    the exotic one, and a read-modify-write would lose counts or deadlock
    exactly when the table matters most.
    """
    now = _now()
    with plain_session() as db:
        row = db.execute(
            sql("""
                INSERT INTO error_events (
                    id, fingerprint, service, exception_type, message, traceback,
                    location, occurrences, first_seen_at, last_seen_at,
                    last_tenant_id, tenants_seen, last_reference
                )
                VALUES (
                    :id, :fingerprint, :service, :exception_type, :message, :traceback,
                    :location, 1, :now, :now, :tenant_id, :first_tenant, :reference
                )
                ON CONFLICT (fingerprint) DO UPDATE SET
                    occurrences = error_events.occurrences + 1,
                    last_seen_at = :now,
                    last_tenant_id = COALESCE(:tenant_id, error_events.last_tenant_id),
                    -- Only counts up, and only when the tenant actually
                    -- changed. Approximate on purpose: an exact distinct count
                    -- would need a second table, and the question being asked
                    -- is "one customer or all of them", not "which".
                    tenants_seen = error_events.tenants_seen + CASE
                        WHEN :tenant_id IS NOT NULL
                         AND error_events.last_tenant_id IS DISTINCT FROM :tenant_id
                        THEN 1 ELSE 0 END,
                    last_reference = :reference,
                    message = :message,
                    traceback = :traceback,
                    -- A fault that comes back after being resolved is news
                    -- again, so resolving it clears both marks.
                    resolved_at = NULL,
                    resolved_by = ''
                RETURNING occurrences, alerted_at, resolved_at
                """),
            {
                "id": uuid.uuid4(),
                "fingerprint": fault.fingerprint,
                "service": service,
                "exception_type": fault.exception_type,
                "message": fault.message,
                "traceback": fault.traceback,
                "location": fault.location,
                "now": now,
                "tenant_id": tenant_id,
                "first_tenant": 1 if tenant_id is not None else 0,
                "reference": reference,
            },
        ).one()

        occurrences = int(row.occurrences)
        alerted_at = row.alerted_at
        quiet = alerted_at is not None and (now - alerted_at) < ALERT_INTERVAL
        if quiet:
            return False, occurrences

        # The global ceiling, checked in the same transaction that claims the
        # slot. Two services failing simultaneously must not each decide there
        # was room.
        recent = db.execute(
            sql("SELECT count(*) FROM error_events WHERE alerted_at > :since"),
            {"since": now - datetime.timedelta(hours=1)},
        ).scalar_one()
        if int(recent) >= MAX_ALERTS_PER_HOUR:
            logger.warning(
                "alert for %s suppressed: %s alerts already sent this hour",
                fault.location,
                recent,
            )
            return False, occurrences

        db.execute(
            sql("UPDATE error_events SET alerted_at = :now WHERE fingerprint = :fingerprint"),
            {"now": now, "fingerprint": fault.fingerprint},
        )
        return True, occurrences


def _alert(fault: Fault, *, service: str, occurrences: int, reference: str) -> None:
    """Email somebody. Failure here is logged and never propagated."""
    settings = get_settings()
    recipient = settings.alert_email
    if not recipient:
        # Not silent: an unconfigured alert address is itself a thing worth
        # knowing, and the ops health endpoint reports it.
        logger.warning("fault %s would have alerted, but AETHER_ALERT_EMAIL is unset", reference)
        return

    body = (
        f"{service} raised {fault.exception_type}\n\n"
        f"  where       {fault.location}\n"
        f"  occurrences {occurrences}\n"
        f"  reference   {reference}\n"
        f"  environment {settings.env}\n\n"
        f"{fault.message}\n\n"
        f"This fault will not alert again for {int(ALERT_INTERVAL.total_seconds() // 60)} "
        f"minutes, however often it happens. Resolve it in the staff console to "
        f"hear about it again if it returns.\n"
    )
    try:
        status, detail = mail.send(
            recipient, f"[aether/{settings.env}] {fault.exception_type} in {service}", body
        )
        if status != mail.SENT:
            # Deliberately not captured. An alert failing to send would
            # otherwise become a fault, which would try to alert, which would
            # fail to send.
            logger.error("fault alert not delivered (%s): %s", status, detail)
    except Exception:  # noqa: BLE001
        logger.exception("fault alert raised while sending; not re-captured")


def recent(limit: int = 50, *, include_resolved: bool = False) -> list[dict]:
    """Open faults, newest first. The raw material of the ops endpoint.

    Returns everything including the scrubbed text; the *caller* decides who
    may see which fields, because the role split belongs at the boundary
    where the reader is known (D57).
    """
    clause = "" if include_resolved else "WHERE resolved_at IS NULL"
    with plain_session() as db:
        rows = db.execute(
            sql(f"""
                SELECT id, fingerprint, service, exception_type, message, traceback,
                       location, occurrences, first_seen_at, last_seen_at,
                       tenants_seen, last_reference, alerted_at, resolved_at, resolved_by
                FROM error_events {clause}
                ORDER BY last_seen_at DESC
                LIMIT :limit
                """),
            {"limit": max(1, min(limit, 200))},
        ).mappings()
        return [dict(r) for r in rows]


def resolve(fingerprint: str, *, by: str) -> bool:
    """Mark a fault handled. Returns whether anything changed.

    This is what re-arms the alarm: a recurrence after resolving is news
    again, rather than being folded silently into a row that already alerted.
    """
    with plain_session() as db:
        changed = db.execute(
            sql("""
                UPDATE error_events
                SET resolved_at = :now, resolved_by = :by, alerted_at = NULL
                WHERE fingerprint = :fingerprint AND resolved_at IS NULL
                RETURNING id
                """),
            {"now": _now(), "by": by[:320], "fingerprint": fingerprint},
        ).first()
        return changed is not None


def summary() -> dict:
    """Counts for the ops health endpoint. Cheap enough to poll."""
    with plain_session() as db:
        row = db.execute(
            sql("""
                SELECT
                  count(*) FILTER (WHERE resolved_at IS NULL) AS open,
                  count(*) FILTER (WHERE last_seen_at > :hour) AS active_last_hour,
                  COALESCE(sum(occurrences) FILTER (WHERE last_seen_at > :day), 0) AS day_total
                FROM error_events
                """),
            {
                "hour": _now() - datetime.timedelta(hours=1),
                "day": _now() - datetime.timedelta(days=1),
            },
        ).one()
        return {
            "open": int(row.open),
            "active_last_hour": int(row.active_last_hour),
            "occurrences_last_day": int(row.day_total),
        }


# ── Catching what nothing else caught ─────────────────────────────────────────


class FaultMiddleware:
    """The last thing between an exception and the customer.

    **Pure ASGI rather than `BaseHTTPMiddleware`, and the difference is not
    stylistic.** `BaseHTTPMiddleware` runs the endpoint in a separate task, and
    a context variable set downstream — the tenant id, set once a request is
    attributed — is not visible when the exception surfaces back here. Every
    fault would be recorded as belonging to nobody, which is precisely the
    field that separates "one customer is broken" from "everyone is". Plain
    ASGI stays in the same task, so the context is the same context.

    It also adds the reference to every response, not only failures: a
    customer describing something odd that did not raise at all is still a
    conversation that has to find the right requests in the log.
    """

    def __init__(self, app, service: str) -> None:
        self.app = app
        self.service = service

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        reference = new_reference()
        current_reference.set(reference)
        begin_unit_of_work()
        started = False

        async def watched(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = MutableHeaders(scope=message)
                headers.append("X-Aether-Reference", reference)
            await send(message)

        try:
            await self.app(scope, receive, watched)
        except Exception as exc:  # noqa: BLE001 - this is the net
            capture(exc, service=self.service, reference=reference)
            if started:
                # Headers are already on the wire, so there is no clean 500 to
                # send. The connection breaks, which is honest: pretending to
                # finish a half-written response would be worse than failing.
                raise
            await JSONResponse(
                status_code=500,
                content={
                    "detail": "Something went wrong on our side. It has been recorded.",
                    "reference": reference,
                },
            )(scope, receive, send)


def install(app: FastAPI, *, service: str) -> None:
    """Wrap one service so nothing it raises goes unrecorded."""
    app.add_middleware(FaultMiddleware, service=service)
