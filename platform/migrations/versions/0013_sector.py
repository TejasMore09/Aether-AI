"""What kind of business this is.

Revision ID: 0013

Phase 3.1. Until now a stock brokerage and a bakery received byte-identical
packs, which is the specific gap the vision called out. This is the hook to
hang the rest of Phase 3 on: 3.2 layers per-sector bands over pack defaults,
3.4 gives an agent industry knowledge, 3.6 tells the customer where each band
came from.

The taxonomy itself lives in `domains/sectors.yaml`, not in the database.
Sectors are claims about how businesses group -- the same kind of thing as a
domain pack or `relations.yaml` -- and belong somewhere a person can read the
reasoning and correct it, under review, rather than in rows nobody sees.

Stored as text rather than an enum for the same reason the throttle scope is:
adding a sector should be a pull request against a YAML file, not a migration
every deployment has to apply in lockstep.

'other' rather than NULL as the default. A business that has not chosen and a
business that does not fit are the same situation from the product's side, and
one representation for one situation avoids every caller having to remember
which of the two it is holding.
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("sector", sa.String(40), nullable=False, server_default="other"),
    )


def downgrade() -> None:
    op.drop_column("tenants", "sector")
