"""add net_before_taxes_cents to person

Revision ID: 5bc3c320d74d
Revises: 07dadb45adca
Create Date: 2026-07-07 13:15:35.193051

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5bc3c320d74d"
down_revision: str | None = "07dadb45adca"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("person") as batch_op:
        batch_op.add_column(sa.Column("net_before_taxes_cents", sa.Integer(), nullable=True))

    # Backfill with gross_cents as a starting point; edit in the settings
    # page to the real net-imposable figure from the payslip.
    op.execute("UPDATE person SET net_before_taxes_cents = gross_cents")

    with op.batch_alter_table("person") as batch_op:
        batch_op.alter_column("net_before_taxes_cents", nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("person") as batch_op:
        batch_op.drop_column("net_before_taxes_cents")
