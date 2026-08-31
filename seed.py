"""Populate the database with deterministic demo inventory data."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path

from sqlalchemy import select
from passlib.context import CryptContext

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.database import AsyncSessionLocal
from backend.models import Product, Sale, Shop, Supplier, User


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
OWNER_EMAIL = "demo.owner@jiranimart.example"
OWNER_PASSWORD = "demo-password-123"


SHOP_DATA = {
    "name": "Jirani Fresh Mart",
    "location": "Westlands, Nairobi",
    "owner_name": "Amina Njeri",
    "owner_phone": "+254700123456",
}

SUPPLIER_DATA = [
    {
        "name": "Nairobi Wholesale Hub",
        "contact_name": "Peter Otieno",
        "contact_phone": "+254711234567",
        "email": "orders@nairobiwholesale.example",
        "webhook_url": "https://supplier.example.com/webhooks/restock",
        "lead_time_days": 2,
    },
    {
        "name": "Umoja Distributors",
        "contact_name": "Grace Wambui",
        "contact_phone": "+254722345678",
        "email": "sales@umojadistributors.example",
        "webhook_url": None,
        "lead_time_days": 4,
    },
]

PRODUCT_DATA = [
    {"name": "Maize Flour 2kg", "sku": "DEMO-MAIZE-2KG", "supplier": 0, "stock": 4, "threshold": 8, "price": 180, "reorder": 30},
    {"name": "White Sugar 1kg", "sku": "DEMO-SUGAR-1KG", "supplier": 1, "stock": 22, "threshold": 10, "price": 165, "reorder": 40},
    {"name": "Cooking Oil 1L", "sku": "DEMO-OIL-1L", "supplier": 0, "stock": 3, "threshold": 6, "price": 320, "reorder": 24},
    {"name": "Black Tea 100 Bags", "sku": "DEMO-TEA-100", "supplier": 1, "stock": 18, "threshold": 8, "price": 290, "reorder": 20},
    {"name": "Long-Grain Rice 2kg", "sku": "DEMO-RICE-2KG", "supplier": 0, "stock": 7, "threshold": 10, "price": 340, "reorder": 25},
    {"name": "Bar Soap 800g", "sku": "DEMO-SOAP-800", "supplier": 1, "stock": 31, "threshold": 12, "price": 125, "reorder": 36},
    {"name": "UHT Milk 500ml", "sku": "DEMO-MILK-500", "supplier": 0, "stock": 5, "threshold": 10, "price": 75, "reorder": 30},
    {"name": "Bottled Water 1.5L", "sku": "DEMO-WATER-15", "supplier": 1, "stock": 48, "threshold": 20, "price": 80, "reorder": 60},
]

SALE_DATA = [
    (0, 2, 360),
    (1, 3, 495),
    (2, 1, 320),
    (3, 2, 580),
    (4, 1, 340),
    (5, 4, 500),
    (6, 2, 150),
    (7, 6, 480),
    (0, 1, 180),
    (2, 2, 640),
    (1, 1, 165),
    (4, 2, 680),
    (3, 1, 290),
    (6, 3, 225),
    (7, 4, 320),
]


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        shop = (
            await session.execute(select(Shop).where(Shop.name == SHOP_DATA["name"]))
        ).scalar_one_or_none()
        if shop is None:
            shop = Shop(**SHOP_DATA)
            session.add(shop)
            await session.flush()

        owner = (
            await session.execute(select(User).where(User.email == OWNER_EMAIL))
        ).scalar_one_or_none()
        if owner is None:
            session.add(
                User(
                    shop_id=shop.id,
                    email=OWNER_EMAIL,
                    hashed_password=pwd_context.hash(OWNER_PASSWORD),
                    role="owner",
                )
            )

        suppliers: list[Supplier] = []
        for data in SUPPLIER_DATA:
            supplier = (
                await session.execute(select(Supplier).where(Supplier.name == data["name"]))
            ).scalar_one_or_none()
            if supplier is None:
                supplier = Supplier(**data)
                session.add(supplier)
                await session.flush()
            suppliers.append(supplier)

        products: list[Product] = []
        for data in PRODUCT_DATA:
            product = (
                await session.execute(
                    select(Product).where(
                        Product.shop_id == shop.id, Product.sku == data["sku"]
                    )
                )
            ).scalar_one_or_none()
            if product is None:
                product = Product(
                    shop_id=shop.id,
                    supplier_id=suppliers[data["supplier"]].id,
                    name=data["name"],
                    sku=data["sku"],
                    unit_price=data["price"],
                    current_stock=data["stock"],
                    reorder_threshold=data["threshold"],
                    reorder_quantity=data["reorder"],
                )
                session.add(product)
                await session.flush()
            products.append(product)

        now = datetime.now(timezone.utc)
        for index, (product_index, quantity, total_price) in enumerate(SALE_DATA, start=1):
            marker = f"seed-sale-{index:02d}"
            exists = (
                await session.execute(select(Sale).where(Sale.notes == marker))
            ).scalar_one_or_none()
            if exists is None:
                session.add(
                    Sale(
                        shop_id=shop.id,
                        product_id=products[product_index].id,
                        quantity=quantity,
                        total_price=total_price,
                        timestamp=now - timedelta(days=(index - 1) % 7, hours=index),
                        notes=marker,
                    )
                )

        await session.commit()
        print("Demo seed data is ready: 1 shop, 2 suppliers, 8 products, 15 sales.")


if __name__ == "__main__":
    asyncio.run(seed())
