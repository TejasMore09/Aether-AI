"""Money stops being dollars by assumption.

Revision ID: 0012

Phase 3.0, and a prerequisite for the rest of Phase 3 rather than polish.
Aether targets India, the US and Europe (D31), and every monetary value in the
system was USD by name. An explanation telling a Pune manufacturer they are
losing $147 a day is not slightly wrong; it is a number they cannot check
against anything they know.

**A tenant has one currency and the platform never converts.** No FX rate is
stored or applied anywhere. A rate is a fact about a moment, and a stale one
silently corrupts figures that have already been shown to a customer and acted
on. Businesses report in their own currency and it stays there. Most of the
product turns out to be currency-neutral already -- DSO is days, overdue share
is a fraction -- so only the money is affected.

**The currency is copied onto each approval rather than joined from the
tenant.** If a business ever changes currency, a decision recorded last March
must keep meaning what it meant last March. Reading it through the tenant's
current setting would silently rewrite history, which is the same reasoning
that put bands on the observation rather than looking them up at read time.

**`expected_loss_usd` is renamed, `cost_usd` is not**, and the difference is
the point. The first is the customer's money and may be rupees. The second is
what a diagnosis costs *us* at the model provider, billed in USD whoever the
tenant is. Two kinds of money that were previously spelled the same.
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # USD for everything existing: it is what those numbers actually were.
    op.add_column(
        "tenants",
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
    )
    op.add_column(
        "pending_approvals",
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
    )
    op.alter_column("pending_approvals", "expected_loss_usd", new_column_name="expected_loss")


def downgrade() -> None:
    op.alter_column("pending_approvals", "expected_loss", new_column_name="expected_loss_usd")
    op.drop_column("pending_approvals", "currency")
    op.drop_column("tenants", "currency")
