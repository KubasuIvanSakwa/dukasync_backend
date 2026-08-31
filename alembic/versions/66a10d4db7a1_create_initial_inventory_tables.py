"""create initial inventory tables

Revision ID: 66a10d4db7a1
Revises: 
Create Date: 2026-08-28 15:32:40.235789

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '66a10d4db7a1'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    restock_status = sa.Enum(
        "PENDING",
        "CONFIRMED",
        "SHIPPED",
        "DELIVERED",
        "CANCELLED",
        name="restockstatus",
    )
    op.create_table(
        "shops",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("location", sa.String(length=255)),
        sa.Column("owner_name", sa.String(length=120)),
        sa.Column("owner_phone", sa.String(length=20)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_shops_id", "shops", ["id"], unique=False)

    op.create_table(
        "suppliers",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("contact_name", sa.String(length=120)),
        sa.Column("contact_phone", sa.String(length=20)),
        sa.Column("email", sa.String(length=120)),
        sa.Column("webhook_url", sa.String(length=2048)),
        sa.Column("lead_time_days", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_suppliers_id", "suppliers", ["id"], unique=False)

    op.create_table(
        "products",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("shop_id", sa.BigInteger(), nullable=False),
        sa.Column("supplier_id", sa.BigInteger()),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("sku", sa.String(length=60)),
        sa.Column("description", sa.Text()),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.0"),
        sa.Column("current_stock", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reorder_threshold", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("reorder_quantity", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_products_id", "products", ["id"], unique=False)
    op.create_index("ix_products_shop_id", "products", ["shop_id"], unique=False)
    op.create_index("ix_products_supplier_id", "products", ["supplier_id"], unique=False)
    op.create_index("ix_products_sku", "products", ["sku"], unique=True)

    op.create_table(
        "sales",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("shop_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("total_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("notes", sa.Text()),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_sales_id", "sales", ["id"], unique=False)
    op.create_index("ix_sales_product_id", "sales", ["product_id"], unique=False)
    op.create_index("ix_sales_shop_id", "sales", ["shop_id"], unique=False)
    op.create_index("ix_sales_timestamp", "sales", ["timestamp"], unique=False)

    op.create_table(
        "restock_orders",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("shop_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("supplier_id", sa.BigInteger()),
        sa.Column("quantity_ordered", sa.Integer(), nullable=False),
        sa.Column("status", restock_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expected_delivery", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text()),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_restock_orders_id", "restock_orders", ["id"], unique=False)
    op.create_index("ix_restock_orders_product_id", "restock_orders", ["product_id"], unique=False)
    op.create_index("ix_restock_orders_supplier_id", "restock_orders", ["supplier_id"], unique=False)
    op.create_index("ix_restock_orders_status", "restock_orders", ["status"], unique=False)


def downgrade() -> None:
    op.drop_table("restock_orders")
    op.drop_table("sales")
    op.drop_table("products")
    op.drop_table("suppliers")
    op.drop_table("shops")
    sa.Enum(name="restockstatus").drop(op.get_bind(), checkfirst=True)
