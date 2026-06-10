"""API endpoint tests."""

import pytest
import tempfile
import os
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

from src.commerce_service.app import app
from src.commerce_service.repository import Repository
from src.commerce_service.service import CommerceService


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    db_url = f"sqlite:///{db_path}"
    yield db_url
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def test_client(temp_db):
    """Create a test client with a temporary database."""
    from src.commerce_service import app as app_module

    app_module.repository = Repository(temp_db)
    app_module.service = CommerceService(app_module.repository)

    return TestClient(app)


def test_health_check(test_client):
    """Test health endpoint requires no authentication."""
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_missing_api_key(test_client):
    """Test that missing API key returns 401."""
    response = test_client.post("/skus", json={"sku": "SKU-001", "initial_stock": 100})
    assert response.status_code == 401


def test_invalid_api_key(test_client):
    """Test that invalid API key returns 401."""
    response = test_client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "wrong-key"}
    )
    assert response.status_code == 401


def test_create_sku(test_client):
    """Test creating a SKU."""
    response = test_client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"}
    )
    assert response.status_code == 201
    assert response.json() == {"sku": "SKU-001", "stock": 100}


def test_adjust_stock(test_client):
    """Test adjusting stock for a SKU."""
    # Create SKU first
    test_client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"}
    )

    # Adjust stock
    response = test_client.post(
        "/stock/adjust",
        json={"sku": "SKU-001", "amount": -20},
        headers={"X-API-Key": "test-api-key"}
    )
    assert response.status_code == 200
    assert response.json() == {"sku": "SKU-001", "stock": 80}


def test_insufficient_stock_rejection(test_client):
    """Test that reservation with insufficient stock returns 400."""
    # Create SKU with limited stock
    test_client.post(
        "/skus",
        json={"sku": "SKU-002", "initial_stock": 5},
        headers={"X-API-Key": "test-api-key"}
    )

    # Try to reserve more than available
    response = test_client.post(
        "/reservations",
        json={"sku": "SKU-002", "quantity": 10, "idempotency_key": "key-001"},
        headers={"X-API-Key": "test-api-key"}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_happy_path_workflow(test_client):
    """Test the happy path: SKU -> Reserve -> Confirm -> Order lookup."""
    # Create SKU
    test_client.post(
        "/skus",
        json={"sku": "SKU-003", "initial_stock": 50},
        headers={"X-API-Key": "test-api-key"}
    )

    # Create reservation
    res_response = test_client.post(
        "/reservations",
        json={"sku": "SKU-003", "quantity": 10, "idempotency_key": "key-003"},
        headers={"X-API-Key": "test-api-key"}
    )
    assert res_response.status_code == 201
    reservation_id = res_response.json()["id"]
    assert res_response.json()["status"] == "PENDING"

    # Confirm reservation
    confirm_response = test_client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-api-key"}
    )
    assert confirm_response.status_code == 200
    assert confirm_response.json()["reservation_id"] == reservation_id

    # Get orders
    orders_response = test_client.get(
        "/orders",
        headers={"X-API-Key": "test-api-key"}
    )
    assert orders_response.status_code == 200
    assert orders_response.json()["total"] == 1
    assert orders_response.json()["orders"][0]["reservation_id"] == reservation_id


def test_idempotent_reservation(test_client):
    """Test that idempotent retry returns matching data without double-deduction."""
    # Create SKU
    test_client.post(
        "/skus",
        json={"sku": "SKU-004", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"}
    )

    # Create reservation
    res1 = test_client.post(
        "/reservations",
        json={"sku": "SKU-004", "quantity": 20, "idempotency_key": "key-004"},
        headers={"X-API-Key": "test-api-key"}
    )
    assert res1.status_code == 201
    reservation_id_1 = res1.json()["id"]

    # Retry with same idempotency key
    res2 = test_client.post(
        "/reservations",
        json={"sku": "SKU-004", "quantity": 20, "idempotency_key": "key-004"},
        headers={"X-API-Key": "test-api-key"}
    )
    assert res2.status_code == 201
    assert res2.json()["id"] == reservation_id_1

    # Check stock was only deducted once
    from src.commerce_service.app import repository
    stock = repository.get_sku_stock("SKU-004")
    assert stock == 80  # 100 - 20, not 100 - 20 - 20


def test_expired_reservation(test_client):
    """Test that expired reservation cannot be confirmed."""
    from src.commerce_service import app as app_module
    from src.commerce_service.repository import Reservation
    from datetime import datetime

    # Create SKU
    test_client.post(
        "/skus",
        json={"sku": "SKU-005", "initial_stock": 50},
        headers={"X-API-Key": "test-api-key"}
    )

    # Create reservation
    res_response = test_client.post(
        "/reservations",
        json={"sku": "SKU-005", "quantity": 10, "idempotency_key": "key-005"},
        headers={"X-API-Key": "test-api-key"}
    )
    reservation_id = res_response.json()["id"]

    # Manually update reservation created_at to be older than 300 seconds
    session = app_module.repository.get_session()
    try:
        res = session.query(Reservation).filter(Reservation.id == reservation_id).first()
        res.created_at = datetime.utcnow() - timedelta(seconds=301)
        session.commit()
    finally:
        session.close()

    # Try to confirm expired reservation
    confirm_response = test_client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-api-key"}
    )
    assert confirm_response.status_code == 400
    assert "expired" in confirm_response.json()["detail"].lower()

    # Verify stock was restored
    stock = app_module.repository.get_sku_stock("SKU-005")
    assert stock == 50  # Stock should be restored


def test_cancel_reservation(test_client):
    """Test cancelling a reservation restores stock."""
    # Create SKU
    test_client.post(
        "/skus",
        json={"sku": "SKU-006", "initial_stock": 60},
        headers={"X-API-Key": "test-api-key"}
    )

    # Create reservation
    res_response = test_client.post(
        "/reservations",
        json={"sku": "SKU-006", "quantity": 15, "idempotency_key": "key-006"},
        headers={"X-API-Key": "test-api-key"}
    )
    reservation_id = res_response.json()["id"]

    # Cancel reservation
    cancel_response = test_client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": "test-api-key"}
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "CANCELLED"

    # Verify stock was restored
    from src.commerce_service.app import repository
    stock = repository.get_sku_stock("SKU-006")
    assert stock == 60


def test_pagination(test_client):
    """Test pagination of orders."""
    # Create SKU
    test_client.post(
        "/skus",
        json={"sku": "SKU-007", "initial_stock": 1000},
        headers={"X-API-Key": "test-api-key"}
    )

    # Create and confirm multiple reservations
    for i in range(15):
        res_response = test_client.post(
            "/reservations",
            json={"sku": "SKU-007", "quantity": 10, "idempotency_key": f"key-007-{i}"},
            headers={"X-API-Key": "test-api-key"}
        )
        reservation_id = res_response.json()["id"]
        test_client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": "test-api-key"}
        )

    # Get first page
    page1 = test_client.get(
        "/orders?page=1&size=10",
        headers={"X-API-Key": "test-api-key"}
    )
    assert page1.status_code == 200
    assert page1.json()["page"] == 1
    assert page1.json()["size"] == 10
    assert len(page1.json()["orders"]) == 10
    assert page1.json()["total"] == 15

    # Get second page
    page2 = test_client.get(
        "/orders?page=2&size=10",
        headers={"X-API-Key": "test-api-key"}
    )
    assert page2.status_code == 200
    assert page2.json()["page"] == 2
    assert len(page2.json()["orders"]) == 5


def test_invalid_state_transitions(test_client):
    """Test that invalid state transitions are rejected."""
    # Create SKU and reservation
    test_client.post(
        "/skus",
        json={"sku": "SKU-008", "initial_stock": 50},
        headers={"X-API-Key": "test-api-key"}
    )

    res_response = test_client.post(
        "/reservations",
        json={"sku": "SKU-008", "quantity": 10, "idempotency_key": "key-008"},
        headers={"X-API-Key": "test-api-key"}
    )
    reservation_id = res_response.json()["id"]

    # Confirm it
    test_client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-api-key"}
    )

    # Try to cancel a CONFIRMED reservation (should fail)
    cancel_response = test_client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": "test-api-key"}
    )
    assert cancel_response.status_code == 400
