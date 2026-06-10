import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from commerce_service.app import app, get_db
from commerce_service.repository import Repository, Base


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()


@pytest.fixture
def client(test_db):
    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_sku_authorized(client):
    response = client.post(
        "/skus",
        json={"sku_id": "PROD-001", "name": "Widget"},
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 201
    assert response.json()["sku_id"] == "PROD-001"


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"sku_id": "PROD-001", "name": "Widget"},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 401


def test_create_sku_no_auth_header(client):
    response = client.post(
        "/skus",
        json={"sku_id": "PROD-001", "name": "Widget"},
    )
    assert response.status_code == 401


def test_get_sku(client):
    client.post(
        "/skus",
        json={"sku_id": "PROD-001", "name": "Widget"},
        headers={"X-API-Key": "test-key-12345"},
    )
    response = client.get("/skus/PROD-001")
    assert response.status_code == 200
    assert response.json()["sku_id"] == "PROD-001"


def test_get_nonexistent_sku(client):
    response = client.get("/skus/NONEXISTENT")
    assert response.status_code == 404


def test_adjust_stock_authorized(client):
    client.post(
        "/skus",
        json={"sku_id": "PROD-001", "name": "Widget"},
        headers={"X-API-Key": "test-key-12345"},
    )
    response = client.post(
        "/stock/PROD-001/adjust",
        json={"quantity": 100},
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 200
    assert response.json()["available"] == 100


def test_adjust_stock_unauthorized(client):
    response = client.post(
        "/stock/PROD-001/adjust",
        json={"quantity": 100},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 401


def test_get_stock(client):
    client.post(
        "/skus",
        json={"sku_id": "PROD-001", "name": "Widget"},
        headers={"X-API-Key": "test-key-12345"},
    )
    client.post(
        "/stock/PROD-001/adjust",
        json={"quantity": 50},
        headers={"X-API-Key": "test-key-12345"},
    )
    response = client.get("/stock/PROD-001")
    assert response.status_code == 200
    assert response.json()["available"] == 50


def test_create_reservation_happy_path(client):
    client.post(
        "/skus",
        json={"sku_id": "PROD-001", "name": "Widget"},
        headers={"X-API-Key": "test-key-12345"},
    )
    client.post(
        "/stock/PROD-001/adjust",
        json={"quantity": 100},
        headers={"X-API-Key": "test-key-12345"},
    )

    response = client.post(
        "/reservations",
        json={
            "sku_id": "PROD-001",
            "quantity": 10,
            "idempotency_key": "idem-key-1",
        },
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 201
    assert response.json()["sku_id"] == "PROD-001"
    assert response.json()["status"] == "active"


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku_id": "PROD-001", "name": "Widget"},
        headers={"X-API-Key": "test-key-12345"},
    )
    client.post(
        "/stock/PROD-001/adjust",
        json={"quantity": 5},
        headers={"X-API-Key": "test-key-12345"},
    )

    response = client.post(
        "/reservations",
        json={
            "sku_id": "PROD-001",
            "quantity": 10,
            "idempotency_key": "idem-key-1",
        },
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 409


def test_create_reservation_unauthorized(client):
    response = client.post(
        "/reservations",
        json={
            "sku_id": "PROD-001",
            "quantity": 10,
            "idempotency_key": "idem-key-1",
        },
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 401


def test_create_reservation_idempotent(client):
    client.post(
        "/skus",
        json={"sku_id": "PROD-001", "name": "Widget"},
        headers={"X-API-Key": "test-key-12345"},
    )
    client.post(
        "/stock/PROD-001/adjust",
        json={"quantity": 100},
        headers={"X-API-Key": "test-key-12345"},
    )

    response1 = client.post(
        "/reservations",
        json={
            "sku_id": "PROD-001",
            "quantity": 10,
            "idempotency_key": "idem-key-1",
        },
        headers={"X-API-Key": "test-key-12345"},
    )
    response2 = client.post(
        "/reservations",
        json={
            "sku_id": "PROD-001",
            "quantity": 10,
            "idempotency_key": "idem-key-1",
        },
        headers={"X-API-Key": "test-key-12345"},
    )

    assert response1.json()["reservation_id"] == response2.json()["reservation_id"]


def test_confirm_reservation_happy_path(client):
    client.post(
        "/skus",
        json={"sku_id": "PROD-001", "name": "Widget"},
        headers={"X-API-Key": "test-key-12345"},
    )
    client.post(
        "/stock/PROD-001/adjust",
        json={"quantity": 100},
        headers={"X-API-Key": "test-key-12345"},
    )

    reservation_response = client.post(
        "/reservations",
        json={
            "sku_id": "PROD-001",
            "quantity": 10,
            "idempotency_key": "idem-key-1",
        },
        headers={"X-API-Key": "test-key-12345"},
    )
    reservation_id = reservation_response.json()["reservation_id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        json={"idempotency_key": "idem-key-1"},
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


def test_confirm_reservation_unauthorized(client):
    response = client.post(
        "/reservations/nonexistent/confirm",
        json={"idempotency_key": "idem-key-1"},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 401


def test_cancel_reservation_happy_path(client):
    client.post(
        "/skus",
        json={"sku_id": "PROD-001", "name": "Widget"},
        headers={"X-API-Key": "test-key-12345"},
    )
    client.post(
        "/stock/PROD-001/adjust",
        json={"quantity": 100},
        headers={"X-API-Key": "test-key-12345"},
    )

    reservation_response = client.post(
        "/reservations",
        json={
            "sku_id": "PROD-001",
            "quantity": 10,
            "idempotency_key": "idem-key-1",
        },
        headers={"X-API-Key": "test-key-12345"},
    )
    reservation_id = reservation_response.json()["reservation_id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        json={},
        headers={"X-API-Key": "test-key-12345"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_cancel_reservation_unauthorized(client):
    response = client.post(
        "/reservations/nonexistent/cancel",
        json={},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 401


def test_get_order(client):
    client.post(
        "/skus",
        json={"sku_id": "PROD-001", "name": "Widget"},
        headers={"X-API-Key": "test-key-12345"},
    )
    client.post(
        "/stock/PROD-001/adjust",
        json={"quantity": 100},
        headers={"X-API-Key": "test-key-12345"},
    )

    reservation_response = client.post(
        "/reservations",
        json={
            "sku_id": "PROD-001",
            "quantity": 10,
            "idempotency_key": "idem-key-1",
        },
        headers={"X-API-Key": "test-key-12345"},
    )
    reservation_id = reservation_response.json()["reservation_id"]

    order_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        json={"idempotency_key": "idem-key-1"},
        headers={"X-API-Key": "test-key-12345"},
    )
    order_id = order_response.json()["order_id"]

    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    assert response.json()["order_id"] == order_id


def test_get_nonexistent_order(client):
    response = client.get("/orders/nonexistent")
    assert response.status_code == 404


def test_list_orders_empty(client):
    response = client.get("/orders")
    assert response.status_code == 200
    assert response.json()["orders"] == []
    assert response.json()["next_cursor"] is None


def test_list_orders_with_pagination(client):
    client.post(
        "/skus",
        json={"sku_id": "PROD-001", "name": "Widget"},
        headers={"X-API-Key": "test-key-12345"},
    )
    client.post(
        "/stock/PROD-001/adjust",
        json={"quantity": 1000},
        headers={"X-API-Key": "test-key-12345"},
    )

    for i in range(15):
        reservation_response = client.post(
            "/reservations",
            json={
                "sku_id": "PROD-001",
                "quantity": 1,
                "idempotency_key": f"idem-key-{i}",
            },
            headers={"X-API-Key": "test-key-12345"},
        )
        reservation_id = reservation_response.json()["reservation_id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            json={"idempotency_key": f"idem-key-{i}"},
            headers={"X-API-Key": "test-key-12345"},
        )

    response = client.get("/orders?limit=10")
    assert response.status_code == 200
    assert len(response.json()["orders"]) == 10
    assert response.json()["next_cursor"] is not None

    response_page2 = client.get(f"/orders?limit=10&cursor={response.json()['next_cursor']}")
    assert len(response_page2.json()["orders"]) == 5
    assert response_page2.json()["next_cursor"] is None
