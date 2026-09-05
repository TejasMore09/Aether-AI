"""Backups, and whether the thing that checks them would actually notice.

Requires the dev database and the postgres command-line tools.

A backup test that takes a dump and asserts the file is non-empty proves
nothing at all — the failure this feature exists to prevent produces a
perfectly good file. Three things were measured while building this:

- `pg_dump` run as the **application** role hits row-level security, prints an
  error, **exits 0**, and writes a plausible file containing not one row
  belonging to any tenant;
- `pg_restore` prints errors and **exits 0** as well;
- `pg_stat_user_tables.n_live_tup`, the cheap way to count rows, is an
  estimate that read 4,331 against a true 55,839 on this database.

So the tests below go after the checker rather than the backup. The important
ones deliberately hand `verify` something broken and insist it says so, because
a verifier that only ever reports success is indistinguishable from one that
returns True.
"""

import subprocess
import uuid

import pytest
import sqlalchemy
from sqlalchemy import text

from aether.core.db import get_engine
from aether.core.db import session as plain_session
from aether.core.models import RLS_TABLES
from aether.ops import backup

pytestmark = pytest.mark.postgres

# The owner connection. Backups need it, and the point of half this file is
# what happens when something uses the application role instead.
OWNER_URL = "postgresql+psycopg://aether:aether_dev_only@localhost:5433/aether"
APP_URL = "postgresql+psycopg://aether_app:aether_app_dev_only@localhost:5433/aether"


@pytest.fixture(scope="module", autouse=True)
def database():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except sqlalchemy.exc.OperationalError:
        pytest.skip("Postgres not reachable — start it with: docker compose up -d db")

    available, why = backup.tools_available()
    if not available:
        pytest.skip(f"postgres client tools unavailable: {why}")


@pytest.fixture(scope="module")
def dump(tmp_path_factory, database):
    """One real dump of the real development database, made once."""
    return backup.create(tmp_path_factory.mktemp("dumps"), url=OWNER_URL)


# ── Taking one ────────────────────────────────────────────────────────────────


def test_a_backup_produces_a_file_that_can_be_recognised_again(dump):
    assert dump.path.exists()
    assert dump.size_bytes > 10_000, "a dump of this database should not be tiny"
    assert len(dump.sha256) == 64, "so a copy elsewhere can be shown to be this file"


def test_a_backup_taken_as_the_application_role_is_refused(tmp_path):
    """The failure this whole feature exists to prevent.

    Row-level security does exactly what it was built to do and makes the
    resulting file look like a backup: measured, `pg_dump` as this role prints
    one error, exits 0, and writes 54 KB of schema with no tenant's rows in it.
    Nothing downstream would notice.
    """
    with pytest.raises(backup.BackupError) as caught:
        backup.create(tmp_path, url=APP_URL)

    assert "row-level security" in str(caught.value).lower()
    assert list(tmp_path.glob("*.dump")) == [], "and the bad file is not left behind"


def test_a_backup_without_an_owner_connection_refuses_rather_than_guessing(monkeypatch, tmp_path):
    """Falling back to the application role would be the friendly thing to do
    and would produce exactly the empty backup above."""
    monkeypatch.setattr(backup.get_settings(), "migration_database_url", "", raising=False)
    with pytest.raises(backup.BackupError) as caught:
        backup.create(tmp_path)
    assert "AETHER_MIGRATION_DATABASE_URL" in str(caught.value)


# ── Proving one ───────────────────────────────────────────────────────────────


def test_a_real_backup_verifies(dump):
    """The restore is performed, not inspected: the file is loaded into a
    scratch database and that database is then asked questions."""
    result = backup.verify(dump.path, url=OWNER_URL)
    assert result.ok, result.problems

    assert result.checks["revision"]["ok"]
    assert result.checks["tables"]["ok"]
    assert result.checks["rows"]["ok"]
    assert result.checks["extensions"]["ok"]


def test_the_restore_carries_row_level_security(dump):
    """The check that matters most, and the one whose absence would be
    invisible. A restored database with the tables and not the policies is one
    where every tenant can read every other tenant, and it looks entirely
    normal from the outside."""
    result = backup.verify(dump.path, url=OWNER_URL)
    rls = result.checks["row_level_security"]

    assert rls["unprotected"] == []
    assert rls["protected"] == len(RLS_TABLES), (
        f"every table with a policy in the source must have one in the restore: {rls}"
    )


def test_the_row_counts_are_exact_rather_than_estimated(dump):
    """`n_live_tup` was the first version of this and it is an estimate — it
    read 4,331 rows in the source against 55,839 in the restore, the same data.
    An estimate that reads zero for a populated table makes the emptiness check
    silently skip the table it exists to protect."""
    result = backup.verify(dump.path, url=OWNER_URL)
    rows = result.checks["rows"]

    # Counted through a different route than the verifier uses, so this is a
    # check rather than a restatement — and through the *owner* connection,
    # because the ordinary session is the application role and row-level
    # security refuses to count a table it has no tenant context for. Which is
    # the same mechanism that empties a careless backup.
    owner = sqlalchemy.create_engine(OWNER_URL)
    with owner.connect() as conn:
        observations = conn.execute(text("SELECT count(*) FROM observations")).scalar_one()
    owner.dispose()

    assert rows["restored_total"] >= observations > 0
    assert rows["source_total"] == rows["restored_total"], (
        "an idle database should restore to exactly what it holds"
    )


# ── Noticing when it is wrong ─────────────────────────────────────────────────


def test_a_dump_missing_every_tenants_rows_is_caught(tmp_path):
    """Built the way a misconfiguration would build it — as the application
    role, straight through pg_dump, bypassing the refusal in `create`.

    This is the file that exits 0 and looks fine. Three independent checks
    catch it, which is the point of having more than one.
    """
    path = tmp_path / "rls-blinded.dump"
    subprocess.run(
        [
            "pg_dump",
            "--dbname",
            APP_URL.replace("postgresql+psycopg://", "postgresql://"),
            "--format=c",
            "--no-owner",
            "--no-privileges",
            "--file",
            str(path),
        ],
        capture_output=True,
        check=False,
    )
    assert path.exists() and path.stat().st_size > 0, "the premise: it really does write a file"

    result = backup.verify(path, url=OWNER_URL)

    assert not result.ok
    assert result.checks["rows"]["restored_total"] == 0
    assert result.checks["rows"]["emptied"], "tables that had rows came back empty"
    assert result.checks["row_level_security"]["unprotected"], "and without policies"
    assert any("empty" in p for p in result.problems)


def test_a_truncated_file_is_caught(dump, tmp_path):
    """Half a dump restores about half a database, which is worse than none —
    it is the version somebody might not notice they restored."""
    broken = tmp_path / "truncated.dump"
    broken.write_bytes(dump.path.read_bytes()[: dump.size_bytes // 3])

    result = backup.verify(broken, url=OWNER_URL)
    assert not result.ok, result.checks


def test_a_file_that_is_not_a_dump_at_all_is_caught(tmp_path):
    rubbish = tmp_path / "not-a-dump.dump"
    rubbish.write_bytes(b"this is not a postgres archive" * 100)
    assert not backup.verify(rubbish, url=OWNER_URL).ok


def test_a_missing_file_is_caught_without_raising(tmp_path):
    result = backup.verify(tmp_path / "never-existed.dump", url=OWNER_URL)
    assert not result.ok
    assert any("no such file" in p for p in result.problems)


def test_verification_leaves_no_scratch_database_behind(dump):
    """A half-restored copy of every customer's data, left on the machine
    because a check failed, would be a worse outcome than the failure."""
    before = _scratch_databases()
    backup.verify(dump.path, url=OWNER_URL)
    assert _scratch_databases() == before

    rubbish = dump.path.parent / "rubbish.dump"
    rubbish.write_bytes(b"nope")
    backup.verify(rubbish, url=OWNER_URL)
    assert _scratch_databases() == before, "including when the restore fails"


def _scratch_databases() -> set[str]:
    with plain_session() as db:
        rows = db.execute(
            text("SELECT datname FROM pg_database WHERE datname LIKE 'aether_verify_%'")
        ).scalars()
        return set(rows)


# ── Keeping them ──────────────────────────────────────────────────────────────


def test_pruning_keeps_the_newest_and_drops_the_rest(tmp_path):
    for day in range(1, 21):
        (tmp_path / f"aether-202601{day:02d}T000000Z.dump").write_bytes(b"x")

    gone = backup.prune(tmp_path, keep=5)

    left = sorted(p.name for p in tmp_path.glob("aether-*.dump"))
    assert len(left) == 5
    assert len(gone) == 15
    assert left[-1].startswith("aether-20260120"), "the newest are the ones kept"


def test_pruning_never_empties_the_directory(tmp_path):
    """Deleting by age alone means a backup system that has been broken for a
    month quietly removes the last good file it ever made."""
    (tmp_path / "aether-20200101T000000Z.dump").write_bytes(b"x")
    backup.prune(tmp_path, keep=0)
    assert list(tmp_path.glob("aether-*.dump")), "a floor of one, however old"


def test_pruning_ignores_files_it_did_not_write(tmp_path):
    (tmp_path / "aether-20260101T000000Z.dump").write_bytes(b"x")
    (tmp_path / "notes.txt").write_bytes(b"x")
    backup.prune(tmp_path, keep=0)
    assert (tmp_path / "notes.txt").exists()


# ── The cycle, and what it records ────────────────────────────────────────────


def test_a_full_cycle_records_what_it_proved(tmp_path):
    outcome = backup.run_cycle(tmp_path, keep=3, url=OWNER_URL)

    assert outcome["status"] == "ok", outcome["detail"]
    assert outcome["verified"] is True

    with plain_session() as db:
        row = db.execute(
            text(
                "SELECT status, verified, size_bytes, sha256, checks FROM backup_runs "
                "ORDER BY started_at DESC LIMIT 1"
            )
        ).one()

    assert row.status == "ok"
    assert row.verified is True
    assert row.size_bytes > 0
    assert len(row.sha256) == 64
    # The evidence, not just the verdict: a green result has to be auditable
    # given that neither tool's exit code can be believed.
    assert row.checks["row_level_security"]["ok"] is True
    assert row.checks["rows"]["restored_total"] > 0


def test_a_failing_cycle_is_recorded_rather_than_raised(monkeypatch, tmp_path):
    """The scheduler must not stop on a bad night. A backup system that halts
    on its first failure has failed twice."""

    def broken(*args, **kwargs):
        raise backup.BackupError("the disk is full")

    monkeypatch.setattr(backup, "create", broken)
    outcome = backup.run_cycle(tmp_path, url=OWNER_URL)  # must not raise

    assert outcome["status"] == "failed"
    assert outcome["verified"] is False
    assert "disk is full" in outcome["detail"]


def test_a_cycle_that_cannot_be_verified_is_not_reported_as_success(monkeypatch, tmp_path):
    """Making a file and being able to recover from it are different claims,
    and folding them together is how "we have backups" comes to mean nothing."""
    monkeypatch.setattr(
        backup,
        "verify",
        lambda *a, **kw: backup.Verification(ok=False, problems=["nothing came back"]),
    )
    outcome = backup.run_cycle(tmp_path, url=OWNER_URL)

    assert outcome["status"] == "failed"
    assert outcome["verified"] is False
    assert list(tmp_path.glob("*.dump")), (
        "and the file is kept — an unproven backup may still be the best thing "
        "available at three in the morning"
    )


# ── Saying so ─────────────────────────────────────────────────────────────────


def test_the_status_reports_when_a_backup_last_worked(tmp_path):
    backup.run_cycle(tmp_path, keep=2, url=OWNER_URL)
    status = backup.status()

    assert status["last_success_at"] is not None
    assert status["last_verified_at"] is not None
    assert status["stale"] is False


def test_a_platform_that_has_never_backed_up_says_it_is_stale():
    """The state every new deployment starts in, and the one most worth saying
    out loud rather than reporting as a quiet absence."""
    with plain_session() as db:
        db.execute(text("DELETE FROM backup_runs"))

    status = backup.status()
    assert status["last_success_at"] is None
    assert status["stale"] is True


def test_an_old_backup_counts_as_stale():
    """A backup system that silently stops is the classic version of this
    failure: nothing errors, and the files just stop appearing."""
    with plain_session() as db:
        db.execute(text("DELETE FROM backup_runs"))
        db.execute(
            text("""
                INSERT INTO backup_runs (id, started_at, finished_at, status, verified)
                VALUES (:id, now() - interval '5 days', now() - interval '5 days', 'ok', true)
                """),
            {"id": uuid.uuid4()},
        )

    assert backup.status()["stale"] is True


def test_health_reports_backups_and_will_not_call_the_platform_healthy_without_them():
    """ "Healthy" has to mean the operational questions came back well too. A
    platform serving requests while nothing has been backed up for a week is
    working, which is a different word."""
    from aether.core import health

    with plain_session() as db:
        db.execute(text("DELETE FROM backup_runs"))

    snapshot = health.snapshot("test")
    assert snapshot["backups"]["stale"] is True
    assert snapshot["healthy"] is False
