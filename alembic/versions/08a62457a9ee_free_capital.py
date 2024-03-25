"""free capital

Revision ID: 08a62457a9ee
Revises: 62c1d05d2134
Create Date: 2024-03-25 12:48:31.219581

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "08a62457a9ee"
down_revision: Union[str, None] = "62c1d05d2134"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "share_strategy",
        sa.Column("free_capital", sa.Float(), default=0.0),
    )


def downgrade() -> None:
    op.drop_column("share_strategy", "free_capital")
