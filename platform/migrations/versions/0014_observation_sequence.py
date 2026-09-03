"""A definite answer to "which reading is the current one".

Revision ID: 0014

Found by an intermittent test, and it was a product bug rather than a test
one. The monitor evaluates the latest reading for a domain, ordered by
`observed_at`. Two readings can carry the same `observed_at` — a connector
posting a batch, a source with second precision, or simply a coarse system
clock — and `created_at` can tie with it, because both come from the same call
to the clock.

With both equal there was nothing left to order by, so the database returned
whichever row it liked. Measured on this machine: two readings recorded
back to back collided about a quarter of the time, and the wrong one was then
evaluated in half of those. The same data gated an action or did not, roughly
one time in eight.

A monotonic sequence is the only thing that can settle it. `observed_at` says
when the reading refers to and is the customer's fact; `seq` says when we were
told, and is ours. Latest observation wins, and where two claim the same
moment the later-arriving one does — because it is the later information about
that moment, which is what an amendment or a correction looks like.

Not a unique constraint on (tenant, domain, observed_at): resending a reading
for a moment already recorded is a legitimate correction, and refusing it
would turn a fixable mistake into a permanent one.
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # BIGSERIAL backfills existing rows in physical order, which is the best
    # available guess at insertion order for readings recorded before this.
    op.add_column("observations", sa.Column("seq", sa.BigInteger(), nullable=False, server_default=sa.text("0")))
    op.execute("CREATE SEQUENCE observations_seq_seq OWNED BY observations.seq")
    op.execute("SELECT setval('observations_seq_seq', coalesce((SELECT count(*) FROM observations), 0) + 1)")
    op.execute("UPDATE observations SET seq = nextval('observations_seq_seq')")
    op.execute("ALTER TABLE observations ALTER COLUMN seq SET DEFAULT nextval('observations_seq_seq')")
    # The app connects as a non-owner role, so a new sequence is unusable to it
    # until said otherwise. 0001 grants table privileges and default privileges
    # for future tables; sequences were not covered, because until now there
    # were none.
    op.execute("GRANT USAGE, SELECT ON SEQUENCE observations_seq_seq TO aether_app")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT USAGE, SELECT ON SEQUENCES TO aether_app"
    )

    # The index the "latest reading" query actually uses, in its exact order.
    op.create_index(
        "ix_obs_tenant_domain_latest",
        "observations",
        ["tenant_id", "domain", "observed_at", "seq"],
    )


def downgrade() -> None:
    op.drop_index("ix_obs_tenant_domain_latest", table_name="observations")
    op.drop_column("observations", "seq")
    op.execute("DROP SEQUENCE IF EXISTS observations_seq_seq")
