import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.app import app, get_db
from commerce_service.models import Base, init_db, get_session_factory


@pytest.fixture
def test_db():
    database_url = "sqlite:///:memory:"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    db = SessionLocal()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield db
    db.close()


@pytest.fixture
def client(test_db):
    return TestClient(app)


def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_authorized(client: TestClient):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key-12345"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["initial_stock"] == 100
    assert data["available_stock"] == 100


def test_create_sku_unauthorized(client: TestClient):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
    )
    assert response.status_code == 403


def test_create_sku_invalid_api_key(client: TestClient):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 401


def test_adjust_stock(client: TestClient):
    api_key = {"X-API-Key": "test-api-key-12345"}

    client.post("/skus", json={"sku": "SKU-002", "initial_stock": 50}, headers=api_key)

    response = client.post(
        "/stock/adjust", json={"sku": "SKU-002", "amount": 20}, headers=api_key
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "SKU-002"
    assert data["available_stock"] == 70


def test_create_reservation_success(client: TestClient):
    api_key = {"X-API-Key": "test-api-key-12345"}

    client.post("/skus", json={"sku": "SKU-003", "initial_stock": 100}, headers=api_key)

    response = client.post(
        "/reservations",
        json={"sku": "SKU-003", "quantity": 30, "idempotency_key": "idempotency-1"},
        headers=api_key,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-003"
    assert data["quantity"] == 30
    assert data["status"] == "PENDING"


def test_create_reservation_insufficient_stock(client: TestClient):
    api_key = {"X-API-Key": "test-api-key-12345"}

    client.post("/skus", json={"sku": "SKU-004", "initial_stock": 50}, headers=api_key)

    response = client.post(
        "/reservations",
        json={"sku": "SKU-004", "quantity": 100, "idempotency_key": "idempotency-2"},
        headers=api_key,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_create_reservation_idempotent(client: TestClient):
    api_key = {"X-API-Key": "test-api-key-12345"}

    client.post("/skus", json={"sku": "SKU-005", "initial_stock": 100}, headers=api_key)

    response1 = client.post(
        "/reservations",
        json={"sku": "SKU-005", "quantity": 25, "idempotency_key": "idempotency-3"},
        headers=api_key,
    )
    assert response1.status_code == 201
    data1 = response1.json()

    response2 = client.post(
        "/reservations",
        json={"sku": "SKU-005", "quantity": 25, "idempotency_key": "idempotency-3"},
        headers=api_key,
    )
    assert response2.status_code == 201
    data2 = response2.json()

    assert data1["id"] == data2["id"]

    response = client.get("/orders")
    assert response.status_code == 200
    orders_data = response.json()
    assert orders_data["total"] == 0


def test_confirm_reservation_success(client: TestClient):
    api_key = {"X-API-Key": "test-api-key-12345"}

    client.post("/skus", json={"sku": "SKU-006", "initial_stock": 100}, headers=api_key)

    res = client.post(
        "/reservations",
        json={"sku": "SKU-006", "quantity": 20, "idempotency_key": "idempotency-4"},
        headers=api_key,
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm", headers=api_key
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CONFIRMED"
    assert data["reservation_id"] == reservation_id


def test_confirm_reservation_expired(client: TestClient, test_db):
    api_key = {"X-API-Key": "test-api-key-12345"}

    client.post("/skus", json={"sku": "SKU-007", "initial_stock": 100}, headers=api_key)

    res = client.post(
        "/reservations",
        json={"sku": "SKU-007", "quantity": 20, "idempotency_key": "idempotency-5"},
        headers=api_key,
    )
    reservation_id = res.json()["id"]

    from commerce_service.models import ReservationOrm

    reservation = test_db.query(ReservationOrm).filter_by(id=reservation_id).first()
    past_time = datetime.now(timezone.utc) - timedelta(seconds=301)
    reservation.created_at = past_time
    test_db.commit()

    response = client.post(
        f"/reservations/{reservation_id}/confirm", headers=api_key
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Reservation expired"

    updated_reservation = (
        test_db.query(ReservationOrm).filter_by(id=reservation_id).first()
    )
    assert updated_reservation.status == "EXPIRED"


def test_cancel_reservation_success(client: TestClient):
    api_key = {"X-API-Key": "test-api-key-12345"}

    client.post("/skus", json={"sku": "SKU-008", "initial_stock": 100}, headers=api_key)

    res = client.post(
        "/reservations",
        json={"sku": "SKU-008", "quantity": 25, "idempotency_key": "idempotency-6"},
        headers=api_key,
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel", headers=api_key
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"


def test_get_orders_pagination(client: TestClient):
    api_key = {"X-API-Key": "test-api-key-12345"}

    client.post("/skus", json={"sku": "SKU-009", "initial_stock": 1000}, headers=api_key)

    for i in range(25):
        res = client.post(
            "/reservations",
            json={"sku": "SKU-009", "quantity": 10, "idempotency_key": f"idempotency-{i}"},
            headers=api_key,
        )
        reservation_id = res.json()["id"]
        client.post(f"/reservations/{reservation_id}/confirm", headers=api_key)

    response = client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["total"] == 25
    assert data["page"] == 1
    assert data["size"] == 10

    response = client.get("/orders?page=2&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10

    response = client.get("/orders?page=3&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 5


def test_happy_path_workflow(client: TestClient):
    api_key = {"X-API-Key": "test-api-key-12345"}

    sku_response = client.post(
        "/skus", json={"sku": "SKU-HAPPY", "initial_stock": 200}, headers=api_key
    )
    assert sku_response.status_code == 201

    reservation_response = client.post(
        "/reservations",
        json={"sku": "SKU-HAPPY", "quantity": 50, "idempotency_key": "happy-1"},
        headers=api_key,
    )
    assert reservation_response.status_code == 201
    reservation_id = reservation_response.json()["id"]

    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm", headers=api_key
    )
    assert confirm_response.status_code == 200
    order_id = confirm_response.json()["id"]

    orders_response = client.get("/orders")
    assert orders_response.status_code == 200
    orders_data = orders_response.json()
    assert orders_data["total"] >= 1

    found_order = any(order["id"] == order_id for order in orders_data["items"])
    assert found_order
