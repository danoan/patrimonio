"""add tags to recurringrule and txn

Revision ID: 58acbef039a3
Revises: 431a21cdf5a7
Create Date: 2026-07-08 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "58acbef039a3"
down_revision: str | None = "431a21cdf5a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("recurringrule") as batch_op:
        batch_op.add_column(sa.Column("tags", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    with op.batch_alter_table("txn") as batch_op:
        batch_op.add_column(sa.Column("tags", sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("txn") as batch_op:
        batch_op.drop_column("tags")
    with op.batch_alter_table("recurringrule") as batch_op:
        batch_op.drop_column("tags")
