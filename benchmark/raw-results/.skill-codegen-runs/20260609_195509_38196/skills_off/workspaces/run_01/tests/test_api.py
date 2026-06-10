import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.app import app, get_db
from commerce_service.models import Base


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


@pytest.fixture(autouse=True)
def cleanup(db):
    yield
    app.dependency_overrides.clear()


HEADERS_WITH_API_KEY = {"X-API-Key": "test-key-12345"}


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"id": "SKU001", "name": "Widget", "available_stock": 100},
        headers=HEADERS_WITH_API_KEY,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "SKU001"
    assert data["name"] == "Widget"
    assert data["available_stock"] == 100


def test_create_sku_missing_api_key(client):
    response = client.post(
        "/skus",
        json={"id": "SKU001", "name": "Widget", "available_stock": 100},
    )
    assert response.status_code == 403


def test_create_sku_invalid_api_key(client):
    response = client.post(
        "/skus",
        json={"id": "SKU001", "name": "Widget", "available_stock": 100},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 403


def test_adjust_stock_success(client):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Widget", "available_stock": 100},
        headers=HEADERS_WITH_API_KEY,
    )

    response = client.post(
        "/skus/SKU001/adjust-stock",
        json={"quantity_delta": 50},
        headers=HEADERS_WITH_API_KEY,
    )
    assert response.status_code == 200
    assert response.json()["available_stock"] == 150


def test_adjust_stock_sku_not_found(client):
    response = client.post(
        "/skus/NONEXISTENT/adjust-stock",
        json={"quantity_delta": 50},
        headers=HEADERS_WITH_API_KEY,
    )
    assert response.status_code == 404


def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Widget", "available_stock": 100},
        headers=HEADERS_WITH_API_KEY,
    )

    response = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 30, "duration_minutes": 30},
        headers=HEADERS_WITH_API_KEY,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_id"] == "SKU001"
    assert data["quantity"] == 30
    assert data["status"] == "pending"


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Widget", "available_stock": 20},
        headers=HEADERS_WITH_API_KEY,
    )

    response = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 50, "duration_minutes": 30},
        headers=HEADERS_WITH_API_KEY,
    )
    assert response.status_code == 409


def test_create_reservation_sku_not_found(client):
    response = client.post(
        "/reservations",
        json={"sku_id": "NONEXISTENT", "quantity": 10, "duration_minutes": 30},
        headers=HEADERS_WITH_API_KEY,
    )
    assert response.status_code == 404


def test_confirm_reservation_success(client):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Widget", "available_stock": 100},
        headers=HEADERS_WITH_API_KEY,
    )

    res = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 30, "duration_minutes": 30},
        headers=HEADERS_WITH_API_KEY,
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        json={"idempotency_key": "idempotency-key-1"},
        headers=HEADERS_WITH_API_KEY,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reservation"]["status"] == "confirmed"
    assert "order_id" in data


def test_confirm_reservation_idempotency(client):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Widget", "available_stock": 100},
        headers=HEADERS_WITH_API_KEY,
    )

    res = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 30, "duration_minutes": 30},
        headers=HEADERS_WITH_API_KEY,
    )
    reservation_id = res.json()["id"]

    response1 = client.post(
        f"/reservations/{reservation_id}/confirm",
        json={"idempotency_key": "idempotency-key-1"},
        headers=HEADERS_WITH_API_KEY,
    )
    order_id_1 = response1.json()["order_id"]

    response2 = client.post(
        f"/reservations/{reservation_id}/confirm",
        json={"idempotency_key": "idempotency-key-1"},
        headers=HEADERS_WITH_API_KEY,
    )
    order_id_2 = response2.json()["order_id"]

    assert order_id_1 == order_id_2
    assert response2.status_code == 200


def test_confirm_reservation_expired(client):
    from commerce_service.models import get_session_factory, get_engine
    from datetime import datetime, timedelta
    from commerce_service.repository import Repository

    engine = get_engine("sqlite:///:memory:")
    SessionLocal = get_session_factory(engine)
    db = SessionLocal()

    repo = Repository(db)
    repo.create_sku("SKU001", "Widget", 100)

    expires_at = datetime.utcnow() - timedelta(minutes=1)
    res = repo.create_reservation("RES001", "SKU001", 30, expires_at)
    repo.update_sku_stock("SKU001", -30, 30)

    response = client.post(
        "/reservations/RES001/confirm",
        json={"idempotency_key": "idempotency-key-1"},
        headers=HEADERS_WITH_API_KEY,
    )
    assert response.status_code == 410


def test_confirm_reservation_not_found(client):
    response = client.post(
        "/reservations/NONEXISTENT/confirm",
        json={"idempotency_key": "idempotency-key-1"},
        headers=HEADERS_WITH_API_KEY,
    )
    assert response.status_code == 404


def test_cancel_reservation_success(client):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Widget", "available_stock": 100},
        headers=HEADERS_WITH_API_KEY,
    )

    res = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 30, "duration_minutes": 30},
        headers=HEADERS_WITH_API_KEY,
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        json={"reason": "User changed mind"},
        headers=HEADERS_WITH_API_KEY,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_cancel_reservation_not_found(client):
    response = client.post(
        "/reservations/NONEXISTENT/cancel",
        json={"reason": ""},
        headers=HEADERS_WITH_API_KEY,
    )
    assert response.status_code == 404


def test_list_orders(client):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Widget", "available_stock": 100},
        headers=HEADERS_WITH_API_KEY,
    )

    res = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 30, "duration_minutes": 30},
        headers=HEADERS_WITH_API_KEY,
    )
    reservation_id = res.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        json={"idempotency_key": "idempotency-key-1"},
        headers=HEADERS_WITH_API_KEY,
    )

    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["orders"]) == 1
    assert data["orders"][0]["quantity"] == 30


def test_list_orders_pagination(client):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Widget", "available_stock": 100},
        headers=HEADERS_WITH_API_KEY,
    )

    for i in range(25):
        res = client.post(
            "/reservations",
            json={"sku_id": "SKU001", "quantity": 1, "duration_minutes": 30},
            headers=HEADERS_WITH_API_KEY,
        )
        reservation_id = res.json()["id"]

        client.post(
            f"/reservations/{reservation_id}/confirm",
            json={"idempotency_key": f"idempotency-key-{i}"},
            headers=HEADERS_WITH_API_KEY,
        )

    response1 = client.get("/orders?skip=0&limit=10")
    assert response1.status_code == 200
    data1 = response1.json()
    assert data1["total"] == 25
    assert len(data1["orders"]) == 10

    response2 = client.get("/orders?skip=10&limit=10")
    data2 = response2.json()
    assert len(data2["orders"]) == 10

    response3 = client.get("/orders?skip=20&limit=10")
    data3 = response3.json()
    assert len(data3["orders"]) == 5


def test_list_orders_empty(client):
    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert len(data["orders"]) == 0


def test_get_order(client):
    client.post(
        "/skus",
        json={"id": "SKU001", "name": "Widget", "available_stock": 100},
        headers=HEADERS_WITH_API_KEY,
    )

    res = client.post(
        "/reservations",
        json={"sku_id": "SKU001", "quantity": 30, "duration_minutes": 30},
        headers=HEADERS_WITH_API_KEY,
    )
    reservation_id = res.json()["id"]

    confirm_res = client.post(
        f"/reservations/{reservation_id}/confirm",
        json={"idempotency_key": "idempotency-key-1"},
        headers=HEADERS_WITH_API_KEY,
    )
    order_id = confirm_res.json()["order_id"]

    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == order_id
    assert data["quantity"] == 30


def test_get_order_not_found(client):
    response = client.get("/orders/NONEXISTENT")
    assert response.status_code == 404
