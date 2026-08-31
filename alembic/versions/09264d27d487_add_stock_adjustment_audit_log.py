"""add stock adjustment audit log

Revision ID: 09264d27d487
Revises: c6ee9494a6db
Create Date: 2026-08-28 20:04:34.724247

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '09264d27d487'
down_revision: Union[str, None] = 'c6ee9494a6db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stock_adjustments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("shop_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity_change", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_stock_adjustments_id", "stock_adjustments", ["id"], unique=False)
    op.create_index("ix_stock_adjustments_product_id", "stock_adjustments", ["product_id"], unique=False)
    op.create_index("ix_stock_adjustments_shop_id", "stock_adjustments", ["shop_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_stock_adjustments_shop_id", table_name="stock_adjustments")
    op.drop_index("ix_stock_adjustments_product_id", table_name="stock_adjustments")
    op.drop_index("ix_stock_adjustments_id", table_name="stock_adjustments")
    op.drop_table("stock_adjustments")
