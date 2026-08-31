"""Asynchronous background tasks for inventory automation."""

from __future__ import annotations

import hashlib
import hmac
import json
import os

import httpx
from sqlalchemy import select

from .database import AsyncSessionLocal
from .models import Product, RestockOrder, RestockStatus, Supplier


async def check_and_create_restock_order(product_id: int) -> None:
    """Create a pending restock order and notify the assigned supplier."""
    async with AsyncSessionLocal() as db:
        product = await db.get(Product, product_id)
        if not product or not product.is_low_stock or not product.supplier_id:
            return

        supplier = await db.get(Supplier, product.supplier_id)
        if not supplier:
            return

        existing = await db.execute(
            select(RestockOrder).where(
                RestockOrder.product_id == product.id,
                RestockOrder.status.in_(
                    [RestockStatus.PENDING, RestockStatus.CONFIRMED]
                ),
            )
        )
        if existing.scalars().first():
            return

        order = RestockOrder(
            shop_id=product.shop_id,
            product_id=product.id,
            supplier_id=supplier.id,
            quantity_ordered=product.reorder_quantity,
            status=RestockStatus.PENDING,
            notes=(
                f"Auto-triggered: stock={product.quantity_in_stock}, "
                f"threshold={product.reorder_threshold}"
            ),
        )
        db.add(order)
        await db.commit()
        await db.refresh(order)

        if not supplier.webhook_url:
            return

        payload = {
            "event": "restock_order.created",
            "order_id": order.id,
            "product_id": product.id,
            "product_name": product.name,
            "quantity": order.quantity_ordered,
            "status": order.status.value,
        }
        payload_bytes = json.dumps(
            payload, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        secret = os.getenv("WEBHOOK_SECRET", "")
        signature = hmac.new(
            secret.encode("utf-8"), payload_bytes, hashlib.sha256
        ).hexdigest()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                supplier.webhook_url,
                content=payload_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Signature": f"sha256={signature}",
                },
            )
            response.raise_for_status()