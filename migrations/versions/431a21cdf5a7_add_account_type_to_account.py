"""add account_type to account

Revision ID: 431a21cdf5a7
Revises: 711d278f96eb
Create Date: 2026-07-07 15:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "431a21cdf5a7"
down_revision: str | None = "711d278f96eb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("account") as batch_op:
        batch_op.add_column(
            sa.Column("account_type", sa.String(), nullable=False, server_default="checking")
        )
    with op.batch_alter_table("account") as batch_op:
        batch_op.alter_column("account_type", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("account") as batch_op:
        batch_op.drop_column("account_type")
