import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import time
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from commerce_service.app import app
from commerce_service.repository import Base, get_db

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_commerce.db"

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

VALID_API_KEY = "test-api-key-12345"
INVALID_API_KEY = "invalid-key"


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success():
    response = client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "WIDGET-001"
    assert data["stock"] == 100


def test_create_sku_missing_api_key():
    response = client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "API key required"


def test_create_sku_invalid_api_key():
    response = client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Key": INVALID_API_KEY}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API key"


def test_adjust_stock():
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    response = client.post(
        "/stock/adjust",
        json={"sku": "WIDGET-001", "amount": 50},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["stock"] == 150


def test_adjust_stock_negative():
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    response = client.post(
        "/stock/adjust",
        json={"sku": "WIDGET-001", "amount": -30},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["stock"] == 70


def test_create_reservation_success():
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    response = client.post(
        "/reservations",
        json={"sku": "WIDGET-001", "quantity": 50, "idempotency_key": "key-001"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "WIDGET-001"
    assert data["quantity"] == 50
    assert data["status"] == "PENDING"
    assert data["idempotency_key"] == "key-001"

    sku_response = client.get(
        "/health",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert sku_response.status_code == 200


def test_create_reservation_insufficient_stock():
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 30},
        headers={"X-API-Key": VALID_API_KEY}
    )
    response = client.post(
        "/reservations",
        json={"sku": "WIDGET-001", "quantity": 50, "idempotency_key": "key-001"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_create_reservation_idempotency():
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    response1 = client.post(
        "/reservations",
        json={"sku": "WIDGET-001", "quantity": 50, "idempotency_key": "key-001"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response1.status_code == 201
    reservation_id_1 = response1.json()["id"]

    response2 = client.post(
        "/reservations",
        json={"sku": "WIDGET-001", "quantity": 50, "idempotency_key": "key-001"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response2.status_code == 201
    reservation_id_2 = response2.json()["id"]

    assert reservation_id_1 == reservation_id_2
    assert response1.json() == response2.json()


def test_confirm_reservation():
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "WIDGET-001", "quantity": 50, "idempotency_key": "key-001"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reservation_id"] == reservation_id
    assert data["sku"] == "WIDGET-001"
    assert data["quantity"] == 50


def test_confirm_reservation_expired():
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "WIDGET-001", "quantity": 50, "idempotency_key": "key-001"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    reservation_id = res_response.json()["id"]

    time.sleep(301)

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Reservation expired"


def test_cancel_reservation():
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "WIDGET-001", "quantity": 50, "idempotency_key": "key-001"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 200
    assert response.json()["detail"] == "Reservation cancelled"


def test_get_orders_pagination():
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 1000},
        headers={"X-API-Key": VALID_API_KEY}
    )

    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={"sku": "WIDGET-001", "quantity": 10, "idempotency_key": f"key-{i}"},
            headers={"X-API-Key": VALID_API_KEY}
        )
        reservation_id = res_response.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": VALID_API_KEY}
        )

    response = client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] == 25
    assert len(data["orders"]) == 10

    response = client.get("/orders?page=2&size=10")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 2
    assert len(data["orders"]) == 10

    response = client.get("/orders?page=3&size=10")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 3
    assert len(data["orders"]) == 5


def test_happy_path_workflow():
    client.post(
        "/skus",
        json={"sku": "PRODUCT-X", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "PRODUCT-X", "quantity": 50, "idempotency_key": "order-1"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert res_response.status_code == 201
    reservation_id = res_response.json()["id"]

    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert confirm_response.status_code == 200
    order_id = confirm_response.json()["id"]

    orders_response = client.get("/orders")
    assert orders_response.status_code == 200
    orders = orders_response.json()["orders"]
    assert len(orders) == 1
    assert orders[0]["id"] == order_id
    assert orders[0]["sku"] == "PRODUCT-X"
    assert orders[0]["quantity"] == 50


def test_confirm_non_pending_reservation():
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    res_response = client.post(
        "/reservations",
        json={"sku": "WIDGET-001", "quantity": 50, "idempotency_key": "key-001"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    reservation_id = res_response.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY}
    )

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Reservation is not in PENDING status"
