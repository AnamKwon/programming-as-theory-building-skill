import pytest
import os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.app import app, get_db, init_db
from commerce_service.models import Base
from commerce_service.security import API_KEY


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield SessionLocal()
    app.dependency_overrides.clear()


@pytest.fixture
def client(test_db):
    return TestClient(app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_without_api_key(client):
    response = client.post("/skus", json={"sku_code": "SKU-001"})
    assert response.status_code == 401


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku_code": "SKU-001"},
        headers={"x-api-key": API_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_code"] == "SKU-001"
    assert data["stock_available"] == 0


def test_create_sku_invalid_api_key(client):
    response = client.post(
        "/skus",
        json={"sku_code": "SKU-001"},
        headers={"x-api-key": "wrong-key"},
    )
    assert response.status_code == 401


def test_adjust_stock_success(client):
    sku = client.post(
        "/skus",
        json={"sku_code": "SKU-001"},
        headers={"x-api-key": API_KEY},
    ).json()

    response = client.post(
        f"/skus/{sku['id']}/adjust-stock",
        json={"delta": 100},
        headers={"x-api-key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["stock_available"] == 100


def test_adjust_stock_not_found(client):
    response = client.post(
        "/skus/999/adjust-stock",
        json={"delta": 100},
        headers={"x-api-key": API_KEY},
    )
    assert response.status_code == 404


def test_create_reservation_success(client):
    sku = client.post(
        "/skus",
        json={"sku_code": "SKU-001"},
        headers={"x-api-key": API_KEY},
    ).json()

    client.post(
        f"/skus/{sku['id']}/adjust-stock",
        json={"delta": 100},
        headers={"x-api-key": API_KEY},
    )

    response = client.post(
        "/reservations",
        json={"sku_id": sku["id"], "quantity": 50},
        headers={"x-api-key": API_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["quantity"] == 50
    assert data["status"] == "pending"


def test_create_reservation_insufficient_stock(client):
    sku = client.post(
        "/skus",
        json={"sku_code": "SKU-001"},
        headers={"x-api-key": API_KEY},
    ).json()

    client.post(
        f"/skus/{sku['id']}/adjust-stock",
        json={"delta": 30},
        headers={"x-api-key": API_KEY},
    )

    response = client.post(
        "/reservations",
        json={"sku_id": sku["id"], "quantity": 50},
        headers={"x-api-key": API_KEY},
    )
    assert response.status_code == 409
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotency(client):
    sku = client.post(
        "/skus",
        json={"sku_code": "SKU-001"},
        headers={"x-api-key": API_KEY},
    ).json()

    client.post(
        f"/skus/{sku['id']}/adjust-stock",
        json={"delta": 100},
        headers={"x-api-key": API_KEY},
    )

    key = "idempotency-123"
    res1 = client.post(
        "/reservations",
        json={"sku_id": sku["id"], "quantity": 50, "idempotency_key": key},
        headers={"x-api-key": API_KEY},
    ).json()

    res2 = client.post(
        "/reservations",
        json={"sku_id": sku["id"], "quantity": 50, "idempotency_key": key},
        headers={"x-api-key": API_KEY},
    ).json()

    assert res1["id"] == res2["id"]


def test_confirm_reservation_success(client):
    sku = client.post(
        "/skus",
        json={"sku_code": "SKU-001"},
        headers={"x-api-key": API_KEY},
    ).json()

    client.post(
        f"/skus/{sku['id']}/adjust-stock",
        json={"delta": 100},
        headers={"x-api-key": API_KEY},
    )

    res = client.post(
        "/reservations",
        json={"sku_id": sku["id"], "quantity": 50},
        headers={"x-api-key": API_KEY},
    ).json()

    response = client.post(
        f"/reservations/{res['id']}/confirm",
        headers={"x-api-key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"  # order status, initially pending


def test_confirm_reservation_not_found(client):
    response = client.post(
        "/reservations/999/confirm",
        headers={"x-api-key": API_KEY},
    )
    assert response.status_code == 404


def test_confirm_reservation_expired(client):
    from datetime import datetime, timedelta
    from commerce_service.models import ReservationModel

    sku = client.post(
        "/skus",
        json={"sku_code": "SKU-001"},
        headers={"x-api-key": API_KEY},
    ).json()

    client.post(
        f"/skus/{sku['id']}/adjust-stock",
        json={"delta": 100},
        headers={"x-api-key": API_KEY},
    )

    res = client.post(
        "/reservations",
        json={"sku_id": sku["id"], "quantity": 50},
        headers={"x-api-key": API_KEY},
    ).json()

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    db.query(ReservationModel).filter(
        ReservationModel.id == res["id"]
    ).update({"expires_at": datetime.utcnow() - timedelta(seconds=100)})
    db.commit()

    response = client.post(
        f"/reservations/{res['id']}/confirm",
        headers={"x-api-key": API_KEY},
    )
    assert response.status_code == 410


def test_cancel_reservation_success(client):
    sku = client.post(
        "/skus",
        json={"sku_code": "SKU-001"},
        headers={"x-api-key": API_KEY},
    ).json()

    client.post(
        f"/skus/{sku['id']}/adjust-stock",
        json={"delta": 100},
        headers={"x-api-key": API_KEY},
    )

    res = client.post(
        "/reservations",
        json={"sku_id": sku["id"], "quantity": 50},
        headers={"x-api-key": API_KEY},
    ).json()

    response = client.post(
        f"/reservations/{res['id']}/cancel",
        headers={"x-api-key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cancelled"


def test_cancel_reservation_not_found(client):
    response = client.post(
        "/reservations/999/cancel",
        headers={"x-api-key": API_KEY},
    )
    assert response.status_code == 404


def test_cancel_confirmed_reservation(client):
    sku = client.post(
        "/skus",
        json={"sku_code": "SKU-001"},
        headers={"x-api-key": API_KEY},
    ).json()

    client.post(
        f"/skus/{sku['id']}/adjust-stock",
        json={"delta": 100},
        headers={"x-api-key": API_KEY},
    )

    res = client.post(
        "/reservations",
        json={"sku_id": sku["id"], "quantity": 50},
        headers={"x-api-key": API_KEY},
    ).json()

    client.post(
        f"/reservations/{res['id']}/confirm",
        headers={"x-api-key": API_KEY},
    )

    response = client.post(
        f"/reservations/{res['id']}/cancel",
        headers={"x-api-key": API_KEY},
    )
    assert response.status_code == 400
    assert "Cannot cancel" in response.json()["detail"]


def test_list_orders_success(client):
    sku = client.post(
        "/skus",
        json={"sku_code": "SKU-001"},
        headers={"x-api-key": API_KEY},
    ).json()

    client.post(
        f"/skus/{sku['id']}/adjust-stock",
        json={"delta": 300},
        headers={"x-api-key": API_KEY},
    )

    for i in range(5):
        res = client.post(
            "/reservations",
            json={"sku_id": sku["id"], "quantity": 10},
            headers={"x-api-key": API_KEY},
        ).json()
        client.post(
            f"/reservations/{res['id']}/confirm",
            headers={"x-api-key": API_KEY},
        )

    response = client.get("/orders?page=1&limit=20")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["orders"]) == 5


def test_list_orders_pagination(client):
    sku = client.post(
        "/skus",
        json={"sku_code": "SKU-001"},
        headers={"x-api-key": API_KEY},
    ).json()

    client.post(
        f"/skus/{sku['id']}/adjust-stock",
        json={"delta": 500},
        headers={"x-api-key": API_KEY},
    )

    for i in range(25):
        res = client.post(
            "/reservations",
            json={"sku_id": sku["id"], "quantity": 10},
            headers={"x-api-key": API_KEY},
        ).json()
        client.post(
            f"/reservations/{res['id']}/confirm",
            headers={"x-api-key": API_KEY},
        )

    page1 = client.get("/orders?page=1&limit=10").json()
    page2 = client.get("/orders?page=2&limit=10").json()
    page3 = client.get("/orders?page=3&limit=10").json()

    assert page1["total"] == 25
    assert len(page1["orders"]) == 10
    assert len(page2["orders"]) == 10
    assert len(page3["orders"]) == 5


def test_get_order_success(client):
    sku = client.post(
        "/skus",
        json={"sku_code": "SKU-001"},
        headers={"x-api-key": API_KEY},
    ).json()

    client.post(
        f"/skus/{sku['id']}/adjust-stock",
        json={"delta": 100},
        headers={"x-api-key": API_KEY},
    )

    res = client.post(
        "/reservations",
        json={"sku_id": sku["id"], "quantity": 50},
        headers={"x-api-key": API_KEY},
    ).json()

    order = client.post(
        f"/reservations/{res['id']}/confirm",
        headers={"x-api-key": API_KEY},
    ).json()

    response = client.get(f"/orders/{order['id']}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == order["id"]
    assert data["status"] == "pending"


def test_get_order_not_found(client):
    response = client.get("/orders/999")
    assert response.status_code == 404
