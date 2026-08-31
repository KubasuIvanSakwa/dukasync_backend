"""
models.py — SQLAlchemy ORM models for DukaSync.

Entity Map:
  Shop ──< Product ──< Sale
  Supplier ──< RestockOrder ──< Product (via restock_order_id FK on RestockOrder)

Relationships:
  - A Shop owns many Products.
  - A Product belongs to one Shop and one Supplier.
  - A Sale records one unit-decrement event on a Product.
  - A Supplier can fulfill many RestockOrders.
  - A RestockOrder targets one Product and is triggered when
    product.quantity_in_stock falls below product.reorder_threshold.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

from .database import Base


# ---------------------------------------------------------------------------
# Enum: RestockOrder status machine
# ---------------------------------------------------------------------------
class RestockStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


# ---------------------------------------------------------------------------
# Shop
# ---------------------------------------------------------------------------
class Shop(Base):
    __tablename__ = "shops"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255))
    owner_name: Mapped[str | None] = mapped_column(String(120))
    owner_phone: Mapped[str | None] = mapped_column(String(20))
    phone = synonym("owner_phone")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # One shop → many products
    products: Mapped[list[Product]] = relationship(
        "Product", back_populates="shop", cascade="all, delete-orphan"
    )
    sales: Mapped[list[Sale]] = relationship("Sale", back_populates="shop")
    restock_orders: Mapped[list[RestockOrder]] = relationship(
        "RestockOrder", back_populates="shop"
    )
    users: Mapped[list[User]] = relationship(
        "User", back_populates="shop", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Shop id={self.id} name={self.name!r}>"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    shop_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="owner")

    shop: Mapped[Shop] = relationship("Shop", back_populates="users")

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} shop_id={self.shop_id}>"


# ---------------------------------------------------------------------------
# Supplier
# ---------------------------------------------------------------------------
class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(120))
    contact_phone: Mapped[str | None] = mapped_column(String(20))
    phone = synonym("contact_phone")
    email: Mapped[str | None] = mapped_column(String(120))
    webhook_url: Mapped[str | None] = mapped_column(String(2048))
    lead_time_days: Mapped[int] = mapped_column(Integer, default=3)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # One supplier → many products & restock orders
    products: Mapped[list[Product]] = relationship(
        "Product", back_populates="supplier"
    )
    restock_orders: Mapped[list[RestockOrder]] = relationship(
        "RestockOrder", back_populates="supplier"
    )

    def __repr__(self) -> str:
        return f"<Supplier id={self.id} name={self.name!r}>"


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------
class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("shop_id", "sku", name="uq_products_shop_sku"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    shop_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("suppliers.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(60), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0)
    current_stock: Mapped[int] = mapped_column(Integer, default=0)
    quantity_in_stock = synonym("current_stock")
    reorder_threshold: Mapped[int] = mapped_column(Integer, default=10)
    reorder_quantity: Mapped[int] = mapped_column(Integer, default=50)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    shop: Mapped[Shop] = relationship("Shop", back_populates="products")
    supplier: Mapped[Supplier | None] = relationship(
        "Supplier", back_populates="products"
    )
    sales: Mapped[list[Sale]] = relationship(
        "Sale", back_populates="product", cascade="all, delete-orphan"
    )
    restock_orders: Mapped[list[RestockOrder]] = relationship(
        "RestockOrder", back_populates="product"
    )

    @property
    def is_low_stock(self) -> bool:
        """True when current stock is at or below the reorder threshold."""
        return self.quantity_in_stock <= self.reorder_threshold

    def __repr__(self) -> str:
        return (
            f"<Product id={self.id} sku={self.sku!r} "
            f"qty={self.quantity_in_stock} threshold={self.reorder_threshold}>"
        )


class StockAdjustment(Base):
    __tablename__ = "stock_adjustments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shop_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quantity_change: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ---------------------------------------------------------------------------
# Sale
# ---------------------------------------------------------------------------
class Sale(Base):
    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shop_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_sold = synonym("quantity")
    total_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    sale_price = synonym("total_price")
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    sold_at = synonym("timestamp")
    notes: Mapped[str | None] = mapped_column(Text)

    # Relationship
    shop: Mapped[Shop] = relationship("Shop", back_populates="sales")
    product: Mapped[Product] = relationship("Product", back_populates="sales")

    def __repr__(self) -> str:
        return f"<Sale id={self.id} product_id={self.product_id} qty={self.quantity_sold}>"


# ---------------------------------------------------------------------------
# RestockOrder
# ---------------------------------------------------------------------------
class RestockOrder(Base):
    __tablename__ = "restock_orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    shop_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("suppliers.id", ondelete="SET NULL"), index=True
    )
    quantity_ordered: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[RestockStatus] = mapped_column(
        Enum(RestockStatus), default=RestockStatus.PENDING, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    triggered_at = synonym("created_at")
    expected_delivery: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    # Relationships
    shop: Mapped[Shop | None] = relationship("Shop", back_populates="restock_orders")
    product: Mapped[Product] = relationship("Product", back_populates="restock_orders")
    supplier: Mapped[Supplier | None] = relationship(
        "Supplier", back_populates="restock_orders"
    )

    def __repr__(self) -> str:
        return (
            f"<RestockOrder id={self.id} product_id={self.product_id} "
            f"qty={self.quantity_ordered} status={self.status}>"
        )
