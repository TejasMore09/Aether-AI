"""Running backups, by hand or on a schedule.

    python -m aether.ops backup            take one, verify it, prune
    python -m aether.ops verify <file>     prove an existing file
    python -m aether.ops schedule          the loop the deployment runs

**A loop rather than cron**, which is a deliberate choice and not the obvious
one. Cron is the right tool on a machine somebody administers; in a container
it means a second process supervisor, a second place logs go, and a failure
mode where the schedule stops and the container stays cheerfully healthy. The
loop is one process that either runs or does not, and its failures are faults
like every other (6.3).

The cost is that the schedule restarts with the container, so a machine
rebooted daily at the wrong moment could keep missing a backup. The staleness
alarm in `status()` is what catches that: two days without a verified backup
and the platform says so rather than waiting to be asked.
"""

from __future__ import annotations

import argparse
import sys
import time

from aether.core import logs
from aether.core.config import get_settings
from aether.ops import backup


def _one_cycle(settings) -> int:
    outcome = backup.run_cycle(
        settings.backup_dir, keep=settings.backup_keep, url=settings.migration_database_url or None
    )
    verified = "verified" if outcome["verified"] else "NOT verified"
    print(f"{outcome['status']}: {verified} — {outcome.get('detail', '') or 'no problems'}")
    return 0 if outcome["status"] == "ok" else 1


def main(argv: list[str] | None = None) -> int:
    logs.configure("backup")
    settings = get_settings()

    parser = argparse.ArgumentParser(prog="aether.ops")
    parser.add_argument("action", choices=("backup", "verify", "schedule"))
    parser.add_argument("path", nargs="?", help="the dump to verify")
    args = parser.parse_args(argv)

    available, why = backup.tools_available()
    if not available:
        print(f"cannot run: {why}", file=sys.stderr)
        return 2

    if args.action == "verify":
        if not args.path:
            parser.error("verify needs a path")
        result = backup.verify(args.path, url=settings.migration_database_url or None)
        for line in result.problems:
            print(f"  problem: {line}")
        for name, check in result.checks.items():
            print(f"  {name}: {'ok' if check.get('ok') else 'FAILED'}")
        return 0 if result.ok else 1

    if args.action == "backup":
        return _one_cycle(settings)

    interval = max(settings.backup_interval_hours, 0.25) * 3600
    print(f"backing up every {interval / 3600:.1f}h into {settings.backup_dir}")
    while True:
        # Deliberately ignoring the result: `run_cycle` never raises and has
        # already recorded and alerted. A scheduler that stops on the first
        # failure is a scheduler that stops.
        _one_cycle(settings)
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
