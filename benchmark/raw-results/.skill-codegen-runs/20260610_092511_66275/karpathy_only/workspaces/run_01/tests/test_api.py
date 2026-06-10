import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.app import app, get_db
from commerce_service.models import Base

engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(bind=engine)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


API_KEY = "test-key-123"


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_create_sku_without_api_key():
    response = client.post(
        "/skus",
        json={"name": "Widget", "price": 29.99},
    )
    assert response.status_code == 401


def test_create_sku_with_api_key():
    response = client.post(
        "/skus",
        json={"name": "Widget", "price": 29.99},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Widget"
    assert data["price"] == 29.99


def test_adjust_stock():
    # Create SKU first
    sku_response = client.post(
        "/skus",
        json={"name": "Widget", "price": 29.99},
        headers={"X-API-Key": API_KEY},
    )
    sku_id = sku_response.json()["id"]

    # Adjust stock
    response = client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity_change": 100},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["quantity_available"] == 100


def test_adjust_stock_nonexistent_sku():
    response = client.post(
        "/stock/adjust",
        json={"sku_id": "sku_nonexistent", "quantity_change": 100},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 400


def test_create_reservation():
    # Create SKU and add stock
    sku_response = client.post(
        "/skus",
        json={"name": "Widget", "price": 29.99},
        headers={"X-API-Key": API_KEY},
    )
    sku_id = sku_response.json()["id"]

    client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity_change": 100},
        headers={"X-API-Key": API_KEY},
    )

    # Create reservation
    response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "idem_001"},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"
    assert data["quantity"] == 10


def test_create_reservation_insufficient_stock():
    # Create SKU with limited stock
    sku_response = client.post(
        "/skus",
        json={"name": "Widget", "price": 29.99},
        headers={"X-API-Key": API_KEY},
    )
    sku_id = sku_response.json()["id"]

    client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity_change": 10},
        headers={"X-API-Key": API_KEY},
    )

    # Try to reserve more than available
    response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 20, "idempotency_key": "idem_001"},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_reservation_idempotency():
    # Create SKU and add stock
    sku_response = client.post(
        "/skus",
        json={"name": "Widget", "price": 29.99},
        headers={"X-API-Key": API_KEY},
    )
    sku_id = sku_response.json()["id"]

    client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity_change": 100},
        headers={"X-API-Key": API_KEY},
    )

    # Create reservation
    response1 = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "idem_001"},
        headers={"X-API-Key": API_KEY},
    )
    reservation_id = response1.json()["id"]

    # Retry with same idempotency key
    response2 = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "idem_001"},
        headers={"X-API-Key": API_KEY},
    )
    assert response2.status_code == 200
    assert response2.json()["id"] == reservation_id


def test_confirm_reservation():
    # Create SKU and reservation
    sku_response = client.post(
        "/skus",
        json={"name": "Widget", "price": 29.99},
        headers={"X-API-Key": API_KEY},
    )
    sku_id = sku_response.json()["id"]

    client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity_change": 100},
        headers={"X-API-Key": API_KEY},
    )

    res_response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "idem_001"},
        headers={"X-API-Key": API_KEY},
    )
    reservation_id = res_response.json()["id"]

    # Confirm
    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


def test_cancel_reservation():
    # Create SKU and reservation
    sku_response = client.post(
        "/skus",
        json={"name": "Widget", "price": 29.99},
        headers={"X-API-Key": API_KEY},
    )
    sku_id = sku_response.json()["id"]

    client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity_change": 100},
        headers={"X-API-Key": API_KEY},
    )

    res_response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "idem_001"},
        headers={"X-API-Key": API_KEY},
    )
    reservation_id = res_response.json()["id"]

    # Cancel
    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_list_orders_pagination():
    # Create multiple orders
    for _ in range(15):
        client.post("/orders", headers={"X-API-Key": API_KEY})

    # List first page
    response = client.get("/orders?skip=0&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["total"] == 15
    assert data["skip"] == 0
    assert data["limit"] == 10

    # List second page
    response = client.get("/orders?skip=10&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 5


def test_list_orders_invalid_pagination():
    response = client.get("/orders?skip=-1&limit=10")
    assert response.status_code == 400

    response = client.get("/orders?skip=0&limit=0")
    assert response.status_code == 400

    response = client.get("/orders?skip=0&limit=101")
    assert response.status_code == 400


def test_get_order():
    # Create order
    order_response = client.post("/orders", headers={"X-API-Key": API_KEY})
    order_id = order_response.json()["id"]

    # Get order
    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == order_id
    assert data["status"] == "pending"


def test_get_nonexistent_order():
    response = client.get("/orders/ord_nonexistent")
    assert response.status_code == 404


def test_unauthorized_mutation():
    # Try to create SKU without API key
    response = client.post(
        "/skus",
        json={"name": "Widget", "price": 29.99},
    )
    assert response.status_code == 401

    # Try with invalid API key
    response = client.post(
        "/skus",
        json={"name": "Widget", "price": 29.99},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 401
