"""Backups, and proof that one of them could actually be restored.

The plan asked for "automated backups with a *tested* restore, not merely
configured". The emphasis is the entire feature. Almost everybody has the
first half; the first time most people exercise the second half is the day
they need it, which is the worst possible day to learn something was wrong.

**Three things were measured while writing this, and each of them changes the
design.** None were guesses.

1. `pg_dump` run as the *application* role errors with "query would be
   affected by row-level security policy", **exits 0**, and still writes a
   plausible 57 KB file — the schema and the non-tenant tables, with not one
   row belonging to any customer. Row-level security is doing exactly what it
   was built to do; it just makes a misconfigured backup look like a backup.
2. `pg_restore` reports errors and **exits 0** as well.
3. So the exit code of either tool is worth nothing as evidence, and
   verification has to mean *restoring the file into a scratch database and
   asking it questions*.

That is what `verify` does. It is slower and it is the only version that means
anything (D63).

**What is checked, and why each one.**

- *The schema arrived.* Table names and the Alembic revision must match the
  source. A dump restored at the wrong revision is a database the code cannot
  run against.
- *Row-level security arrived.* Every table that carries a policy in the
  source must carry one in the restore. This is the check that matters most:
  a restored database with the tables but not the policies is one where every
  tenant can read every other tenant, and nothing about it looks broken.
- *No table that has rows lost all of them.* This is what catches finding (1).
  It is deliberately not an equality check on counts — the source is live and
  moves on after the snapshot, so demanding equality would fail honest backups
  and train people to ignore the result.
- *pgvector is present.* The knowledge base is a column type; without the
  extension the restore stops before it starts.

**What this does not do, said here rather than discovered later.** The files
land on the same machine as the database, which means this survives a dropped
table, a bad migration and a corrupted index — and does not survive losing the
host. Off-site copying is not implemented. When it is, the copy must be
encrypted before it leaves: a dump is every customer's operating data in one
file, and it is the one artefact of this platform that carries no access
control of its own.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import pathlib
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field

from sqlalchemy import text as sql

from aether.core import errors
from aether.core.config import get_settings
from aether.core.db import session as plain_session
from aether.core.models import RLS_TABLES

logger = logging.getLogger(__name__)

SERVICE = "backup"

# Custom format: compressed, and restorable table by table rather than as one
# enormous script that has to succeed from beginning to end.
_FORMAT = "c"

# Long enough for a large database on a small machine, short enough that a
# wedged process does not silently hold the schedule forever.
_TIMEOUT_SECONDS = 1800

_FILENAME = "aether-%Y%m%dT%H%M%SZ.dump"


class BackupError(RuntimeError):
    """A backup could not be produced, or could not be proven."""


@dataclass(frozen=True)
class Backup:
    """A file on disk, and enough about it to recognise it again."""

    path: pathlib.Path
    size_bytes: int
    sha256: str
    taken_at: datetime.datetime
    seconds: float


@dataclass
class Verification:
    """What a restore of one file actually demonstrated."""

    ok: bool
    checks: dict = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    # Errors the restore printed. Kept even on success, because version skew
    # between client and server produces noise that is worth seeing and is not
    # by itself a failure — the questions asked of the restored data are.
    restore_noise: str = ""


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def owner_url() -> str:
    """The connection a backup must use, and a clear refusal if it is absent.

    Not the application role. `pg_dump` as that role produces a file that
    looks right and contains none of any tenant's rows — measured, see the
    module docstring. Refusing here is the only place that mistake can be
    caught before the day it matters.
    """
    url = get_settings().migration_database_url
    if not url:
        raise BackupError(
            "AETHER_MIGRATION_DATABASE_URL is not set. A backup must connect as the "
            "database owner: row-level security silently empties a dump taken as the "
            "application role."
        )
    return url


def _libpq(url: str) -> str:
    """SQLAlchemy's URL form is not what the postgres tools accept."""
    return re.sub(r"^postgresql\+\w+://", "postgresql://", url)


def _run(command: list[str], *, url: str) -> subprocess.CompletedProcess:
    environment = {**os.environ, "PGCONNECT_TIMEOUT": "10"}
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        command,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        env=environment,
        check=False,
    )


def _digest(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def tools_available() -> tuple[bool, str]:
    """Whether pg_dump and pg_restore can be found at all."""
    missing = [tool for tool in ("pg_dump", "pg_restore", "psql") if shutil.which(tool) is None]
    if missing:
        return False, f"not on PATH: {', '.join(missing)}"
    return True, ""


def create(directory: pathlib.Path | str, *, url: str | None = None) -> Backup:
    """Write one dump. Raises `BackupError` rather than returning a bad file."""
    url = url or owner_url()
    target = pathlib.Path(directory)
    target.mkdir(parents=True, exist_ok=True)

    started = _now()
    path = target / started.strftime(_FILENAME)

    result = _run(
        [
            "pg_dump",
            "--dbname",
            _libpq(url),
            f"--format={_FORMAT}",
            "--file",
            str(path),
            # Roles live in the cluster, not the database, so ownership cannot
            # be restored into a fresh one anyway. Dumping without it makes the
            # file restorable somewhere that has different role names, which is
            # what a recovery machine is.
            "--no-owner",
            "--no-privileges",
        ],
        url=url,
    )

    # The exit code is not trusted, because it lies: as the application role
    # this command prints a row-level-security error, exits 0, and leaves a
    # file behind. stderr is what actually says whether anything went wrong.
    noise = (result.stderr or "").strip()
    if result.returncode != 0 or "error:" in noise.lower():
        path.unlink(missing_ok=True)
        raise BackupError(f"pg_dump failed: {noise[:600] or f'exit {result.returncode}'}")

    if not path.exists() or path.stat().st_size == 0:
        raise BackupError("pg_dump produced no file")

    # A dump is every customer's operating data in one file and is the one
    # artefact here with no access control of its own.
    try:
        path.chmod(0o600)
    except OSError:  # Windows and some volume drivers do not implement this.
        logger.debug("could not restrict permissions on %s", path)

    return Backup(
        path=path,
        size_bytes=path.stat().st_size,
        sha256=_digest(path),
        taken_at=started,
        seconds=(_now() - started).total_seconds(),
    )


def _query(url: str, database: str, statement: str) -> list[tuple]:
    """Ask one question of one database, over psql, returning parsed rows."""
    base = _libpq(url).rsplit("/", 1)[0]
    result = _run(
        ["psql", "--dbname", f"{base}/{database}", "-At", "-F", "\x1f", "-c", statement],
        url=url,
    )
    if result.returncode != 0:
        raise BackupError(f"query failed on {database}: {(result.stderr or '').strip()[:400]}")
    return [tuple(line.split("\x1f")) for line in result.stdout.splitlines() if line]


_TABLE_NAMES = "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"


def _counts(url: str, database: str, tables: list[str]) -> dict[str, int]:
    """Exact row counts, one query, every table.

    `pg_stat_user_tables.n_live_tup` was the first version of this and it is
    an *estimate* maintained by the stats collector. Measured on the
    development database it read 4,331 rows in the source against 55,839 in
    the freshly restored copy — the same data, because the source's statistics
    were stale and the restore's were not.

    That is not a cosmetic difference. The check that matters here is "a table
    with rows did not come back empty", and an estimate that reads zero for a
    populated table makes that check silently skip the table it was meant to
    protect. Counting is a full scan per table and this runs once a night.
    """
    if not tables:
        return {}
    # Names come from pg_tables, not from anything a caller supplied, and are
    # quoted regardless.
    union = " UNION ALL ".join(
        f"SELECT '{name}' AS t, count(*) AS n FROM public.\"{name}\"" for name in tables
    )
    return {name: int(number) for name, number in _query(url, database, union)}


_POLICIES = "SELECT tablename, count(*) FROM pg_policies WHERE schemaname='public' GROUP BY 1"

_REVISION = "SELECT version_num FROM alembic_version"

_EXTENSIONS = "SELECT extname FROM pg_extension"


def _shape(url: str, database: str) -> dict:
    """Everything the verification compares, from one database."""
    tables = [row[0] for row in _query(url, database, _TABLE_NAMES)]
    counts = _counts(url, database, tables)
    policies = {name: int(value) for name, value in _query(url, database, _POLICIES)}
    revision = _query(url, database, _REVISION)
    extensions = {row[0] for row in _query(url, database, _EXTENSIONS)}
    return {
        "counts": counts,
        "policies": policies,
        "revision": revision[0][0] if revision else "",
        "extensions": extensions,
    }


def verify(path: pathlib.Path | str, *, url: str | None = None) -> Verification:
    """Restore the file into a scratch database and interrogate it.

    The scratch database is dropped whether or not anything worked. Leaving a
    half-restored copy of every customer's data on the machine because a check
    failed would be a worse outcome than the failure.
    """
    url = url or owner_url()
    path = pathlib.Path(path)
    if not path.exists():
        return Verification(ok=False, problems=[f"no such file: {path}"])

    scratch = f"aether_verify_{uuid.uuid4().hex[:12]}"
    base = _libpq(url).rsplit("/", 1)[0]
    problems: list[str] = []
    checks: dict = {}
    noise = ""

    try:
        source = _shape(url, _libpq(url).rsplit("/", 1)[-1].split("?")[0])

        create_result = _run(
            ["psql", "--dbname", f"{base}/postgres", "-c", f'CREATE DATABASE "{scratch}"'], url=url
        )
        if create_result.returncode != 0:
            return Verification(
                ok=False,
                problems=[f"could not create a scratch database: {create_result.stderr[:300]}"],
            )

        restored = _run(
            [
                "pg_restore",
                "--dbname",
                f"{base}/{scratch}",
                "--no-owner",
                "--no-privileges",
                str(path),
            ],
            url=url,
        )
        noise = (restored.stderr or "").strip()

        # Note what pg_restore said, and then go and look for ourselves. A
        # version-skewed client emits errors for settings the server does not
        # know and still exits 0; that is noise. Whether the data arrived is a
        # question only the data can answer.
        target = _shape(url, scratch)

        checks["revision"] = {
            "source": source["revision"],
            "restored": target["revision"],
            "ok": source["revision"] == target["revision"] and bool(target["revision"]),
        }
        if not checks["revision"]["ok"]:
            problems.append(
                f"schema revision {target['revision']!r} does not match source "
                f"{source['revision']!r}"
            )

        missing_tables = sorted(set(source["counts"]) - set(target["counts"]))
        checks["tables"] = {
            "source": len(source["counts"]),
            "restored": len(target["counts"]),
            "missing": missing_tables,
            "ok": not missing_tables,
        }
        if missing_tables:
            problems.append(f"tables missing from the restore: {', '.join(missing_tables[:8])}")

        # The check that matters most. A restored database with the tables and
        # not the policies is one where every tenant can read every other
        # tenant, and nothing about it looks wrong from the outside.
        unprotected = sorted(
            table
            for table in RLS_TABLES
            if table in target["counts"] and not target["policies"].get(table)
        )
        checks["row_level_security"] = {
            "expected": len(RLS_TABLES),
            "protected": len([t for t in RLS_TABLES if target["policies"].get(t)]),
            "unprotected": unprotected,
            "ok": not unprotected,
        }
        if unprotected:
            problems.append(
                "restored without row-level security, so tenants would be readable "
                f"across: {', '.join(unprotected[:8])}"
            )

        # Not an equality check. The source is live and moves on after the
        # snapshot, so demanding equal counts would fail honest backups and
        # teach people to ignore the result. What is not survivable is a table
        # that had rows and now has none — which is exactly what a dump taken
        # as the application role produces.
        emptied = sorted(
            name
            for name, rows in source["counts"].items()
            if rows > 0 and target["counts"].get(name, 0) == 0
        )
        checks["rows"] = {
            "source_total": sum(source["counts"].values()),
            "restored_total": sum(target["counts"].values()),
            "emptied": emptied,
            "ok": not emptied,
        }
        if emptied:
            problems.append(
                f"tables that have rows in the source came back empty: {', '.join(emptied[:8])}"
            )

        missing_extensions = sorted(source["extensions"] - target["extensions"])
        checks["extensions"] = {"missing": missing_extensions, "ok": not missing_extensions}
        if missing_extensions:
            problems.append(f"extensions missing: {', '.join(missing_extensions)}")

    except BackupError as exc:
        problems.append(str(exc))
    finally:
        _run(
            ["psql", "--dbname", f"{base}/postgres", "-c", f'DROP DATABASE IF EXISTS "{scratch}"'],
            url=url,
        )

    return Verification(
        ok=not problems, checks=checks, problems=problems, restore_noise=noise[:2000]
    )


def prune(directory: pathlib.Path | str, *, keep: int = 14) -> list[pathlib.Path]:
    """Delete all but the newest `keep` dumps. Returns what went.

    A floor rather than an age: deleting by age alone means a backup system
    that has been broken for a month quietly deletes the last good file it
    ever made.
    """
    target = pathlib.Path(directory)
    if not target.exists():
        return []
    dumps = sorted(target.glob("aether-*.dump"), key=lambda p: p.name, reverse=True)
    gone = []
    for old in dumps[max(keep, 1) :]:
        old.unlink(missing_ok=True)
        gone.append(old)
    return gone


def run_cycle(directory: pathlib.Path | str, *, keep: int = 14, url: str | None = None) -> dict:
    """Take a backup, prove it, tidy up, and record what happened.

    Never raises. A failure here is recorded and captured as a fault so that
    6.3's alerting says so — a backup system that stops silently is the whole
    reason this is worth building carefully.
    """
    started = _now()
    row_id = uuid.uuid4()
    outcome: dict = {"status": "failed", "verified": False, "detail": "", "checks": {}}

    try:
        backup = create(directory, url=url)
        outcome |= {
            "path": str(backup.path),
            "size_bytes": backup.size_bytes,
            "sha256": backup.sha256,
        }

        verification = verify(backup.path, url=url)
        outcome["checks"] = verification.checks
        outcome["verified"] = verification.ok

        if verification.ok:
            outcome["status"] = "ok"
            outcome["detail"] = verification.restore_noise[:500]
        else:
            # The file is kept. A backup that failed its checks may still be
            # the best thing available at three in the morning, and deleting
            # the evidence of why it failed helps nobody.
            outcome["detail"] = "; ".join(verification.problems)[:1000]
            raise BackupError(outcome["detail"])

        prune(directory, keep=keep)

    except Exception as exc:  # noqa: BLE001 - recorded, never propagated
        outcome["detail"] = outcome["detail"] or f"{type(exc).__name__}: {exc}"[:1000]
        logger.error("backup cycle failed: %s", outcome["detail"])
        errors.capture(exc, service=SERVICE)

    _record(row_id, started, outcome)
    return outcome


def _record(row_id: uuid.UUID, started: datetime.datetime, outcome: dict) -> None:
    """Write the run down. Failing to record must not fail the backup."""
    try:
        with plain_session() as db:
            db.execute(
                sql("""
                    INSERT INTO backup_runs (
                        id, started_at, finished_at, status, path, size_bytes,
                        sha256, verified, checks, detail
                    ) VALUES (
                        :id, :started, :finished, :status, :path, :size,
                        :sha256, :verified, CAST(:checks AS jsonb), :detail
                    )
                    """),
                {
                    "id": row_id,
                    "started": started,
                    "finished": _now(),
                    "status": outcome["status"],
                    "path": outcome.get("path", ""),
                    "size": outcome.get("size_bytes", 0),
                    "sha256": outcome.get("sha256", ""),
                    "verified": outcome["verified"],
                    "checks": json.dumps(outcome.get("checks", {})),
                    "detail": outcome.get("detail", ""),
                },
            )
    except Exception:  # noqa: BLE001
        logger.exception("could not record the backup run; it happened but is unrecorded")


# How long without a successful, verified backup before the platform should be
# saying so out loud. A daily schedule with a day of slack: one missed night is
# a hiccup, two is a system that has stopped.
STALE_AFTER = datetime.timedelta(hours=48)


def status() -> dict:
    """When a backup last worked, and whether that was recently enough.

    Read by `core.health`, so the staff console can answer the question that
    otherwise goes unasked until it is urgent.
    """
    with plain_session() as db:
        row = db.execute(
            sql("""
                SELECT
                  max(started_at) FILTER (WHERE status = 'ok') AS last_ok,
                  max(started_at) FILTER (WHERE verified) AS last_verified,
                  max(started_at) AS last_attempt,
                  count(*) FILTER (WHERE status = 'failed') AS failures
                FROM backup_runs
                """)
        ).one()

    last_ok = row.last_ok
    stale = last_ok is None or (_now() - last_ok) > STALE_AFTER
    return {
        "last_success_at": last_ok.isoformat() if last_ok else None,
        "last_verified_at": row.last_verified.isoformat() if row.last_verified else None,
        "last_attempt_at": row.last_attempt.isoformat() if row.last_attempt else None,
        "failures": int(row.failures or 0),
        # True also when there has never been one, which is the state every
        # new deployment starts in and the one most worth saying out loud.
        "stale": stale,
    }
