import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.app import app
from commerce_service.repository import Base, get_db


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"sku_name": "SKU-001", "initial_stock": 100},
    )
    assert response.status_code == 403


def test_create_sku_authorized(client):
    response = client.post(
        "/skus",
        json={"sku_name": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_name"] == "SKU-001"
    assert data["available_stock"] == 100


def test_create_sku_invalid_payload(client):
    response = client.post(
        "/skus",
        json={"sku_name": "", "initial_stock": -10},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 422


def test_adjust_stock(client):
    client.post(
        "/skus",
        json={"sku_name": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-key"},
    )

    response = client.post(
        "/stock/adjust",
        json={"sku_id": 1, "quantity_delta": 50},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    assert response.json()["available_stock"] == 150


def test_create_reservation_happy_path(client):
    client.post(
        "/skus",
        json={"sku_name": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-key"},
    )

    response = client.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["quantity"] == 50
    assert data["status"] == "pending"


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku_name": "SKU-001", "initial_stock": 10},
        headers={"X-API-Key": "test-key"},
    )

    response = client.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotent(client):
    client.post(
        "/skus",
        json={"sku_name": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-key"},
    )

    response1 = client.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-key"},
    )
    response2 = client.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-key"},
    )

    assert response1.status_code == 200
    assert response2.status_code == 200
    assert response1.json()["id"] == response2.json()["id"]


def test_confirm_reservation(client):
    client.post(
        "/skus",
        json={"sku_name": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-key"},
    )

    res_response = client.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-key"},
    )
    reservation_id = res_response.json()["id"]

    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-key"},
    )
    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "confirmed"


def test_cancel_reservation(client):
    client.post(
        "/skus",
        json={"sku_name": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-key"},
    )

    res_response = client.post(
        "/reservations",
        json={"sku_id": 1, "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-key"},
    )
    reservation_id = res_response.json()["id"]

    cancel_response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": "test-key"},
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"


def test_list_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku_name": "SKU-001", "initial_stock": 500},
        headers={"X-API-Key": "test-key"},
    )

    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 10, "idempotency_key": f"key-{i}"},
            headers={"X-API-Key": "test-key"},
        )
        reservation_id = res_response.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": "test-key"},
        )

    response = client.get("/orders?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 10
    assert data["total"] == 25
    assert data["limit"] == 10
    assert data["offset"] == 0


def test_list_orders_invalid_pagination(client):
    response = client.get("/orders?limit=0&offset=0")
    assert response.status_code == 400

    response = client.get("/orders?limit=200&offset=0")
    assert response.status_code == 400

    response = client.get("/orders?limit=10&offset=-1")
    assert response.status_code == 400


def test_unauthorized_mutation(client):
    response = client.post(
        "/skus",
        json={"sku_name": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 403
