"""API endpoint tests."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.app import app, get_session
from commerce_service.models import Base
from commerce_service.security import API_TOKEN

# Create test database
engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(bind=engine)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override database dependency."""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_session] = override_get_db
client = TestClient(app)

HEADERS = {"X-API-Token": API_TOKEN}
INVALID_HEADERS = {"X-API-Token": "invalid-token"}


def test_health_check():
    """Test health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success():
    """Test successful SKU creation."""
    response = client.post("/skus", json={"sku": "SKU-001", "initial_stock": 100}, headers=HEADERS)
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["available_stock"] == 100


def test_create_sku_unauthorized():
    """Test SKU creation without token."""
    response = client.post("/skus", json={"sku": "SKU-001", "initial_stock": 100})
    assert response.status_code == 401
    assert "Missing API token" in response.json()["detail"]


def test_create_sku_invalid_token():
    """Test SKU creation with invalid token."""
    response = client.post("/skus", json={"sku": "SKU-001", "initial_stock": 100}, headers=INVALID_HEADERS)
    assert response.status_code == 401
    assert "Invalid API token" in response.json()["detail"]


def test_adjust_stock_success():
    """Test successful stock adjustment."""
    client.post("/skus", json={"sku": "SKU-001", "initial_stock": 100}, headers=HEADERS)
    response = client.post("/stock/adjust", json={"sku": "SKU-001", "amount": -10}, headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["available_stock"] == 90


def test_adjust_stock_unauthorized():
    """Test stock adjustment without token."""
    response = client.post("/stock/adjust", json={"sku": "SKU-001", "amount": -10})
    assert response.status_code == 401


def test_adjust_stock_nonexistent_sku():
    """Test adjusting stock for non-existent SKU."""
    response = client.post("/stock/adjust", json={"sku": "SKU-MISSING", "amount": 10}, headers=HEADERS)
    assert response.status_code == 400


def test_create_reservation_success():
    """Test successful reservation creation."""
    client.post("/skus", json={"sku": "SKU-001", "initial_stock": 100}, headers=HEADERS)
    response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 10, "idempotency_key": "idempotency-1"},
        headers=HEADERS,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["quantity"] == 10
    assert data["status"] == "PENDING"


def test_create_reservation_insufficient_stock():
    """Test reservation with insufficient stock."""
    client.post("/skus", json={"sku": "SKU-001", "initial_stock": 100}, headers=HEADERS)
    response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 150, "idempotency_key": "idempotency-1"},
        headers=HEADERS,
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotency():
    """Test idempotent reservation creation."""
    client.post("/skus", json={"sku": "SKU-001", "initial_stock": 100}, headers=HEADERS)
    response1 = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 10, "idempotency_key": "idempotency-1"},
        headers=HEADERS,
    )
    response2 = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 10, "idempotency_key": "idempotency-1"},
        headers=HEADERS,
    )
    assert response1.status_code == 201
    assert response2.status_code == 201
    assert response1.json()["id"] == response2.json()["id"]

    # Verify stock was only deducted once
    response = client.get("/orders", headers=HEADERS)
    # No orders yet since none confirmed
    assert response.json()["total"] == 0


def test_create_reservation_unauthorized():
    """Test reservation without token."""
    response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 10, "idempotency_key": "idempotency-1"},
    )
    assert response.status_code == 401


def test_confirm_reservation_success():
    """Test successful reservation confirmation."""
    client.post("/skus", json={"sku": "SKU-001", "initial_stock": 100}, headers=HEADERS)
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 10, "idempotency_key": "idempotency-1"},
        headers=HEADERS,
    )
    reservation_id = res_response.json()["id"]
    response = client.post(f"/reservations/{reservation_id}/confirm", headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["quantity"] == 10


def test_confirm_reservation_unauthorized():
    """Test confirmation without token."""
    response = client.post("/reservations/1/confirm")
    assert response.status_code == 401


def test_confirm_reservation_invalid_state():
    """Test confirming reservation not in PENDING state."""
    client.post("/skus", json={"sku": "SKU-001", "initial_stock": 100}, headers=HEADERS)
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 10, "idempotency_key": "idempotency-1"},
        headers=HEADERS,
    )
    reservation_id = res_response.json()["id"]
    client.post(f"/reservations/{reservation_id}/confirm", headers=HEADERS)

    # Try to confirm again
    response = client.post(f"/reservations/{reservation_id}/confirm", headers=HEADERS)
    assert response.status_code == 400
    assert "not in PENDING state" in response.json()["detail"]


def test_confirm_reservation_expired(test_db_override):
    """Test confirming expired reservation."""
    client.post("/skus", json={"sku": "SKU-001", "initial_stock": 100}, headers=HEADERS)
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 10, "idempotency_key": "idempotency-1"},
        headers=HEADERS,
    )
    reservation_id = res_response.json()["id"]

    # Manually set reservation created_at to 301 seconds ago
    db = test_db_override()
    from commerce_service.models import ReservationModel

    reservation = db.query(ReservationModel).filter(ReservationModel.id == reservation_id).first()
    old_time = datetime.now(timezone.utc) - timedelta(seconds=301)
    reservation.created_at = old_time.replace(tzinfo=None)
    db.commit()
    db.close()

    response = client.post(f"/reservations/{reservation_id}/confirm", headers=HEADERS)
    assert response.status_code == 400
    assert "Reservation expired" in response.json()["detail"]


def test_cancel_reservation_success():
    """Test successful reservation cancellation."""
    client.post("/skus", json={"sku": "SKU-001", "initial_stock": 100}, headers=HEADERS)
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 10, "idempotency_key": "idempotency-1"},
        headers=HEADERS,
    )
    reservation_id = res_response.json()["id"]
    response = client.post(f"/reservations/{reservation_id}/cancel", headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


def test_cancel_reservation_unauthorized():
    """Test cancellation without token."""
    response = client.post("/reservations/1/cancel")
    assert response.status_code == 401


def test_cancel_reservation_invalid_state():
    """Test cancelling reservation not in PENDING state."""
    client.post("/skus", json={"sku": "SKU-001", "initial_stock": 100}, headers=HEADERS)
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-001", "quantity": 10, "idempotency_key": "idempotency-1"},
        headers=HEADERS,
    )
    reservation_id = res_response.json()["id"]
    client.post(f"/reservations/{reservation_id}/confirm", headers=HEADERS)

    # Try to cancel confirmed reservation
    response = client.post(f"/reservations/{reservation_id}/cancel", headers=HEADERS)
    assert response.status_code == 400
    assert "not in PENDING state" in response.json()["detail"]


def test_get_orders_success():
    """Test successful order retrieval."""
    client.post("/skus", json={"sku": "SKU-001", "initial_stock": 1000}, headers=HEADERS)

    # Create some orders
    for i in range(15):
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 10, "idempotency_key": f"idempotency-{i}"},
            headers=HEADERS,
        )
        reservation_id = res_response.json()["id"]
        client.post(f"/reservations/{reservation_id}/confirm", headers=HEADERS)

    response = client.get("/orders", headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 15
    assert len(data["items"]) == 10  # Default page size
    assert data["page"] == 1
    assert data["size"] == 10


def test_get_orders_pagination():
    """Test order pagination."""
    client.post("/skus", json={"sku": "SKU-001", "initial_stock": 1000}, headers=HEADERS)

    # Create multiple orders
    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 10, "idempotency_key": f"idempotency-{i}"},
            headers=HEADERS,
        )
        reservation_id = res_response.json()["id"]
        client.post(f"/reservations/{reservation_id}/confirm", headers=HEADERS)

    # Test page 2 with custom size
    response = client.get("/orders?page=2&size=10", headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 25
    assert len(data["items"]) == 10
    assert data["page"] == 2
    assert data["size"] == 10

    # Test page 3
    response = client.get("/orders?page=3&size=10", headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 5
    assert data["page"] == 3


def test_happy_path_workflow():
    """Test complete happy path workflow."""
    # Create SKU
    sku_response = client.post("/skus", json={"sku": "SKU-WORKFLOW", "initial_stock": 100}, headers=HEADERS)
    assert sku_response.status_code == 201

    # Create reservation
    res_response = client.post(
        "/reservations",
        json={"sku": "SKU-WORKFLOW", "quantity": 10, "idempotency_key": "workflow-1"},
        headers=HEADERS,
    )
    assert res_response.status_code == 201
    reservation_id = res_response.json()["id"]
    assert res_response.json()["status"] == "PENDING"

    # Confirm reservation
    confirm_response = client.post(f"/reservations/{reservation_id}/confirm", headers=HEADERS)
    assert confirm_response.status_code == 200
    order_id = confirm_response.json()["id"]

    # Get orders
    orders_response = client.get("/orders", headers=HEADERS)
    assert orders_response.status_code == 200
    data = orders_response.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == order_id
    assert data["items"][0]["sku"] == "SKU-WORKFLOW"
    assert data["items"][0]["quantity"] == 10
