"""add accountvaluation table

Revision ID: 711d278f96eb
Revises: fa2e995aa295
Create Date: 2026-07-07 14:13:40.754343

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "711d278f96eb"
down_revision: str | None = "fa2e995aa295"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accountvaluation",
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("period", sa.String(), nullable=False),
        sa.Column("balance_cents", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"]),
        sa.PrimaryKeyConstraint("account_id", "period"),
    )


def downgrade() -> None:
    op.drop_table("accountvaluation")
