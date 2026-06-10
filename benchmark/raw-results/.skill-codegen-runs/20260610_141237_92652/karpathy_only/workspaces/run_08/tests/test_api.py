import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.commerce_service.app import app, get_db
from src.commerce_service.models import Base

SQLALCHEMY_DATABASE_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(bind=engine)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

API_TOKEN = "test-token-123"
HEADERS = {"X-API-Token": API_TOKEN}

@pytest.fixture(autouse=True)
def reset_db():
    """Reset database before each test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield

def test_health_check():
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_create_sku():
    """Test SKU creation."""
    response = client.post(
        "/skus",
        json={"sku": "PROD-001", "initial_stock": 100},
        headers=HEADERS
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "PROD-001"
    assert data["available_stock"] == 100

def test_create_sku_missing_token():
    """Test SKU creation without API token."""
    response = client.post(
        "/skus",
        json={"sku": "PROD-001", "initial_stock": 100}
    )
    assert response.status_code == 401

def test_create_sku_invalid_token():
    """Test SKU creation with invalid API token."""
    response = client.post(
        "/skus",
        json={"sku": "PROD-001", "initial_stock": 100},
        headers={"X-API-Token": "invalid-token"}
    )
    assert response.status_code == 401

def test_adjust_stock():
    """Test stock adjustment."""
    client.post(
        "/skus",
        json={"sku": "PROD-001", "initial_stock": 100},
        headers=HEADERS
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "PROD-001", "amount": 50},
        headers=HEADERS
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 150

def test_adjust_stock_negative():
    """Test negative stock adjustment."""
    client.post(
        "/skus",
        json={"sku": "PROD-001", "initial_stock": 100},
        headers=HEADERS
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "PROD-001", "amount": -30},
        headers=HEADERS
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 70

def test_create_reservation_success():
    """Test successful reservation creation."""
    client.post(
        "/skus",
        json={"sku": "PROD-001", "initial_stock": 100},
        headers=HEADERS
    )

    response = client.post(
        "/reservations",
        json={
            "sku": "PROD-001",
            "quantity": 10,
            "idempotency_key": "key-001"
        },
        headers=HEADERS
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "PROD-001"
    assert data["quantity"] == 10
    assert data["status"] == "PENDING"

def test_create_reservation_insufficient_stock():
    """Test reservation with insufficient stock."""
    client.post(
        "/skus",
        json={"sku": "PROD-001", "initial_stock": 100},
        headers=HEADERS
    )

    response = client.post(
        "/reservations",
        json={
            "sku": "PROD-001",
            "quantity": 150,
            "idempotency_key": "key-001"
        },
        headers=HEADERS
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]

def test_create_reservation_idempotency():
    """Test reservation idempotency."""
    client.post(
        "/skus",
        json={"sku": "PROD-001", "initial_stock": 100},
        headers=HEADERS
    )

    response1 = client.post(
        "/reservations",
        json={
            "sku": "PROD-001",
            "quantity": 10,
            "idempotency_key": "key-001"
        },
        headers=HEADERS
    )
    assert response1.status_code == 201
    data1 = response1.json()
    res_id = data1["id"]

    response2 = client.post(
        "/reservations",
        json={
            "sku": "PROD-001",
            "quantity": 10,
            "idempotency_key": "key-001"
        },
        headers=HEADERS
    )
    assert response2.status_code == 201
    data2 = response2.json()
    assert data2["id"] == res_id
    assert data1 == data2

def test_confirm_reservation_success():
    """Test successful reservation confirmation."""
    client.post(
        "/skus",
        json={"sku": "PROD-001", "initial_stock": 100},
        headers=HEADERS
    )

    res = client.post(
        "/reservations",
        json={
            "sku": "PROD-001",
            "quantity": 10,
            "idempotency_key": "key-001"
        },
        headers=HEADERS
    )
    res_id = res.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers=HEADERS
    )
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert data["reservation_id"] == res_id

def test_confirm_reservation_not_pending():
    """Test confirmation of non-PENDING reservation."""
    client.post(
        "/skus",
        json={"sku": "PROD-001", "initial_stock": 100},
        headers=HEADERS
    )

    res = client.post(
        "/reservations",
        json={
            "sku": "PROD-001",
            "quantity": 10,
            "idempotency_key": "key-001"
        },
        headers=HEADERS
    )
    res_id = res.json()["id"]

    client.post(
        f"/reservations/{res_id}/confirm",
        headers=HEADERS
    )

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers=HEADERS
    )
    assert response.status_code == 400
    assert "not PENDING" in response.json()["detail"]

def test_cancel_reservation_success():
    """Test successful reservation cancellation."""
    client.post(
        "/skus",
        json={"sku": "PROD-001", "initial_stock": 100},
        headers=HEADERS
    )

    res = client.post(
        "/reservations",
        json={
            "sku": "PROD-001",
            "quantity": 10,
            "idempotency_key": "key-001"
        },
        headers=HEADERS
    )
    res_id = res.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers=HEADERS
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"
    assert data["restored_quantity"] == 10

def test_cancel_reservation_not_pending():
    """Test cancellation of non-PENDING reservation."""
    client.post(
        "/skus",
        json={"sku": "PROD-001", "initial_stock": 100},
        headers=HEADERS
    )

    res = client.post(
        "/reservations",
        json={
            "sku": "PROD-001",
            "quantity": 10,
            "idempotency_key": "key-001"
        },
        headers=HEADERS
    )
    res_id = res.json()["id"]

    client.post(
        f"/reservations/{res_id}/confirm",
        headers=HEADERS
    )

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers=HEADERS
    )
    assert response.status_code == 400
    assert "not PENDING" in response.json()["detail"]

def test_list_orders():
    """Test orders listing."""
    client.post(
        "/skus",
        json={"sku": "PROD-001", "initial_stock": 100},
        headers=HEADERS
    )

    res = client.post(
        "/reservations",
        json={
            "sku": "PROD-001",
            "quantity": 10,
            "idempotency_key": "key-001"
        },
        headers=HEADERS
    )
    res_id = res.json()["id"]

    client.post(
        f"/reservations/{res_id}/confirm",
        headers=HEADERS
    )

    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] == 1
    assert len(data["items"]) == 1

def test_list_orders_pagination():
    """Test orders pagination."""
    client.post(
        "/skus",
        json={"sku": "PROD-001", "initial_stock": 100},
        headers=HEADERS
    )

    for i in range(15):
        res = client.post(
            "/reservations",
            json={
                "sku": "PROD-001",
                "quantity": 1,
                "idempotency_key": f"key-{i}"
            },
            headers=HEADERS
        )
        res_id = res.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers=HEADERS
        )

    response = client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] == 15
    assert len(data["items"]) == 10

    response = client.get("/orders?page=2&size=10")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 2
    assert len(data["items"]) == 5

def test_happy_path_workflow():
    """Test complete happy path: SKU -> Reserve -> Confirm -> Order lookup."""
    client.post(
        "/skus",
        json={"sku": "WIDGET-001", "initial_stock": 50},
        headers=HEADERS
    )

    res = client.post(
        "/reservations",
        json={
            "sku": "WIDGET-001",
            "quantity": 5,
            "idempotency_key": "wid-key-001"
        },
        headers=HEADERS
    )
    assert res.status_code == 201
    res_id = res.json()["id"]

    confirm = client.post(
        f"/reservations/{res_id}/confirm",
        headers=HEADERS
    )
    assert confirm.status_code == 200
    order_id = confirm.json()["id"]

    orders = client.get("/orders")
    assert orders.status_code == 200
    data = orders.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == order_id
    assert data["items"][0]["reservation_id"] == res_id

def test_stock_restoration_on_cancel():
    """Test that stock is restored when reservation is cancelled."""
    client.post(
        "/skus",
        json={"sku": "PROD-001", "initial_stock": 100},
        headers=HEADERS
    )

    res = client.post(
        "/reservations",
        json={
            "sku": "PROD-001",
            "quantity": 30,
            "idempotency_key": "key-001"
        },
        headers=HEADERS
    )
    res_id = res.json()["id"]

    client.post(
        f"/reservations/{res_id}/cancel",
        headers=HEADERS
    )

    client.post(
        "/stock/adjust",
        json={"sku": "PROD-001", "amount": 0},
        headers=HEADERS
    )

    response = client.post(
        "/reservations",
        json={
            "sku": "PROD-001",
            "quantity": 100,
            "idempotency_key": "key-002"
        },
        headers=HEADERS
    )
    assert response.status_code == 201
