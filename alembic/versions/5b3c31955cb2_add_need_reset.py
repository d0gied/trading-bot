"""add need reset

Revision ID: 5b3c31955cb2
Revises: 6cc59238cd99
Create Date: 2024-03-25 14:59:17.992809

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5b3c31955cb2"
down_revision: Union[str, None] = "6cc59238cd99"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "share_strategy", sa.Column("need_reset", sa.Boolean(), default=False)
    )
    op.execute("UPDATE share_strategy SET need_reset = false")


def downgrade() -> None:
    pass
