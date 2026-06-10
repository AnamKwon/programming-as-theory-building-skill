import pytest
from fastapi.testclient import TestClient
import tempfile
from pathlib import Path

from commerce_service.app import app
from commerce_service.repository import Repository
from commerce_service.service import CommerceService


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield db_path


@pytest.fixture
def client(temp_db, monkeypatch):
    """Create a test client with a temporary database."""
    monkeypatch.setattr(
        "commerce_service.app.repo", Repository(temp_db)
    )
    monkeypatch.setattr(
        "commerce_service.app.service", CommerceService(Repository(temp_db))
    )
    return TestClient(app)


@pytest.fixture
def valid_headers():
    """Return valid API key headers."""
    return {"X-API-Key": "commerce-secret-key-12345"}


@pytest.fixture
def invalid_headers():
    """Return invalid API key headers."""
    return {"X-API-Key": "invalid-key"}


def test_health_check(client):
    """Test health endpoint (no auth required)."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client, valid_headers):
    """Test successful SKU creation."""
    response = client.post(
        "/skus",
        json={"sku": "TEST-SKU-001", "initial_stock": 100},
        headers=valid_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "TEST-SKU-001"
    assert data["available_stock"] == 100


def test_create_sku_missing_auth(client):
    """Test SKU creation without API key."""
    response = client.post(
        "/skus",
        json={"sku": "TEST-SKU-002", "initial_stock": 100},
    )
    assert response.status_code == 401


def test_create_sku_invalid_auth(client, invalid_headers):
    """Test SKU creation with invalid API key."""
    response = client.post(
        "/skus",
        json={"sku": "TEST-SKU-003", "initial_stock": 100},
        headers=invalid_headers,
    )
    assert response.status_code == 401


def test_adjust_stock_success(client, valid_headers):
    """Test successful stock adjustment."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-004", "initial_stock": 50},
        headers=valid_headers,
    )
    response = client.post(
        "/stock/adjust",
        json={"sku": "TEST-SKU-004", "amount": 25},
        headers=valid_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 75


def test_create_reservation_success(client, valid_headers):
    """Test successful reservation creation."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-005", "initial_stock": 100},
        headers=valid_headers,
    )
    response = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU-005",
            "quantity": 30,
            "idempotency_key": "key-1",
        },
        headers=valid_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "TEST-SKU-005"
    assert data["quantity"] == 30
    assert data["status"] == "PENDING"


def test_create_reservation_insufficient_stock(client, valid_headers):
    """Test reservation with insufficient stock."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-006", "initial_stock": 20},
        headers=valid_headers,
    )
    response = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU-006",
            "quantity": 30,
            "idempotency_key": "key-2",
        },
        headers=valid_headers,
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotent(client, valid_headers):
    """Test idempotent reservation creation."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-007", "initial_stock": 100},
        headers=valid_headers,
    )
    response1 = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU-007",
            "quantity": 25,
            "idempotency_key": "key-3",
        },
        headers=valid_headers,
    )
    response2 = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU-007",
            "quantity": 25,
            "idempotency_key": "key-3",
        },
        headers=valid_headers,
    )

    assert response1.status_code == 201
    assert response2.status_code == 201
    data1 = response1.json()
    data2 = response2.json()
    assert data1["id"] == data2["id"]

    sku_response = client.get("/health")
    assert sku_response.status_code == 200


def test_confirm_reservation_success(client, valid_headers):
    """Test successful reservation confirmation."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-008", "initial_stock": 100},
        headers=valid_headers,
    )
    res_response = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU-008",
            "quantity": 20,
            "idempotency_key": "key-4",
        },
        headers=valid_headers,
    )
    res_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers=valid_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CONFIRMED"
    assert data["confirmed_at"] is not None


def test_confirm_reservation_not_pending(client, valid_headers):
    """Test confirming a non-pending reservation."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-009", "initial_stock": 100},
        headers=valid_headers,
    )
    res_response = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU-009",
            "quantity": 20,
            "idempotency_key": "key-5",
        },
        headers=valid_headers,
    )
    res_id = res_response.json()["id"]

    client.post(f"/reservations/{res_id}/cancel", headers=valid_headers)
    response = client.post(f"/reservations/{res_id}/confirm", headers=valid_headers)
    assert response.status_code == 400


def test_cancel_reservation_success(client, valid_headers):
    """Test successful reservation cancellation."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-010", "initial_stock": 100},
        headers=valid_headers,
    )
    res_response = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU-010",
            "quantity": 20,
            "idempotency_key": "key-6",
        },
        headers=valid_headers,
    )
    res_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers=valid_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"


def test_get_orders_success(client, valid_headers):
    """Test getting orders with pagination."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-011", "initial_stock": 1000},
        headers=valid_headers,
    )

    for i in range(5):
        res_response = client.post(
            "/reservations",
            json={
                "sku": "TEST-SKU-011",
                "quantity": 10,
                "idempotency_key": f"key-order-{i}",
            },
            headers=valid_headers,
        )
        res_id = res_response.json()["id"]
        client.post(f"/reservations/{res_id}/confirm", headers=valid_headers)

    response = client.get("/orders?page=1&size=10", headers=valid_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert data["page"] == 1
    assert data["size"] == 10
    assert len(data["items"]) == 5


def test_get_orders_pagination(client, valid_headers):
    """Test orders pagination offset behavior."""
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-012", "initial_stock": 1000},
        headers=valid_headers,
    )

    order_ids = []
    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={
                "sku": "TEST-SKU-012",
                "quantity": 10,
                "idempotency_key": f"key-pag-{i}",
            },
            headers=valid_headers,
        )
        res_id = res_response.json()["id"]
        confirm_response = client.post(
            f"/reservations/{res_id}/confirm", headers=valid_headers
        )
        order_ids.append(confirm_response.json()["id"])

    page1 = client.get("/orders?page=1&size=10", headers=valid_headers)
    assert page1.status_code == 200
    data1 = page1.json()
    assert data1["total"] == 25
    assert data1["total_pages"] == 3
    assert len(data1["items"]) == 10

    page2 = client.get("/orders?page=2&size=10", headers=valid_headers)
    data2 = page2.json()
    assert len(data2["items"]) == 10

    page3 = client.get("/orders?page=3&size=10", headers=valid_headers)
    data3 = page3.json()
    assert len(data3["items"]) == 5


def test_get_orders_no_auth(client):
    """Test getting orders without authentication."""
    response = client.get("/orders")
    assert response.status_code == 401


def test_happy_path_complete_workflow(client, valid_headers):
    """Test complete happy path: SKU -> Reserve -> Confirm -> Order."""
    sku_response = client.post(
        "/skus",
        json={"sku": "COMPLETE-TEST", "initial_stock": 100},
        headers=valid_headers,
    )
    assert sku_response.status_code == 201

    res_response = client.post(
        "/reservations",
        json={
            "sku": "COMPLETE-TEST",
            "quantity": 25,
            "idempotency_key": "complete-key",
        },
        headers=valid_headers,
    )
    assert res_response.status_code == 201
    res_id = res_response.json()["id"]

    confirm_response = client.post(
        f"/reservations/{res_id}/confirm",
        headers=valid_headers,
    )
    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "CONFIRMED"

    orders_response = client.get("/orders?page=1&size=10", headers=valid_headers)
    assert orders_response.status_code == 200
    assert orders_response.json()["total"] == 1
    assert orders_response.json()["items"][0]["reservation_id"] == res_id
