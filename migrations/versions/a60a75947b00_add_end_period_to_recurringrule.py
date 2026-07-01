"""add end_period to recurringrule

Revision ID: a60a75947b00
Revises: ae3df59b2480
Create Date: 2026-07-03 10:32:34.901816

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a60a75947b00"
down_revision: str | None = "ae3df59b2480"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "recurringrule",
        sa.Column("end_period", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("recurringrule", "end_period")
