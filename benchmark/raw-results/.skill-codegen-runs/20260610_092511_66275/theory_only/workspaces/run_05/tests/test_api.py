import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from commerce_service.models import Base
from commerce_service.app import app, get_db


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionLocal()
    yield session
    try:
        session.close()
    except Exception:
        pass


@pytest.fixture
def client(db_session):
    """Create a TestClient with the test database."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_create_sku_unauthorized(client):
    """Test SKU creation without API key."""
    response = client.post(
        "/skus", json={"id": "sku-001", "name": "Widget", "description": "A widget"}
    )
    assert response.status_code == 422  # Missing header


def test_create_sku_invalid_key(client):
    """Test SKU creation with invalid API key."""
    response = client.post(
        "/skus",
        json={"id": "sku-001", "name": "Widget", "description": "A widget"},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 401


def test_create_sku_success(client):
    """Test successful SKU creation."""
    response = client.post(
        "/skus",
        json={"id": "sku-001", "name": "Widget", "description": "A great widget"},
        headers={"X-API-Key": "sk-demo-key"},
    )
    assert response.status_code == 201
    assert response.json()["id"] == "sku-001"
    assert response.json()["name"] == "Widget"


def test_adjust_stock_success(client):
    """Test stock adjustment."""
    client.post(
        "/skus",
        json={"id": "sku-002", "name": "Gadget", "description": None},
        headers={"X-API-Key": "sk-demo-key"},
    )
    response = client.post(
        "/skus/sku-002/stock",
        json={"quantity": 100},
        headers={"X-API-Key": "sk-demo-key"},
    )
    assert response.status_code == 200
    assert response.json()["available"] == 100


def test_adjust_stock_sku_not_found(client):
    """Test stock adjustment for non-existent SKU."""
    response = client.post(
        "/skus/nonexistent/stock",
        json={"quantity": 100},
        headers={"X-API-Key": "sk-demo-key"},
    )
    assert response.status_code == 404


def test_reserve_inventory_success(client):
    """Test successful reservation."""
    client.post(
        "/skus",
        json={"id": "sku-003", "name": "Thing", "description": None},
        headers={"X-API-Key": "sk-demo-key"},
    )
    client.post(
        "/skus/sku-003/stock",
        json={"quantity": 50},
        headers={"X-API-Key": "sk-demo-key"},
    )
    response = client.post(
        "/reservations",
        json={"sku_id": "sku-003", "quantity": 10, "idempotency_key": "key-1"},
        headers={"X-API-Key": "sk-demo-key"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "active"
    assert response.json()["quantity"] == 10


def test_reserve_inventory_insufficient_stock(client):
    """Test reservation with insufficient stock."""
    client.post(
        "/skus",
        json={"id": "sku-004", "name": "Item", "description": None},
        headers={"X-API-Key": "sk-demo-key"},
    )
    client.post(
        "/skus/sku-004/stock",
        json={"quantity": 5},
        headers={"X-API-Key": "sk-demo-key"},
    )
    response = client.post(
        "/reservations",
        json={"sku_id": "sku-004", "quantity": 10, "idempotency_key": "key-2"},
        headers={"X-API-Key": "sk-demo-key"},
    )
    assert response.status_code == 409


def test_reserve_inventory_idempotent_retry(client):
    """Test idempotent reservation retry."""
    client.post(
        "/skus",
        json={"id": "sku-005", "name": "Product", "description": None},
        headers={"X-API-Key": "sk-demo-key"},
    )
    client.post(
        "/skus/sku-005/stock",
        json={"quantity": 50},
        headers={"X-API-Key": "sk-demo-key"},
    )
    response1 = client.post(
        "/reservations",
        json={"sku_id": "sku-005", "quantity": 10, "idempotency_key": "key-3"},
        headers={"X-API-Key": "sk-demo-key"},
    )
    response2 = client.post(
        "/reservations",
        json={"sku_id": "sku-005", "quantity": 10, "idempotency_key": "key-3"},
        headers={"X-API-Key": "sk-demo-key"},
    )
    assert response1.json()["id"] == response2.json()["id"]


def test_confirm_reservation_success(client):
    """Test reservation confirmation."""
    client.post(
        "/skus",
        json={"id": "sku-006", "name": "Component", "description": None},
        headers={"X-API-Key": "sk-demo-key"},
    )
    client.post(
        "/skus/sku-006/stock",
        json={"quantity": 50},
        headers={"X-API-Key": "sk-demo-key"},
    )
    res_response = client.post(
        "/reservations",
        json={"sku_id": "sku-006", "quantity": 10, "idempotency_key": "key-4"},
        headers={"X-API-Key": "sk-demo-key"},
    )
    res_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": "sk-demo-key"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert response.json()["sku_id"] == "sku-006"


def test_confirm_reservation_not_found(client):
    """Test confirmation of non-existent reservation."""
    response = client.post(
        "/reservations/nonexistent/confirm",
        headers={"X-API-Key": "sk-demo-key"},
    )
    assert response.status_code == 404


def test_cancel_reservation_success(client):
    """Test reservation cancellation."""
    client.post(
        "/skus",
        json={"id": "sku-007", "name": "Widget", "description": None},
        headers={"X-API-Key": "sk-demo-key"},
    )
    client.post(
        "/skus/sku-007/stock",
        json={"quantity": 50},
        headers={"X-API-Key": "sk-demo-key"},
    )
    res_response = client.post(
        "/reservations",
        json={"sku_id": "sku-007", "quantity": 10, "idempotency_key": "key-5"},
        headers={"X-API-Key": "sk-demo-key"},
    )
    res_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"X-API-Key": "sk-demo-key"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_get_order_success(client):
    """Test order retrieval."""
    client.post(
        "/skus",
        json={"id": "sku-008", "name": "Item", "description": None},
        headers={"X-API-Key": "sk-demo-key"},
    )
    client.post(
        "/skus/sku-008/stock",
        json={"quantity": 50},
        headers={"X-API-Key": "sk-demo-key"},
    )
    res_response = client.post(
        "/reservations",
        json={"sku_id": "sku-008", "quantity": 10, "idempotency_key": "key-6"},
        headers={"X-API-Key": "sk-demo-key"},
    )
    res_id = res_response.json()["id"]

    order_response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": "sk-demo-key"},
    )
    order_id = order_response.json()["id"]

    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    assert response.json()["id"] == order_id
    assert response.json()["sku_id"] == "sku-008"


def test_get_order_not_found(client):
    """Test retrieval of non-existent order."""
    response = client.get("/orders/nonexistent")
    assert response.status_code == 404


def test_list_orders_pagination(client):
    """Test order pagination."""
    client.post(
        "/skus",
        json={"id": "sku-009", "name": "Product", "description": None},
        headers={"X-API-Key": "sk-demo-key"},
    )
    client.post(
        "/skus/sku-009/stock",
        json={"quantity": 100},
        headers={"X-API-Key": "sk-demo-key"},
    )

    # Create multiple orders
    for i in range(5):
        res_response = client.post(
            "/reservations",
            json={"sku_id": "sku-009", "quantity": 10, "idempotency_key": f"key-{i}"},
            headers={"X-API-Key": "sk-demo-key"},
        )
        res_id = res_response.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": "sk-demo-key"},
        )

    # Get first page
    response1 = client.get("/orders?limit=2")
    assert response1.status_code == 200
    assert len(response1.json()["orders"]) == 2
    assert response1.json()["next_cursor"] is not None

    # Get next page
    next_cursor = response1.json()["next_cursor"]
    response2 = client.get(f"/orders?limit=10&cursor={next_cursor}")
    assert response2.status_code == 200
    assert len(response2.json()["orders"]) > 0
    # Total should be <= 5
    total = len(response1.json()["orders"]) + len(response2.json()["orders"])
    assert total <= 5


def test_authorize_on_mutating_endpoints(client):
    """Test that mutating endpoints require authorization."""
    endpoints = [
        ("POST", "/skus"),
        ("POST", "/skus/sku-001/stock"),
        ("POST", "/reservations"),
    ]

    for method, path in endpoints:
        if method == "POST":
            response = client.post(path, json={})
            assert response.status_code in [401, 422]  # 401 for missing key or 422 for validation
