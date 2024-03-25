"""add warmup column to strategies

Revision ID: 62c1d05d2134
Revises: 67db9cc4e401
Create Date: 2024-03-25 11:25:08.455272

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "62c1d05d2134"
down_revision: Union[str, None] = "67db9cc4e401"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "share_strategy",
        sa.Column("warmed_up", sa.Boolean(), default=False),
    )


def downgrade() -> None:
    op.drop_column("share_strategy", "warmed_up")
