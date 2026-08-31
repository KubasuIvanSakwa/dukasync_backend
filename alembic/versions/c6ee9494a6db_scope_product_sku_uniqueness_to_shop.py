"""scope product sku uniqueness to shop

Revision ID: c6ee9494a6db
Revises: d887c8b94c13
Create Date: 2026-08-28 15:57:04.933411

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c6ee9494a6db'
down_revision: Union[str, None] = 'd887c8b94c13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_products_sku", table_name="products")
    op.create_unique_constraint(
        "uq_products_shop_sku", "products", ["shop_id", "sku"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_products_shop_sku", "products", type_="unique")
    op.create_index("ix_products_sku", "products", ["sku"], unique=True)
