"""person ir_rate replaces ir_cents and personal_cents

Revision ID: c2e5ec2655b5
Revises: a60a75947b00
Create Date: 2026-07-04 15:48:47.581210

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2e5ec2655b5"
down_revision: str | None = "a60a75947b00"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("person") as batch_op:
        batch_op.add_column(sa.Column("ir_rate", sa.Float(), nullable=True))

    op.execute(
        "UPDATE person SET ir_rate = CAST(ir_cents AS FLOAT) / gross_cents WHERE gross_cents > 0"
    )
    op.execute("UPDATE person SET ir_rate = 0.0 WHERE ir_rate IS NULL")

    with op.batch_alter_table("person") as batch_op:
        batch_op.alter_column("ir_rate", nullable=False)
        batch_op.drop_column("ir_cents")
        batch_op.drop_column("personal_cents")


def downgrade() -> None:
    with op.batch_alter_table("person") as batch_op:
        batch_op.add_column(sa.Column("ir_cents", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("personal_cents", sa.Integer(), nullable=True))

    op.execute("UPDATE person SET ir_cents = CAST(gross_cents * ir_rate AS INTEGER)")
    # personal_cents was replaced by an inferred value and cannot be recovered.
    op.execute("UPDATE person SET personal_cents = 0")

    with op.batch_alter_table("person") as batch_op:
        batch_op.alter_column("ir_cents", nullable=False)
        batch_op.alter_column("personal_cents", nullable=False)
        batch_op.drop_column("ir_rate")
