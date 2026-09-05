"""Answering "is it working?" without guessing.

`/healthz` already existed on all three services and returned `{"status":
"ok"}` unconditionally. That is not a health check, it is a check that Python
is running — and it will say `ok` while every request in the building fails
because Postgres is unreachable. An uptime monitor watching it would report a
green month through a total outage.

So the two questions are separated, because they have different answers and
different consequences:

**`/healthz` is liveness.** Is this process alive? It stays trivial on
purpose. A liveness probe that touches the database is how a brief database
blip becomes an orchestrator killing every healthy container it has.

**`/readyz` is readiness.** Can this process actually serve? It touches the
database, and returns 503 when it cannot. This is the one a load balancer
should route on and the one an uptime monitor should watch.

`snapshot()` is the fuller picture for the staff console: what is configured,
what is broken, and — the parts that are easy to leave out — whether the
alerting path itself is set up, and when a backup was last *proven restorable*
rather than merely taken. An alerting system that is not configured looks
exactly like an alerting system with nothing to report, and a backup system
that has silently stopped looks exactly like one with nothing to do.
"""

from __future__ import annotations

import datetime
import logging

from sqlalchemy import text as sql

from aether.core import errors, mail
from aether.core.config import get_settings
from aether.core.db import session as plain_session

logger = logging.getLogger(__name__)

_STARTED_AT = datetime.datetime.now(datetime.UTC)


def database_ok() -> tuple[bool, str]:
    """Whether the database answers. Returns (ok, detail)."""
    try:
        with plain_session() as db:
            db.execute(sql("SELECT 1"))
        return True, ""
    except Exception as exc:  # noqa: BLE001 - a readiness probe reports, never raises
        return False, f"{type(exc).__name__}: {exc}"[:200]


def snapshot(service: str) -> dict:
    """Everything the staff console needs to answer "is the platform well?".

    Never raises: a health endpoint that fails when things are unhealthy is
    the least useful thing in the building.
    """
    settings = get_settings()
    ok, detail = database_ok()
    now = datetime.datetime.now(datetime.UTC)

    out: dict = {
        "service": service,
        "environment": settings.env,
        "uptime_seconds": int((now - _STARTED_AT).total_seconds()),
        "database": {"ok": ok, "detail": detail},
        # Configuration facts, not opinions. An unconfigured mail transport
        # means password resets and fault alerts both silently go nowhere, and
        # neither would otherwise announce itself.
        "mail_configured": mail.configured(),
        "alerts_configured": bool(settings.alert_email),
    }

    if ok:
        try:
            out["errors"] = errors.summary()
        except Exception as exc:  # noqa: BLE001
            out["errors"] = {"unavailable": f"{type(exc).__name__}: {exc}"[:200]}
        try:
            # Imported here rather than at module scope: `ops.backup` reaches
            # for postgres command-line tools, and a web process that never
            # takes a backup should not fail to start because they are absent.
            from aether.ops import backup

            out["backups"] = backup.status()
        except Exception as exc:  # noqa: BLE001
            out["backups"] = {"unavailable": f"{type(exc).__name__}: {exc}"[:200], "stale": True}
    else:
        # Said explicitly rather than reported as zero errors, which is what a
        # missing key would be read as — and "no errors" is the most dangerous
        # possible thing to say while the database is down.
        out["errors"] = {"unavailable": "database unreachable"}
        out["backups"] = {"unavailable": "database unreachable", "stale": True}

    # "Healthy" means every question this endpoint can answer came back well,
    # including the operational ones. A platform that is serving requests
    # while nothing has been backed up for a week is not healthy; it is
    # working, which is a different word.
    out["healthy"] = (
        ok
        and out["mail_configured"]
        and out["alerts_configured"]
        and not out["backups"].get("stale", True)
    )
    return out
