import pytest
from fastapi.testclient import TestClient
from src.commerce_service.app import app, _service, _repository
from src.commerce_service.repository import Repository
from src.commerce_service.service import Service


@pytest.fixture(autouse=True)
def reset_db():
    """Reset database before each test."""
    global _repository, _service
    _repository = Repository(":memory:")
    _service = Service(_repository)
    # Update app's references
    import src.commerce_service.app as app_module
    app_module._repository = _repository
    app_module._service = _service
    yield
    # Cleanup after test
    _repository = Repository(":memory:")
    _service = Service(_repository)


@pytest.fixture
def client():
    return TestClient(app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_missing_api_key(client):
    response = client.post("/skus", json={"sku": "SKU001", "initial_stock": 100})
    assert response.status_code == 403


def test_create_sku_invalid_api_key(client):
    headers = {"Authorization": "Bearer invalid-key"}
    response = client.post("/skus", json={"sku": "SKU001", "initial_stock": 100}, headers=headers)
    assert response.status_code == 401


def test_create_sku_success(client):
    headers = {"Authorization": "Bearer test-key-123"}
    response = client.post("/skus", json={"sku": "SKU001", "initial_stock": 100}, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["available_stock"] == 100
    assert "id" in data


def test_adjust_stock_success(client):
    headers = {"Authorization": "Bearer test-key-123"}
    # Create SKU first
    client.post("/skus", json={"sku": "SKU002", "initial_stock": 100}, headers=headers)

    # Adjust stock
    response = client.post("/stock/adjust", json={"sku": "SKU002", "amount": -10}, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "SKU002"
    assert data["available_stock"] == 90


def test_adjust_stock_not_found(client):
    headers = {"Authorization": "Bearer test-key-123"}
    response = client.post("/stock/adjust", json={"sku": "NONEXISTENT", "amount": 10}, headers=headers)
    assert response.status_code == 404


def test_create_reservation_insufficient_stock(client):
    headers = {"Authorization": "Bearer test-key-123"}
    # Create SKU with limited stock
    client.post("/skus", json={"sku": "SKU003", "initial_stock": 5}, headers=headers)

    # Try to reserve more than available
    response = client.post(
        "/reservations",
        json={"sku": "SKU003", "quantity": 10, "idempotency_key": "key-001"},
        headers=headers
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_create_reservation_success(client):
    headers = {"Authorization": "Bearer test-key-123"}
    # Create SKU
    client.post("/skus", json={"sku": "SKU004", "initial_stock": 100}, headers=headers)

    # Create reservation
    response = client.post(
        "/reservations",
        json={"sku": "SKU004", "quantity": 10, "idempotency_key": "key-002"},
        headers=headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU004"
    assert data["quantity"] == 10
    assert data["status"] == "PENDING"
    assert "id" in data
    assert "created_at" in data


def test_idempotent_reservation(client):
    headers = {"Authorization": "Bearer test-key-123"}
    # Create SKU
    client.post("/skus", json={"sku": "SKU005", "initial_stock": 100}, headers=headers)

    # Create first reservation
    response1 = client.post(
        "/reservations",
        json={"sku": "SKU005", "quantity": 10, "idempotency_key": "key-003"},
        headers=headers
    )
    assert response1.status_code == 201
    data1 = response1.json()

    # Try to create with same idempotency key
    response2 = client.post(
        "/reservations",
        json={"sku": "SKU005", "quantity": 10, "idempotency_key": "key-003"},
        headers=headers
    )
    assert response2.status_code == 201
    data2 = response2.json()

    # Should return the same reservation
    assert data1["id"] == data2["id"]
    assert data1["created_at"] == data2["created_at"]

    # Stock should only be deducted once
    response_sku = client.get("/skus", headers=headers)


def test_happy_path_workflow(client):
    headers = {"Authorization": "Bearer test-key-123"}

    # 1. Create SKU
    sku_resp = client.post("/skus", json={"sku": "SKU006", "initial_stock": 100}, headers=headers)
    assert sku_resp.status_code == 201

    # 2. Create reservation
    res_resp = client.post(
        "/reservations",
        json={"sku": "SKU006", "quantity": 10, "idempotency_key": "key-004"},
        headers=headers
    )
    assert res_resp.status_code == 201
    reservation_id = res_resp.json()["id"]

    # 3. Confirm reservation
    confirm_resp = client.post(f"/reservations/{reservation_id}/confirm", headers=headers)
    assert confirm_resp.status_code == 200
    order_data = confirm_resp.json()
    assert order_data["sku"] == "SKU006"
    assert order_data["quantity"] == 10

    # 4. Get orders
    orders_resp = client.get("/orders", headers=headers)
    assert orders_resp.status_code == 200
    orders_data = orders_resp.json()
    assert len(orders_data["items"]) == 1
    assert orders_data["items"][0]["sku"] == "SKU006"


def test_confirm_reservation_not_pending(client):
    headers = {"Authorization": "Bearer test-key-123"}
    # Create SKU and reservation
    client.post("/skus", json={"sku": "SKU007", "initial_stock": 100}, headers=headers)
    res_resp = client.post(
        "/reservations",
        json={"sku": "SKU007", "quantity": 10, "idempotency_key": "key-005"},
        headers=headers
    )
    reservation_id = res_resp.json()["id"]

    # Confirm it
    client.post(f"/reservations/{reservation_id}/confirm", headers=headers)

    # Try to confirm again
    response = client.post(f"/reservations/{reservation_id}/confirm", headers=headers)
    assert response.status_code == 400
    assert "not in PENDING state" in response.json()["detail"]


def test_cancel_reservation(client):
    headers = {"Authorization": "Bearer test-key-123"}
    # Create SKU and reservation
    client.post("/skus", json={"sku": "SKU008", "initial_stock": 100}, headers=headers)
    res_resp = client.post(
        "/reservations",
        json={"sku": "SKU008", "quantity": 10, "idempotency_key": "key-006"},
        headers=headers
    )
    reservation_id = res_resp.json()["id"]

    # Cancel reservation
    response = client.post(f"/reservations/{reservation_id}/cancel", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"

    # Verify stock was restored
    sku_info = _repository.get_sku_by_sku("SKU008")
    assert sku_info["available_stock"] == 100


def test_cancel_non_pending_reservation(client):
    headers = {"Authorization": "Bearer test-key-123"}
    # Create SKU and reservation
    client.post("/skus", json={"sku": "SKU009", "initial_stock": 100}, headers=headers)
    res_resp = client.post(
        "/reservations",
        json={"sku": "SKU009", "quantity": 10, "idempotency_key": "key-007"},
        headers=headers
    )
    reservation_id = res_resp.json()["id"]

    # Confirm it
    client.post(f"/reservations/{reservation_id}/confirm", headers=headers)

    # Try to cancel confirmed reservation
    response = client.post(f"/reservations/{reservation_id}/cancel", headers=headers)
    assert response.status_code == 400
    assert "not in PENDING state" in response.json()["detail"]


def test_pagination(client):
    headers = {"Authorization": "Bearer test-key-123"}
    # Create SKU
    client.post("/skus", json={"sku": "SKU010", "initial_stock": 1000}, headers=headers)

    # Create and confirm 15 reservations to test pagination
    for i in range(15):
        res_resp = client.post(
            "/reservations",
            json={"sku": "SKU010", "quantity": 10, "idempotency_key": f"key-{i}"},
            headers=headers
        )
        reservation_id = res_resp.json()["id"]
        client.post(f"/reservations/{reservation_id}/confirm", headers=headers)

    # Get first page (default size 10)
    response1 = client.get("/orders", headers=headers)
    assert response1.status_code == 200
    data1 = response1.json()
    assert len(data1["items"]) == 10
    assert data1["page"] == 1
    assert data1["size"] == 10
    assert data1["total"] == 15

    # Get second page
    response2 = client.get("/orders?page=2&size=10", headers=headers)
    assert response2.status_code == 200
    data2 = response2.json()
    assert len(data2["items"]) == 5
    assert data2["page"] == 2
