import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.app import app, get_db
from commerce_service.models import Base

DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
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

API_KEY = "demo-key-12345"
HEADERS = {"X-API-Key": API_KEY}


@pytest.fixture(autouse=True)
def cleanup_db():
    """Clean up database before each test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_create_sku():
    response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Product 1"},
        headers=HEADERS,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_code"] == "SKU001"
    assert data["name"] == "Product 1"


def test_create_sku_missing_api_key():
    response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Product 1"},
    )
    assert response.status_code == 403


def test_create_sku_invalid_api_key():
    response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Product 1"},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 403


def test_adjust_stock():
    # Create SKU first
    create_response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Product 1"},
        headers=HEADERS,
    )
    sku_id = create_response.json()["id"]

    # Adjust stock
    response = client.post(
        "/stock",
        json={"sku_id": sku_id, "quantity_delta": 100},
        headers=HEADERS,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_quantity"] == 100
    assert data["reserved_quantity"] == 0


def test_create_reservation_success():
    # Setup
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Product 1"},
        headers=HEADERS,
    )
    sku_id = sku_response.json()["id"]

    client.post(
        "/stock",
        json={"sku_id": sku_id, "quantity_delta": 100},
        headers=HEADERS,
    )

    # Create reservation
    response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 50,
            "idempotency_key": "idem-001",
            "ttl_seconds": 3600,
        },
        headers=HEADERS,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["quantity"] == 50
    assert data["status"] == "pending"


def test_create_reservation_insufficient_stock():
    # Setup
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Product 1"},
        headers=HEADERS,
    )
    sku_id = sku_response.json()["id"]

    client.post(
        "/stock",
        json={"sku_id": sku_id, "quantity_delta": 30},
        headers=HEADERS,
    )

    # Try to reserve more than available
    response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 50,
            "idempotency_key": "idem-001",
            "ttl_seconds": 3600,
        },
        headers=HEADERS,
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_idempotent_reservation():
    # Setup
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Product 1"},
        headers=HEADERS,
    )
    sku_id = sku_response.json()["id"]

    client.post(
        "/stock",
        json={"sku_id": sku_id, "quantity_delta": 100},
        headers=HEADERS,
    )

    # Create first reservation
    response1 = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 50,
            "idempotency_key": "idem-001",
            "ttl_seconds": 3600,
        },
        headers=HEADERS,
    )
    res_id_1 = response1.json()["id"]

    # Create with same idempotency key
    response2 = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 50,
            "idempotency_key": "idem-001",
            "ttl_seconds": 3600,
        },
        headers=HEADERS,
    )
    res_id_2 = response2.json()["id"]

    assert res_id_1 == res_id_2


def test_confirm_reservation():
    # Setup
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Product 1"},
        headers=HEADERS,
    )
    sku_id = sku_response.json()["id"]

    client.post(
        "/stock",
        json={"sku_id": sku_id, "quantity_delta": 100},
        headers=HEADERS,
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 50,
            "idempotency_key": "idem-001",
            "ttl_seconds": 3600,
        },
        headers=HEADERS,
    )
    res_id = res_response.json()["id"]

    # Confirm reservation
    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers=HEADERS,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_id"] == sku_id
    assert data["quantity"] == 50


def test_cancel_reservation():
    # Setup
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Product 1"},
        headers=HEADERS,
    )
    sku_id = sku_response.json()["id"]

    client.post(
        "/stock",
        json={"sku_id": sku_id, "quantity_delta": 100},
        headers=HEADERS,
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 50,
            "idempotency_key": "idem-001",
            "ttl_seconds": 3600,
        },
        headers=HEADERS,
    )
    res_id = res_response.json()["id"]

    # Cancel reservation
    response = client.delete(
        f"/reservations/{res_id}",
        headers=HEADERS,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cancelled"


def test_cancel_reservation_unauthorized():
    # Setup
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Product 1"},
        headers=HEADERS,
    )
    sku_id = sku_response.json()["id"]

    client.post(
        "/stock",
        json={"sku_id": sku_id, "quantity_delta": 100},
        headers=HEADERS,
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 50,
            "idempotency_key": "idem-001",
            "ttl_seconds": 3600,
        },
        headers=HEADERS,
    )
    res_id = res_response.json()["id"]

    # Try to cancel without API key
    response = client.delete(f"/reservations/{res_id}")
    assert response.status_code == 403


def test_list_orders_pagination():
    # Setup
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Product 1"},
        headers=HEADERS,
    )
    sku_id = sku_response.json()["id"]

    client.post(
        "/stock",
        json={"sku_id": sku_id, "quantity_delta": 500},
        headers=HEADERS,
    )

    # Create and confirm multiple reservations
    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={
                "sku_id": sku_id,
                "quantity": 10,
                "idempotency_key": f"idem-{i}",
                "ttl_seconds": 3600,
            },
            headers=HEADERS,
        )
        res_id = res_response.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers=HEADERS,
        )

    # Test first page
    response = client.get("/orders?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 10
    assert data["total"] == 25
    assert data["limit"] == 10
    assert data["offset"] == 0

    # Test second page
    response = client.get("/orders?limit=10&offset=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 10

    # Test third page
    response = client.get("/orders?limit=10&offset=20")
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 5


def test_get_order():
    # Setup
    sku_response = client.post(
        "/skus",
        json={"sku_code": "SKU001", "name": "Product 1"},
        headers=HEADERS,
    )
    sku_id = sku_response.json()["id"]

    client.post(
        "/stock",
        json={"sku_id": sku_id, "quantity_delta": 100},
        headers=HEADERS,
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku_id": sku_id,
            "quantity": 50,
            "idempotency_key": "idem-001",
            "ttl_seconds": 3600,
        },
        headers=HEADERS,
    )
    res_id = res_response.json()["id"]

    order_response = client.post(
        f"/reservations/{res_id}/confirm",
        headers=HEADERS,
    )
    order_id = order_response.json()["id"]

    # Get order
    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == order_id
    assert data["sku_id"] == sku_id
