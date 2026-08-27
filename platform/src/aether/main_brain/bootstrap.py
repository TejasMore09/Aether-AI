"""Create the first platform admin.

Chicken-and-egg: adding staff requires an admin token, and there is no admin
yet. This is the one way in, and it is deliberately a local command rather
than an endpoint — an HTTP route that mints the first superuser is a route
that has to be right forever, including on the day someone forgets to disable
it. A command needs shell access to the deployment.

    python -m aether.main_brain.bootstrap you@company.com --role admin

Refuses to run once any admin exists; from then on staff are added through
POST /v1/staff by someone already accountable.
"""

import argparse
import getpass
import sys

from sqlalchemy import func, select

from aether.core.db import session as plain_session
from aether.core.models import PlatformAdmin, StaffRole
from aether.core.staff import create_admin, record

MIN_PASSWORD = 12


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create the first Aether platform admin.")
    parser.add_argument("email")
    parser.add_argument(
        "--role",
        default=StaffRole.admin.value,
        choices=[r.value for r in StaffRole],
    )
    parser.add_argument("--name", default="")
    args = parser.parse_args(argv)

    with plain_session() as db:
        existing = db.scalar(select(func.count(PlatformAdmin.id)))
    if existing:
        print(
            f"{existing} platform admin(s) already exist. "
            "Add more through POST /v1/staff so the action is attributable.",
            file=sys.stderr,
        )
        return 1

    password = getpass.getpass("Password: ")
    if len(password) < MIN_PASSWORD:
        print(f"Use at least {MIN_PASSWORD} characters.", file=sys.stderr)
        return 1
    if password != getpass.getpass("Confirm: "):
        print("Passwords did not match.", file=sys.stderr)
        return 1

    admin = create_admin(args.email, password, StaffRole(args.role), args.name)
    record(admin.email, "staff.bootstrap", details={"role": admin.role.value})
    print(f"Created {admin.email} as {admin.role.value}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
