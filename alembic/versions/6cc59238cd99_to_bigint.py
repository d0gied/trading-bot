"""to bigint

Revision ID: 6cc59238cd99
Revises: 08a62457a9ee
Create Date: 2024-03-25 14:50:58.124347

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6cc59238cd99"
down_revision: Union[str, None] = "08a62457a9ee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("orders", "price_units", type_=sa.BigInteger())
    op.alter_column("orders", "price_nanos", type_=sa.BigInteger())


def downgrade() -> None:
    op.alter_column("orders", "price_units", type_=sa.Integer())
    op.alter_column("orders", "price_nanos", type_=sa.Integer())
