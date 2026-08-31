"""
schemas.py — Pydantic v2 request/response schemas for DukaSync.

Naming convention:
  <Entity>Base    — shared fields
  <Entity>Create  — fields required on POST (no id / timestamps)
  <Entity>Update  — all fields optional for PATCH
  <Entity>Out     — full read schema returned to the client
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .models import RestockStatus


# ---------------------------------------------------------------------------
# Shared config mixin: enables ORM mode for all read schemas
# ---------------------------------------------------------------------------
class _OrmBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ===========================================================================
# Shop
# ===========================================================================
class ShopBase(BaseModel):
    name: str = Field(..., max_length=120)
    location: Optional[str] = Field(None, max_length=255)
    owner_name: Optional[str] = Field(None, max_length=120)
    phone: Optional[str] = Field(None, max_length=20)


class ShopCreate(ShopBase):
    pass


class ShopUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=120)
    location: Optional[str] = None
    owner_name: Optional[str] = None
    phone: Optional[str] = None


class ShopOut(_OrmBase, ShopBase):
    id: int
    created_at: datetime


# ===========================================================================
# Supplier
# ===========================================================================
class SupplierBase(BaseModel):
    name: str = Field(..., max_length=120)
    contact_name: Optional[str] = Field(None, max_length=120)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = None
    lead_time_days: int = Field(3, ge=0)


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    lead_time_days: Optional[int] = Field(None, ge=0)


class SupplierOut(_OrmBase, SupplierBase):
    id: int
    created_at: datetime


# ===========================================================================
# Product
# ===========================================================================
class ProductBase(BaseModel):
    name: str = Field(..., max_length=180)
    sku: Optional[str] = Field(None, max_length=60)
    description: Optional[str] = None
    unit_price: float = Field(0.0, ge=0)
    quantity_in_stock: int = Field(0, ge=0)
    reorder_threshold: int = Field(10, ge=0)
    reorder_quantity: int = Field(50, ge=1)


class ProductCreate(ProductBase):
    shop_id: int
    supplier_id: Optional[int] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    sku: Optional[str] = None
    description: Optional[str] = None
    unit_price: Optional[float] = Field(None, ge=0)
    quantity_in_stock: Optional[int] = Field(None, ge=0)
    reorder_threshold: Optional[int] = Field(None, ge=0)
    reorder_quantity: Optional[int] = Field(None, ge=1)
    supplier_id: Optional[int] = None


class StockAdjustmentCreate(BaseModel):
    quantity_change: int
    reason: str = Field(..., min_length=1, max_length=255)


class ProductOut(_OrmBase, ProductBase):
    id: int
    shop_id: int
    supplier_id: Optional[int]
    is_low_stock: bool
    created_at: datetime
    updated_at: datetime


# ===========================================================================
# Sale
# ===========================================================================
class SaleBase(BaseModel):
    shop_id: int
    product_id: int
    quantity_sold: int = Field(..., gt=0)
    sale_price: float = Field(..., ge=0)
    notes: Optional[str] = None

    @field_validator("quantity_sold")
    @classmethod
    def qty_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("quantity must be greater than 0")
        return v


class SaleCreate(SaleBase):
    pass


class SaleOut(_OrmBase, SaleBase):
    id: int
    sold_at: datetime


# ===========================================================================
# RestockOrder
# ===========================================================================
class RestockOrderBase(BaseModel):
    product_id: int
    supplier_id: Optional[int] = None
    quantity_ordered: int = Field(..., ge=1)
    status: RestockStatus = RestockStatus.PENDING
    notes: Optional[str] = None


class RestockOrderCreate(RestockOrderBase):
    pass


class RestockOrderUpdate(BaseModel):
    status: Optional[RestockStatus] = None
    quantity_ordered: Optional[int] = Field(None, ge=1)
    expected_delivery: Optional[datetime] = None
    notes: Optional[str] = None


class RestockOrderOut(_OrmBase, RestockOrderBase):
    id: int
    triggered_at: datetime
    created_at: datetime
    expected_delivery: Optional[datetime]


class RestockOrderDetail(RestockOrderOut):
    product_name: str
    supplier_name: Optional[str]


# ===========================================================================
# Low-Stock Alert (read-only response shape)
# ===========================================================================
class LowStockAlert(BaseModel):
    product_id: int
    product_name: str
    sku: Optional[str]
    quantity_in_stock: int
    reorder_threshold: int
    restock_order_id: Optional[int] = None
    message: str = "Stock level is at or below reorder threshold."
