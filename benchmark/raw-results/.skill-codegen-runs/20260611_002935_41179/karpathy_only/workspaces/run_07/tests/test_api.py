"""API endpoint tests."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.app import app
from commerce_service.repository import Base, get_db
from commerce_service.security import API_KEY


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    """Create a test client with overridden database dependency."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client):
    """Test successful SKU creation."""
    response = client.post(
        "/skus",
        json={"sku": "TEST-001", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "TEST-001"
    assert data["available_stock"] == 100


def test_create_sku_missing_api_key(client):
    """Test SKU creation without API key."""
    response = client.post(
        "/skus",
        json={"sku": "TEST-002", "initial_stock": 100},
    )
    assert response.status_code == 403


def test_create_sku_invalid_api_key(client):
    """Test SKU creation with invalid API key."""
    response = client.post(
        "/skus",
        json={"sku": "TEST-003", "initial_stock": 100},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401


def test_adjust_stock_success(client):
    """Test successful stock adjustment."""
    client.post(
        "/skus",
        json={"sku": "TEST-004", "initial_stock": 50},
        headers={"X-API-Key": API_KEY},
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "TEST-004", "amount": 25},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "TEST-004"
    assert data["available_stock"] == 75


def test_adjust_stock_negative(client):
    """Test negative stock adjustment."""
    client.post(
        "/skus",
        json={"sku": "TEST-005", "initial_stock": 50},
        headers={"X-API-Key": API_KEY},
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "TEST-005", "amount": -20},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 30


def test_create_reservation_success(client):
    """Test successful reservation creation."""
    client.post(
        "/skus",
        json={"sku": "TEST-006", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    response = client.post(
        "/reservations",
        json={"sku": "TEST-006", "quantity": 20, "idempotency_key": "key-001"},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "TEST-006"
    assert data["quantity"] == 20
    assert data["status"] == "PENDING"


def test_create_reservation_insufficient_stock(client):
    """Test reservation creation with insufficient stock."""
    client.post(
        "/skus",
        json={"sku": "TEST-007", "initial_stock": 10},
        headers={"X-API-Key": API_KEY},
    )

    response = client.post(
        "/reservations",
        json={"sku": "TEST-007", "quantity": 20, "idempotency_key": "key-002"},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_reservation_idempotency(client):
    """Test idempotent reservation returns same result without double-deduction."""
    client.post(
        "/skus",
        json={"sku": "TEST-008", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    response1 = client.post(
        "/reservations",
        json={"sku": "TEST-008", "quantity": 30, "idempotency_key": "idempotent-key-1"},
        headers={"X-API-Key": API_KEY},
    )
    assert response1.status_code == 201
    data1 = response1.json()
    res_id = data1["id"]

    sku_check = client.post(
        "/stock/adjust",
        json={"sku": "TEST-008", "amount": 0},
        headers={"X-API-Key": API_KEY},
    )
    assert sku_check.json()["available_stock"] == 70

    response2 = client.post(
        "/reservations",
        json={"sku": "TEST-008", "quantity": 30, "idempotency_key": "idempotent-key-1"},
        headers={"X-API-Key": API_KEY},
    )
    assert response2.status_code == 201
    data2 = response2.json()
    assert data2["id"] == res_id

    sku_check2 = client.post(
        "/stock/adjust",
        json={"sku": "TEST-008", "amount": 0},
        headers={"X-API-Key": API_KEY},
    )
    assert sku_check2.json()["available_stock"] == 70


def test_confirm_reservation_success(client):
    """Test successful reservation confirmation."""
    client.post(
        "/skus",
        json={"sku": "TEST-009", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "TEST-009", "quantity": 25, "idempotency_key": "confirm-key-1"},
        headers={"X-API-Key": API_KEY},
    )
    res_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CONFIRMED"
    assert data["order_id"] == 1


def test_confirm_reservation_invalid_status(client):
    """Test confirmation of reservation not in PENDING status."""
    client.post(
        "/skus",
        json={"sku": "TEST-010", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "TEST-010", "quantity": 25, "idempotency_key": "confirm-key-2"},
        headers={"X-API-Key": API_KEY},
    )
    res_id = res_response.json()["id"]

    client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 400


def test_confirm_reservation_expired(client):
    """Test confirmation of expired reservation."""
    from datetime import datetime, timedelta
    from commerce_service.repository import SessionLocal, ReservationModel

    client.post(
        "/skus",
        json={"sku": "TEST-011", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "TEST-011", "quantity": 25, "idempotency_key": "expired-key-1"},
        headers={"X-API-Key": API_KEY},
    )
    res_id = res_response.json()["id"]

    db = SessionLocal()
    reservation = db.query(ReservationModel).filter(ReservationModel.id == res_id).first()
    reservation.created_at = datetime.utcnow() - timedelta(seconds=301)
    db.commit()
    db.close()

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Reservation expired"


def test_cancel_reservation_success(client):
    """Test successful reservation cancellation."""
    client.post(
        "/skus",
        json={"sku": "TEST-012", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "TEST-012", "quantity": 25, "idempotency_key": "cancel-key-1"},
        headers={"X-API-Key": API_KEY},
    )
    res_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"
    assert data["stock_restored"] == 25

    sku_check = client.post(
        "/stock/adjust",
        json={"sku": "TEST-012", "amount": 0},
        headers={"X-API-Key": API_KEY},
    )
    assert sku_check.json()["available_stock"] == 100


def test_cancel_reservation_invalid_status(client):
    """Test cancellation of reservation not in PENDING status."""
    client.post(
        "/skus",
        json={"sku": "TEST-013", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "TEST-013", "quantity": 25, "idempotency_key": "cancel-key-2"},
        headers={"X-API-Key": API_KEY},
    )
    res_id = res_response.json()["id"]

    client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 400


def test_get_orders_pagination(client):
    """Test pagination on GET /orders endpoint."""
    client.post(
        "/skus",
        json={"sku": "TEST-014", "initial_stock": 200},
        headers={"X-API-Key": API_KEY},
    )

    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={"sku": "TEST-014", "quantity": 1, "idempotency_key": f"order-key-{i}"},
            headers={"X-API-Key": API_KEY},
        )
        res_id = res_response.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": API_KEY},
        )

    response = client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 10
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] == 25

    response = client.get("/orders?page=2&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 10
    assert data["page"] == 2

    response = client.get("/orders?page=3&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 5
    assert data["page"] == 3


def test_get_orders_default_pagination(client):
    """Test GET /orders with default pagination parameters."""
    client.post(
        "/skus",
        json={"sku": "TEST-015", "initial_stock": 100},
        headers={"X-API-Key": API_KEY},
    )

    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] == 0


def test_happy_path_workflow(client):
    """Test complete workflow: SKU -> Reserve -> Confirm -> Order lookup."""
    client.post(
        "/skus",
        json={"sku": "TEST-HAPPY", "initial_stock": 150},
        headers={"X-API-Key": API_KEY},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "TEST-HAPPY", "quantity": 50, "idempotency_key": "happy-key-1"},
        headers={"X-API-Key": API_KEY},
    )
    assert res_response.status_code == 201
    res_id = res_response.json()["id"]
    assert res_response.json()["status"] == "PENDING"

    confirm_response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )
    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "CONFIRMED"
    order_id = confirm_response.json()["order_id"]

    orders_response = client.get("/orders?page=1&size=10")
    assert orders_response.status_code == 200
    orders_data = orders_response.json()
    assert len(orders_data["orders"]) == 1
    assert orders_data["orders"][0]["id"] == order_id
    assert orders_data["orders"][0]["reservation_id"] == res_id
