import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.app import app, get_db
from src.commerce_service.models import Base

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)
TEST_API_KEY = "sk-test-key"


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def test_health_check() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_sku() -> None:
    response = client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget", "total_stock": 100},
        headers={"X-API-Key": TEST_API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_id"] == "SKU-001"
    assert data["total_stock"] == 100
    assert data["available_stock"] == 100


def test_create_sku_unauthorized() -> None:
    response = client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget", "total_stock": 100},
    )
    assert response.status_code == 403


def test_create_sku_duplicate() -> None:
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget", "total_stock": 100},
        headers={"X-API-Key": TEST_API_KEY},
    )
    response = client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget", "total_stock": 50},
        headers={"X-API-Key": TEST_API_KEY},
    )
    assert response.status_code == 409


def test_adjust_stock() -> None:
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget", "total_stock": 100},
        headers={"X-API-Key": TEST_API_KEY},
    )
    response = client.post(
        "/skus/SKU-001/stock",
        json={"adjustment": 50},
        headers={"X-API-Key": TEST_API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_stock"] == 150


def test_adjust_stock_negative() -> None:
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget", "total_stock": 100},
        headers={"X-API-Key": TEST_API_KEY},
    )
    response = client.post(
        "/skus/SKU-001/stock",
        json={"adjustment": -150},
        headers={"X-API-Key": TEST_API_KEY},
    )
    assert response.status_code == 400


def test_create_reservation() -> None:
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget", "total_stock": 100},
        headers={"X-API-Key": TEST_API_KEY},
    )
    response = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 10, "idempotency_key": "key-1"},
        headers={"X-API-Key": TEST_API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_id"] == "SKU-001"
    assert data["quantity"] == 10
    assert data["status"] == "pending"


def test_create_reservation_insufficient_stock() -> None:
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget", "total_stock": 10},
        headers={"X-API-Key": TEST_API_KEY},
    )
    response = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 20, "idempotency_key": "key-1"},
        headers={"X-API-Key": TEST_API_KEY},
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotent() -> None:
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget", "total_stock": 100},
        headers={"X-API-Key": TEST_API_KEY},
    )
    res1 = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 10, "idempotency_key": "key-1"},
        headers={"X-API-Key": TEST_API_KEY},
    )
    res2 = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 10, "idempotency_key": "key-1"},
        headers={"X-API-Key": TEST_API_KEY},
    )
    assert res1.status_code == 200
    assert res2.status_code == 200
    assert res1.json()["reservation_id"] == res2.json()["reservation_id"]


def test_confirm_reservation() -> None:
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget", "total_stock": 100},
        headers={"X-API-Key": TEST_API_KEY},
    )
    res = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 10, "idempotency_key": "key-1"},
        headers={"X-API-Key": TEST_API_KEY},
    )
    reservation_id = res.json()["reservation_id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": TEST_API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "confirmed"
    assert data["confirmed_at"] is not None


def test_cancel_reservation() -> None:
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget", "total_stock": 100},
        headers={"X-API-Key": TEST_API_KEY},
    )
    res = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 10, "idempotency_key": "key-1"},
        headers={"X-API-Key": TEST_API_KEY},
    )
    reservation_id = res.json()["reservation_id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": TEST_API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cancelled"


def test_cancel_confirmed_reservation() -> None:
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget", "total_stock": 100},
        headers={"X-API-Key": TEST_API_KEY},
    )
    res = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 10, "idempotency_key": "key-1"},
        headers={"X-API-Key": TEST_API_KEY},
    )
    reservation_id = res.json()["reservation_id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": TEST_API_KEY},
    )

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": TEST_API_KEY},
    )
    assert response.status_code == 409


def test_get_order() -> None:
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget", "total_stock": 100},
        headers={"X-API-Key": TEST_API_KEY},
    )
    res = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 10, "idempotency_key": "key-1"},
        headers={"X-API-Key": TEST_API_KEY},
    )
    reservation_id = res.json()["reservation_id"]

    confirm = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": TEST_API_KEY},
    )

    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["orders"][0]["status"] == "confirmed"


def test_list_orders_pagination() -> None:
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget", "total_stock": 100},
        headers={"X-API-Key": TEST_API_KEY},
    )

    for i in range(5):
        res = client.post(
            "/reservations",
            json={"sku_id": "SKU-001", "quantity": 10, "idempotency_key": f"key-{i}"},
            headers={"X-API-Key": TEST_API_KEY},
        )
        reservation_id = res.json()["reservation_id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": TEST_API_KEY},
        )

    response = client.get("/orders?limit=2&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["orders"]) == 2
    assert data["limit"] == 2
    assert data["offset"] == 0

    response = client.get("/orders?limit=2&offset=2")
    data = response.json()
    assert len(data["orders"]) == 2


def test_unauthorized_confirm() -> None:
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget", "total_stock": 100},
        headers={"X-API-Key": TEST_API_KEY},
    )
    res = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 10, "idempotency_key": "key-1"},
        headers={"X-API-Key": TEST_API_KEY},
    )
    reservation_id = res.json()["reservation_id"]

    response = client.post(f"/reservations/{reservation_id}/confirm")
    assert response.status_code == 403
