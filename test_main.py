"""API tests for shop, product, sale, and low-stock workflows."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


# SQLite needs INTEGER (rather than BIGINT) for auto-incrementing primary keys.
@compiles(BigInteger, "sqlite")
def compile_bigint_for_sqlite(type_, compiler, **kwargs):
    return "INTEGER"


from backend import main, tasks
from backend.database import Base, get_db
from backend.models import RestockOrder, Supplier


TEST_ENGINE = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = async_sessionmaker(TEST_ENGINE, expire_on_commit=False)


async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_test_tables() -> None:
    async with TEST_ENGINE.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def drop_test_tables() -> None:
    async with TEST_ENGINE.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


@pytest.fixture
def client(monkeypatch):
    asyncio.run(create_test_tables())
    monkeypatch.setattr(main, "engine", TEST_ENGINE)
    monkeypatch.setattr(tasks, "AsyncSessionLocal", TestSessionLocal)
    main.app.dependency_overrides[get_db] = override_get_db

    with TestClient(main.app, raise_server_exceptions=False) as test_client:
        yield test_client

    main.app.dependency_overrides.clear()
    asyncio.run(drop_test_tables())


def create_shop(client: TestClient) -> dict:
    response = client.post(
        "/shops/",
        json={
            "name": "Corner Shop",
            "location": "Nairobi",
            "owner_name": "Amina",
            "phone": "+254700000000",
        },
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def auth_headers(client: TestClient):
    shop = create_shop(client)
    return shop, login_shop_owner(client, shop["id"])


def login_shop_owner(client: TestClient, shop_id: int) -> dict[str, str]:
    register = client.post(
        "/auth/register",
        json={"shop_id": shop_id, "email": f"owner{shop_id}@example.com", "password": "password123"},
    )
    assert register.status_code == 201
    login = client.post(
        "/auth/login",
        json={"email": f"owner{shop_id}@example.com", "password": "password123"},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def create_supplier() -> int:
    async def insert_supplier() -> int:
        async with TestSessionLocal() as session:
            supplier = Supplier(name="Test Supplier", contact_phone="+254711111111")
            session.add(supplier)
            await session.commit()
            return supplier.id

    return asyncio.run(insert_supplier())


def test_create_shop(client: TestClient):
    shop = create_shop(client)

    assert shop["id"] > 0
    assert shop["name"] == "Corner Shop"


def test_create_product(client: TestClient, auth_headers):
    shop, headers = auth_headers
    response = client.post(
        "/products/",
        json={
            "shop_id": shop["id"],
            "name": "Maize Flour",
            "sku": "FLOUR-001",
            "quantity_in_stock": 10,
            "reorder_threshold": 3,
            "reorder_quantity": 20,
            "unit_price": 150.0,
        },
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["shop_id"] == shop["id"]
    assert response.json()["quantity_in_stock"] == 10


def test_record_sale_decreases_stock(client: TestClient, auth_headers):
    shop, headers = auth_headers
    product = client.post(
        "/products/",
        json={
            "shop_id": shop["id"],
            "name": "Sugar",
            "sku": "SUGAR-001",
            "quantity_in_stock": 10,
            "reorder_threshold": 2,
            "unit_price": 120.0,
        },
        headers=headers,
    ).json()

    response = client.post(
        "/sales/",
        json={
            "shop_id": shop["id"],
            "product_id": product["id"],
            "quantity_sold": 4,
            "sale_price": 480.0,
        },
        headers=headers,
    )

    assert response.status_code == 201
    inventory = client.get(f"/shops/{shop['id']}/inventory", headers=headers).json()
    assert inventory[0]["quantity_in_stock"] == 6


def test_sale_at_threshold_creates_restock_order(client: TestClient, auth_headers):
    shop, headers = auth_headers
    supplier_id = create_supplier()
    product = client.post(
        "/products/",
        json={
            "shop_id": shop["id"],
            "supplier_id": supplier_id,
            "name": "Cooking Oil",
            "sku": "OIL-001",
            "quantity_in_stock": 5,
            "reorder_threshold": 2,
            "reorder_quantity": 15,
            "unit_price": 300.0,
        },
        headers=headers,
    ).json()

    response = client.post(
        "/sales/",
        json={
            "shop_id": shop["id"],
            "product_id": product["id"],
            "quantity_sold": 3,
            "sale_price": 900.0,
        },
        headers=headers,
    )

    assert response.status_code == 201

    async def find_orders() -> list[RestockOrder]:
        async with TestSessionLocal() as session:
            result = await session.execute(select(RestockOrder))
            return list(result.scalars().all())

    orders = asyncio.run(find_orders())
    assert len(orders) == 1
    assert orders[0].status.value == "PENDING"
    assert orders[0].product_id == product["id"]


def test_missing_shop_returns_404(client: TestClient, auth_headers):
    shop, headers = auth_headers
    response = client.get(
        "/shops/999999/inventory",
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Shop not found"}


def test_missing_product_returns_404(client: TestClient, auth_headers):
    shop, headers = auth_headers
    response = client.post(
        "/sales/",
        json={
            "shop_id": shop["id"],
            "product_id": 999999,
            "quantity_sold": 1,
            "sale_price": 10,
        },
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Product not found"}


def test_missing_supplier_returns_404(client: TestClient, auth_headers):
    shop, headers = auth_headers
    response = client.post(
        "/products/",
        json={"shop_id": shop["id"], "supplier_id": 999999, "name": "Rice"},
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Supplier not found"}


def test_insufficient_stock_returns_400(client: TestClient, auth_headers):
    shop, headers = auth_headers
    product = client.post(
        "/products/",
        json={"shop_id": shop["id"], "name": "Beans", "quantity_in_stock": 2},
        headers=headers,
    ).json()
    response = client.post(
        "/sales/",
        json={
            "shop_id": shop["id"],
            "product_id": product["id"],
            "quantity_sold": 3,
            "sale_price": 30,
        },
        headers=headers,
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_duplicate_sku_within_shop_returns_409(client: TestClient, auth_headers):
    shop, headers = auth_headers
    body = {"shop_id": shop["id"], "name": "Tea", "sku": "TEA-001"}
    assert client.post("/products/", json=body, headers=headers).status_code == 201
    response = client.post("/products/", json=body, headers=headers)
    assert response.status_code == 409
    assert response.json() == {"detail": "SKU already exists in shop"}


def test_sale_quantity_must_be_positive(client: TestClient, auth_headers):
    shop, headers = auth_headers
    response = client.post(
        "/sales/",
        json={"shop_id": shop["id"], "product_id": 1, "quantity_sold": 0, "sale_price": 1},
        headers=headers,
    )
    assert response.status_code == 422
    assert "greater than 0" in response.json()["detail"][0]["msg"]


def test_unhandled_errors_use_consistent_shape(client: TestClient):
    async def raise_error():
        raise RuntimeError("unexpected failure")

    client.app.router.add_api_route("/test-unhandled-error", raise_error, methods=["GET"])
    response = client.get("/test-unhandled-error")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}


def test_protected_endpoint_requires_token(client: TestClient):
    response = client.get("/shops/1/inventory")
    assert response.status_code == 401


def test_shop_user_cannot_access_or_create_in_other_shop(client: TestClient):
    shop_a = create_shop(client)
    shop_b_response = client.post(
        "/shops/",
        json={"name": "Other Shop", "location": "Mombasa"},
    )
    assert shop_b_response.status_code == 201
    shop_b = shop_b_response.json()
    headers_a = login_shop_owner(client, shop_a["id"])
    inventory_response = client.get(
        f"/shops/{shop_b['id']}/inventory", headers=headers_a
    )
    assert inventory_response.status_code == 403
    product_response = client.post(
        "/products/",
        json={"shop_id": shop_b["id"], "name": "Unauthorized Product"},
        headers=headers_a,
    )
    assert product_response.status_code == 403
