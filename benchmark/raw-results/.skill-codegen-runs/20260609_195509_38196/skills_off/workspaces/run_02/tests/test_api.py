import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from commerce_service.app import app, get_db
from commerce_service.models import Base

VALID_API_KEY = "test-key"


@pytest.fixture
def test_db():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False)

    def get_test_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    yield get_test_db

    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    os.unlink(db_path)


@pytest.fixture
def client(test_db):
    app.dependency_overrides[get_db] = test_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_sku_authorized(client):
    response = client.post(
        "/skus",
        json={"code": "SKU001"},
        headers={"x-api-key": VALID_API_KEY},
    )
    assert response.status_code == 200
    assert response.json()["code"] == "SKU001"


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"code": "SKU001"},
        headers={"x-api-key": "wrong-key"},
    )
    assert response.status_code == 401


def test_create_sku_missing_api_key(client):
    response = client.post(
        "/skus",
        json={"code": "SKU001"},
    )
    assert response.status_code == 401


def test_adjust_stock_positive(client):
    client.post(
        "/skus",
        json={"code": "SKU001"},
        headers={"x-api-key": VALID_API_KEY},
    )
    response = client.post(
        "/stock/adjust",
        json={"sku_code": "SKU001", "delta": 100},
        headers={"x-api-key": VALID_API_KEY},
    )
    assert response.status_code == 200
    assert response.json()["quantity"] == 100


def test_adjust_stock_negative(client):
    client.post(
        "/skus",
        json={"code": "SKU001"},
        headers={"x-api-key": VALID_API_KEY},
    )
    client.post(
        "/stock/adjust",
        json={"sku_code": "SKU001", "delta": 100},
        headers={"x-api-key": VALID_API_KEY},
    )
    response = client.post(
        "/stock/adjust",
        json={"sku_code": "SKU001", "delta": -30},
        headers={"x-api-key": VALID_API_KEY},
    )
    assert response.status_code == 200
    assert response.json()["quantity"] == 70


def test_create_reservation_happy_path(client):
    client.post(
        "/skus",
        json={"code": "SKU001"},
        headers={"x-api-key": VALID_API_KEY},
    )
    client.post(
        "/stock/adjust",
        json={"sku_code": "SKU001", "delta": 100},
        headers={"x-api-key": VALID_API_KEY},
    )
    response = client.post(
        "/reservations",
        json={"sku_code": "SKU001", "quantity": 10, "idempotency_key": "key-1"},
        headers={"x-api-key": VALID_API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["quantity"] == 10
    assert data["status"] == "pending"


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"code": "SKU001"},
        headers={"x-api-key": VALID_API_KEY},
    )
    client.post(
        "/stock/adjust",
        json={"sku_code": "SKU001", "delta": 5},
        headers={"x-api-key": VALID_API_KEY},
    )
    response = client.post(
        "/reservations",
        json={"sku_code": "SKU001", "quantity": 10, "idempotency_key": "key-1"},
        headers={"x-api-key": VALID_API_KEY},
    )
    assert response.status_code == 409


def test_create_reservation_idempotent(client):
    client.post(
        "/skus",
        json={"code": "SKU001"},
        headers={"x-api-key": VALID_API_KEY},
    )
    client.post(
        "/stock/adjust",
        json={"sku_code": "SKU001", "delta": 100},
        headers={"x-api-key": VALID_API_KEY},
    )
    response1 = client.post(
        "/reservations",
        json={"sku_code": "SKU001", "quantity": 10, "idempotency_key": "key-1"},
        headers={"x-api-key": VALID_API_KEY},
    )
    response2 = client.post(
        "/reservations",
        json={"sku_code": "SKU001", "quantity": 10, "idempotency_key": "key-1"},
        headers={"x-api-key": VALID_API_KEY},
    )
    assert response1.status_code == 200
    assert response2.status_code == 200
    assert response1.json()["id"] == response2.json()["id"]


def test_confirm_reservation(client):
    client.post(
        "/skus",
        json={"code": "SKU001"},
        headers={"x-api-key": VALID_API_KEY},
    )
    client.post(
        "/stock/adjust",
        json={"sku_code": "SKU001", "delta": 100},
        headers={"x-api-key": VALID_API_KEY},
    )
    res_response = client.post(
        "/reservations",
        json={"sku_code": "SKU001", "quantity": 10, "idempotency_key": "key-1"},
        headers={"x-api-key": VALID_API_KEY},
    )
    res_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"x-api-key": VALID_API_KEY},
    )
    assert response.status_code == 200
    assert response.json()["order_id"]


def test_cancel_reservation(client):
    client.post(
        "/skus",
        json={"code": "SKU001"},
        headers={"x-api-key": VALID_API_KEY},
    )
    client.post(
        "/stock/adjust",
        json={"sku_code": "SKU001", "delta": 100},
        headers={"x-api-key": VALID_API_KEY},
    )
    res_response = client.post(
        "/reservations",
        json={"sku_code": "SKU001", "quantity": 10, "idempotency_key": "key-1"},
        headers={"x-api-key": VALID_API_KEY},
    )
    res_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"x-api-key": VALID_API_KEY},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_get_order_after_confirmation(client):
    client.post(
        "/skus",
        json={"code": "SKU001"},
        headers={"x-api-key": VALID_API_KEY},
    )
    client.post(
        "/stock/adjust",
        json={"sku_code": "SKU001", "delta": 100},
        headers={"x-api-key": VALID_API_KEY},
    )
    res_response = client.post(
        "/reservations",
        json={"sku_code": "SKU001", "quantity": 10, "idempotency_key": "key-1"},
        headers={"x-api-key": VALID_API_KEY},
    )
    res_id = res_response.json()["id"]

    order_response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"x-api-key": VALID_API_KEY},
    )
    order_id = order_response.json()["order_id"]

    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    assert response.json()["id"] == order_id


def test_list_orders_pagination(client):
    client.post(
        "/skus",
        json={"code": "SKU001"},
        headers={"x-api-key": VALID_API_KEY},
    )
    client.post(
        "/stock/adjust",
        json={"sku_code": "SKU001", "delta": 1000},
        headers={"x-api-key": VALID_API_KEY},
    )

    # Create 25 orders
    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={"sku_code": "SKU001", "quantity": 10, "idempotency_key": f"key-{i}"},
            headers={"x-api-key": VALID_API_KEY},
        )
        res_id = res_response.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"x-api-key": VALID_API_KEY},
        )

    # Test first page
    response1 = client.get(
        "/orders?limit=10&offset=0",
        headers={"x-api-key": VALID_API_KEY},
    )
    assert response1.status_code == 200
    page1 = response1.json()
    assert len(page1["orders"]) == 10
    assert page1["total"] == 25

    # Test second page
    response2 = client.get(
        "/orders?limit=10&offset=10",
        headers={"x-api-key": VALID_API_KEY},
    )
    page2 = response2.json()
    assert len(page2["orders"]) == 10

    # Test last page
    response3 = client.get(
        "/orders?limit=10&offset=20",
        headers={"x-api-key": VALID_API_KEY},
    )
    page3 = response3.json()
    assert len(page3["orders"]) == 5


def test_create_reservation_unauthorized_mutation(client):
    response = client.post(
        "/reservations",
        json={"sku_code": "SKU001", "quantity": 10, "idempotency_key": "key-1"},
        headers={"x-api-key": "wrong-key"},
    )
    assert response.status_code == 401
