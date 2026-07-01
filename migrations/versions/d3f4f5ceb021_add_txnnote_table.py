"""add txnnote table

Revision ID: d3f4f5ceb021
Revises: 58acbef039a3
Create Date: 2026-07-10 00:10:56.822231

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3f4f5ceb021"
down_revision: str | None = "58acbef039a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "txnnote",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("txn_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["txn_id"], ["txn.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("txnnote")
