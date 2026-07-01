"""add resolution tracking fields to txn

Revision ID: 62ffbe44ad3b
Revises: c2e5ec2655b5
Create Date: 2026-07-04 23:01:16.431480

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "62ffbe44ad3b"
down_revision: str | None = "c2e5ec2655b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "txn",
        sa.Column("needs_resolution", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "txn",
        sa.Column("resolved_txn_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "txn",
        sa.Column("resolution_note", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("txn", "resolution_note")
    op.drop_column("txn", "resolved_txn_id")
    op.drop_column("txn", "needs_resolution")
