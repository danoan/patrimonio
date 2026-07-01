"""add net_before_taxes_avg_cents to person

Revision ID: fa2e995aa295
Revises: 5bc3c320d74d
Create Date: 2026-07-07 13:22:11.726329

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fa2e995aa295"
down_revision: str | None = "5bc3c320d74d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("person") as batch_op:
        batch_op.add_column(sa.Column("net_before_taxes_avg_cents", sa.Integer(), nullable=True))

    # Backfill with the current net_before_taxes_cents as a starting point;
    # edit in the settings page to the real 12-month average from payslips.
    op.execute("UPDATE person SET net_before_taxes_avg_cents = net_before_taxes_cents")

    with op.batch_alter_table("person") as batch_op:
        batch_op.alter_column("net_before_taxes_avg_cents", nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("person") as batch_op:
        batch_op.drop_column("net_before_taxes_avg_cents")
