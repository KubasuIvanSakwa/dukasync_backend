"""
main.py — DukaSync FastAPI application entry point.

Route layout:
  /api/shops           — CRUD for shops
  /api/suppliers       — CRUD for suppliers
  /api/products        — CRUD for products + low-stock list
  /api/sales           — Record a sale (triggers low-stock check)
  /api/restock-orders  — CRUD + status updates for restock orders
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .database import Base, engine, get_db
from .models import Product, RestockOrder, RestockStatus, Sale, Shop, StockAdjustment, Supplier, User
from .auth import get_current_user, require_shop_access, router as auth_router
from .tasks import check_and_create_restock_order
from .schemas import (
    LowStockAlert,
    ProductCreate,
    ProductOut,
    ProductUpdate,
    RestockOrderCreate,
    RestockOrderOut,
    RestockOrderDetail,
    RestockOrderUpdate,
    SaleCreate,
    SaleOut,
    ShopCreate,
    ShopOut,
    ShopUpdate,
    SupplierCreate,
    SupplierOut,
    SupplierUpdate,
    StockAdjustmentCreate,
)

# ---------------------------------------------------------------------------
# App init
# ---------------------------------------------------------------------------
app = FastAPI(
    title="DukaSync API",
    description="Inventory and restocking coordination for small Kenyan retailers.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.on_event("startup")
async def create_tables() -> None:
    """Create all tables on startup (dev convenience — use Alembic in prod)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ===========================================================================
# Shops
# ===========================================================================
@app.post("/shops/", response_model=ShopOut, status_code=status.HTTP_201_CREATED, tags=["Shops"])
@app.post("/api/shops", response_model=ShopOut, status_code=status.HTTP_201_CREATED, tags=["Shops"])
async def create_shop(payload: ShopCreate, db: AsyncSession = Depends(get_db)) -> Shop:
    shop = Shop(**payload.model_dump())
    db.add(shop)
    await db.flush()
    await db.refresh(shop)
    return shop


@app.get("/api/shops", response_model=List[ShopOut], tags=["Shops"])
async def list_shops(db: AsyncSession = Depends(get_db)) -> list[Shop]:
    result = await db.execute(select(Shop))
    return result.scalars().all()


@app.get("/api/shops/{shop_id}", response_model=ShopOut, tags=["Shops"])
async def get_shop(shop_id: int, db: AsyncSession = Depends(get_db)) -> Shop:
    shop = await db.get(Shop, shop_id)
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return shop


@app.get("/shops/{shop_id}/inventory", response_model=List[ProductOut], tags=["Shops"])
async def get_shop_inventory(
    shop_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Product]:
    shop = await db.get(Shop, shop_id)
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    require_shop_access(shop_id, current_user)
    result = await db.execute(
        select(Product).where(Product.shop_id == shop_id).order_by(Product.name)
    )
    return result.scalars().all()


@app.patch("/api/shops/{shop_id}", response_model=ShopOut, tags=["Shops"])
async def update_shop(
    shop_id: int, payload: ShopUpdate, db: AsyncSession = Depends(get_db)
) -> Shop:
    shop = await db.get(Shop, shop_id)
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(shop, field, value)
    await db.flush()
    await db.refresh(shop)
    return shop


@app.delete("/api/shops/{shop_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Shops"])
async def delete_shop(shop_id: int, db: AsyncSession = Depends(get_db)) -> None:
    shop = await db.get(Shop, shop_id)
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    await db.delete(shop)


# ===========================================================================
# Suppliers
# ===========================================================================
@app.post("/api/suppliers", response_model=SupplierOut, status_code=status.HTTP_201_CREATED, tags=["Suppliers"])
async def create_supplier(payload: SupplierCreate, db: AsyncSession = Depends(get_db)) -> Supplier:
    supplier = Supplier(**payload.model_dump())
    db.add(supplier)
    await db.flush()
    await db.refresh(supplier)
    return supplier


@app.get("/api/suppliers", response_model=List[SupplierOut], tags=["Suppliers"])
async def list_suppliers(db: AsyncSession = Depends(get_db)) -> list[Supplier]:
    result = await db.execute(select(Supplier))
    return result.scalars().all()


@app.get("/api/suppliers/{supplier_id}", response_model=SupplierOut, tags=["Suppliers"])
async def get_supplier(supplier_id: int, db: AsyncSession = Depends(get_db)) -> Supplier:
    supplier = await db.get(Supplier, supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return supplier


@app.patch("/api/suppliers/{supplier_id}", response_model=SupplierOut, tags=["Suppliers"])
async def update_supplier(
    supplier_id: int, payload: SupplierUpdate, db: AsyncSession = Depends(get_db)
) -> Supplier:
    supplier = await db.get(Supplier, supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(supplier, field, value)
    await db.flush()
    await db.refresh(supplier)
    return supplier


# ===========================================================================
# Products
# ===========================================================================
@app.post("/products/", response_model=ProductOut, status_code=status.HTTP_201_CREATED, tags=["Products"])
@app.post("/api/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED, tags=["Products"])
async def create_product(
    payload: ProductCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Product:
    shop = await db.get(Shop, payload.shop_id)
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    require_shop_access(payload.shop_id, current_user)
    if payload.supplier_id is not None and not await db.get(Supplier, payload.supplier_id):
        raise HTTPException(status_code=404, detail="Supplier not found")
    product = Product(**payload.model_dump())
    db.add(product)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if "uq_products_shop_sku" in str(exc) or "products.sku" in str(exc):
            raise HTTPException(status_code=409, detail="SKU already exists in shop")
        raise
    await db.refresh(product)
    return product


@app.get("/api/products", response_model=List[ProductOut], tags=["Products"])
async def list_products(
    shop_id: Optional[int] = None, db: AsyncSession = Depends(get_db)
) -> list[Product]:
    query = select(Product)
    if shop_id:
        query = query.where(Product.shop_id == shop_id)
    result = await db.execute(query)
    return result.scalars().all()


@app.get("/api/products/low-stock", response_model=List[LowStockAlert], tags=["Products"])
async def list_low_stock_products(db: AsyncSession = Depends(get_db)) -> list[LowStockAlert]:
    """Returns all products where quantity_in_stock <= reorder_threshold."""
    result = await db.execute(
        select(Product).where(Product.quantity_in_stock <= Product.reorder_threshold)
    )
    products = result.scalars().all()
    return [
        LowStockAlert(
            product_id=p.id,
            product_name=p.name,
            sku=p.sku,
            quantity_in_stock=p.quantity_in_stock,
            reorder_threshold=p.reorder_threshold,
        )
        for p in products
    ]


@app.get("/api/products/{product_id}", response_model=ProductOut, tags=["Products"])
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)) -> Product:
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@app.patch("/api/products/{product_id}", response_model=ProductOut, tags=["Products"])
async def update_product(
    product_id: int, payload: ProductUpdate, db: AsyncSession = Depends(get_db)
) -> Product:
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    await db.flush()
    await db.refresh(product)
    return product


@app.patch("/products/{product_id}/stock", response_model=ProductOut, tags=["Products"])
@app.patch("/api/products/{product_id}/stock", response_model=ProductOut, tags=["Products"])
async def adjust_stock(
    product_id: int,
    payload: StockAdjustmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Product:
    result = await db.execute(
        select(Product).where(Product.id == product_id).with_for_update()
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    require_shop_access(product.shop_id, current_user)
    if product.quantity_in_stock + payload.quantity_change < 0:
        raise HTTPException(status_code=400, detail="Stock adjustment cannot make stock negative")
    product.quantity_in_stock += payload.quantity_change
    db.add(StockAdjustment(
        product_id=product.id,
        shop_id=product.shop_id,
        quantity_change=payload.quantity_change,
        reason=payload.reason,
    ))
    await db.flush()
    await db.refresh(product)
    return product


# ===========================================================================
# Sales  — core domain event; triggers low-stock check
# ===========================================================================
@app.post("/sales/", response_model=SaleOut, status_code=status.HTTP_201_CREATED, tags=["Sales"])
@app.post("/sales", response_model=SaleOut, status_code=status.HTTP_201_CREATED, tags=["Sales"], include_in_schema=False)
@app.post("/api/sales", response_model=SaleOut, status_code=status.HTTP_201_CREATED, tags=["Sales"])
async def record_sale(
    payload: SaleCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Sale:
    """
    Record a sale and decrement stock.
    If stock falls to or below reorder_threshold, auto-create a PENDING RestockOrder
    (idempotent: skips creation when one is already PENDING or CONFIRMED for this product).
    """
    result = await db.execute(
        select(Product)
        .where(Product.id == payload.product_id)
        .with_for_update()
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    require_shop_access(payload.shop_id, current_user)
    if payload.shop_id != product.shop_id:
        raise HTTPException(status_code=400, detail="Product does not belong to shop")
    if product.quantity_in_stock < payload.quantity_sold:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient stock. Available: {product.quantity_in_stock}",
        )

    # 1. Decrement stock
    product.quantity_in_stock -= payload.quantity_sold

    # 2. Persist sale record
    sale = Sale(**payload.model_dump())
    db.add(sale)
    await db.flush()  # assign sale.id before the low-stock check

    # 3. Schedule low-stock handling after this transaction commits.
    if product.is_low_stock:
        background_tasks.add_task(check_and_create_restock_order, product.id)

    await db.refresh(sale)
    return sale


@app.get("/api/sales", response_model=List[SaleOut], tags=["Sales"])
@app.get("/sales", response_model=List[SaleOut], tags=["Sales"], include_in_schema=False)
async def list_sales(
    product_id: Optional[int] = None, db: AsyncSession = Depends(get_db)
) -> list[Sale]:
    query = select(Sale)
    if product_id:
        query = query.where(Sale.product_id == product_id)
    result = await db.execute(query)
    return result.scalars().all()


# ===========================================================================
# Restock Orders
# ===========================================================================
@app.post("/api/restock-orders", response_model=RestockOrderOut, status_code=status.HTTP_201_CREATED, tags=["Restock"])
async def create_restock_order(
    payload: RestockOrderCreate, db: AsyncSession = Depends(get_db)
) -> RestockOrder:
    product = await db.get(Product, payload.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    order = RestockOrder(shop_id=product.shop_id, **payload.model_dump())
    db.add(order)
    await db.flush()
    await db.refresh(order)
    return order


@app.get("/api/restock-orders", response_model=List[RestockOrderOut], tags=["Restock"])
async def list_restock_orders(
    status_filter: Optional[RestockStatus] = None,
    db: AsyncSession = Depends(get_db),
) -> list[RestockOrder]:
    query = select(RestockOrder)
    if status_filter:
        query = query.where(RestockOrder.status == status_filter)
    result = await db.execute(query)
    return result.scalars().all()


@app.get(
    "/shops/{shop_id}/restock-orders",
    response_model=List[RestockOrderDetail],
    tags=["Restock"],
)
async def list_shop_restock_orders(
    shop_id: int,
    status_filter: Optional[RestockStatus] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    shop = await db.get(Shop, shop_id)
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    require_shop_access(shop_id, current_user)
    query = (
        select(RestockOrder, Product.name, Supplier.name)
        .join(Product, RestockOrder.product_id == Product.id)
        .outerjoin(Supplier, RestockOrder.supplier_id == Supplier.id)
        .where(RestockOrder.shop_id == shop_id)
        .order_by(RestockOrder.created_at.desc())
    )
    if status_filter:
        query = query.where(RestockOrder.status == status_filter)
    rows = (await db.execute(query)).all()
    return [
        {
            **RestockOrderOut.model_validate(order).model_dump(),
            "product_name": product_name,
            "supplier_name": supplier_name,
        }
        for order, product_name, supplier_name in rows
    ]


@app.patch(
    "/shops/{shop_id}/restock-orders/{order_id}/receive",
    response_model=RestockOrderOut,
    tags=["Restock"],
)
async def receive_restock_order(
    shop_id: int,
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RestockOrder:
    require_shop_access(shop_id, current_user)
    result = await db.execute(
        select(RestockOrder)
        .where(RestockOrder.id == order_id, RestockOrder.shop_id == shop_id)
        .with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Restock order not found")
    if order.status == RestockStatus.DELIVERED:
        return order
    product = await db.get(Product, order.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.quantity_in_stock += order.quantity_ordered
    order.status = RestockStatus.DELIVERED
    await db.flush()
    await db.refresh(order)
    return order


@app.patch("/api/restock-orders/{order_id}", response_model=RestockOrderOut, tags=["Restock"])
async def update_restock_order(
    order_id: int, payload: RestockOrderUpdate, db: AsyncSession = Depends(get_db)
) -> RestockOrder:
    order = await db.get(RestockOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="RestockOrder not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(order, field, value)
    await db.flush()
    await db.refresh(order)
    return order
