"""add notes to recurringrule

Revision ID: 07dadb45adca
Revises: 62ffbe44ad3b
Create Date: 2026-07-05 00:23:34.813928

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "07dadb45adca"
down_revision: str | None = "62ffbe44ad3b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "recurringrule",
        sa.Column("notes", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("recurringrule", "notes")
