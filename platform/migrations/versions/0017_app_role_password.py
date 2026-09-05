"""Give the application role a password that was not published in this repository.

Revision ID: 0017

Phase 6.1, and found by writing the deployment rather than by reading the code.

Migration 0001 creates `aether_app` with the password `aether_app_dev_only`,
which is correct for a checkout — the whole point is that `docker compose up`
and `alembic upgrade head` produce a working machine with nothing to
configure. Nothing has ever changed it since, so a production deployment would
have run its application role on a password published in a public repository.

The production configuration check refuses to start a service whose database
URL still carries that password (D60), so the two halves would have deadlocked:
the check demands a password the schema has no way to set.

**The password arrives in the environment and is never written here.** It is
passed through `set_config` and applied with `format(%L)`, which is Postgres's
own literal quoting, so it is neither interpolated into a string by Python nor
recorded in a statement that a log could keep.

**Silent when unset**, because that is the development case and re-running
migrations in a checkout must not fail for want of a variable that has no
business existing there.
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

_VARIABLE = "AETHER_APP_DB_PASSWORD"


def upgrade() -> None:
    password = os.environ.get(_VARIABLE, "")
    if not password:
        return

    connection = op.get_bind()
    # A bound parameter, so the value never appears in a SQL string Python
    # built. `ALTER ROLE ... PASSWORD` cannot take a parameter itself — it is a
    # utility statement, not a planned one — hence the round trip through a
    # session setting and Postgres's own quoting below.
    connection.execute(
        sa.text("SELECT set_config('aether.app_password', :password, true)"),
        {"password": password},
    )
    connection.execute(
        sa.text(
            "DO $$ BEGIN "
            "EXECUTE format('ALTER ROLE aether_app WITH PASSWORD %L', "
            "current_setting('aether.app_password')); "
            "END $$;"
        )
    )


def downgrade() -> None:
    # Deliberately empty. "Undoing" this would mean restoring a password that
    # is printed in migration 0001 and in the repository's history, which is
    # not a state any deployment should be able to roll back into.
    pass
