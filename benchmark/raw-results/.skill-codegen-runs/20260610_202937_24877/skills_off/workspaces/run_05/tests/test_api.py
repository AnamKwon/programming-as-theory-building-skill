import pytest
from fastapi.testclient import TestClient
from src.commerce_service.app import app

client = TestClient(app)
VALID_API_KEY = "test-api-key-secret"


@pytest.fixture
def auth_headers():
    return {"X-API-Key": VALID_API_KEY}


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(auth_headers):
    response = client.post(
        "/skus",
        json={"sku": "TEST-SKU-001", "initial_stock": 100},
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "TEST-SKU-001"
    assert data["available_stock"] == 100
    assert data["reserved_stock"] == 0


def test_create_sku_missing_auth():
    response = client.post(
        "/skus",
        json={"sku": "TEST-SKU-002", "initial_stock": 50},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Missing API key"


def test_create_sku_invalid_auth():
    response = client.post(
        "/skus",
        json={"sku": "TEST-SKU-003", "initial_stock": 75},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API key"


def test_adjust_stock_success(auth_headers):
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-004", "initial_stock": 100},
        headers=auth_headers,
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "TEST-SKU-004", "amount": 25},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 125


def test_adjust_stock_decrease(auth_headers):
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-005", "initial_stock": 100},
        headers=auth_headers,
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "TEST-SKU-005", "amount": -30},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 70


def test_adjust_stock_missing_sku(auth_headers):
    response = client.post(
        "/stock/adjust",
        json={"sku": "NONEXISTENT-SKU", "amount": 10},
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_create_reservation_success(auth_headers):
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-006", "initial_stock": 100},
        headers=auth_headers,
    )

    response = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU-006",
            "quantity": 20,
            "idempotency_key": "test-idempotency-1",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "TEST-SKU-006"
    assert data["quantity"] == 20
    assert data["status"] == "PENDING"
    assert data["idempotency_key"] == "test-idempotency-1"
    assert "id" in data
    assert "created_at" in data


def test_create_reservation_insufficient_stock(auth_headers):
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-007", "initial_stock": 10},
        headers=auth_headers,
    )

    response = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU-007",
            "quantity": 50,
            "idempotency_key": "test-idempotency-2",
        },
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_create_reservation_idempotent(auth_headers):
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-008", "initial_stock": 200},
        headers=auth_headers,
    )

    first_response = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU-008",
            "quantity": 30,
            "idempotency_key": "test-idempotency-3",
        },
        headers=auth_headers,
    )
    first_id = first_response.json()["id"]

    second_response = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU-008",
            "quantity": 30,
            "idempotency_key": "test-idempotency-3",
        },
        headers=auth_headers,
    )
    second_id = second_response.json()["id"]

    assert first_id == second_id
    assert first_response.json() == second_response.json()


def test_confirm_reservation_success(auth_headers):
    create_sku_response = client.post(
        "/skus",
        json={"sku": "TEST-SKU-009", "initial_stock": 100},
        headers=auth_headers,
    )

    create_res_response = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU-009",
            "quantity": 15,
            "idempotency_key": "test-idempotency-4",
        },
        headers=auth_headers,
    )
    reservation_id = create_res_response.json()["id"]

    confirm_response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=auth_headers,
    )
    assert confirm_response.status_code == 200
    data = confirm_response.json()
    assert data["status"] == "CONFIRMED"
    assert data["sku"] == "TEST-SKU-009"
    assert data["quantity"] == 15
    assert "id" in data
    assert "created_at" in data


def test_cancel_reservation_success(auth_headers):
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-010", "initial_stock": 100},
        headers=auth_headers,
    )

    create_res_response = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU-010",
            "quantity": 25,
            "idempotency_key": "test-idempotency-5",
        },
        headers=auth_headers,
    )
    reservation_id = create_res_response.json()["id"]

    cancel_response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=auth_headers,
    )
    assert cancel_response.status_code == 200
    data = cancel_response.json()
    assert data["status"] == "CANCELLED"


def test_cancel_reservation_restores_stock(auth_headers):
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-011", "initial_stock": 100},
        headers=auth_headers,
    )

    create_res_response = client.post(
        "/reservations",
        json={
            "sku": "TEST-SKU-011",
            "quantity": 40,
            "idempotency_key": "test-idempotency-6",
        },
        headers=auth_headers,
    )
    reservation_id = create_res_response.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=auth_headers,
    )

    sku_response = client.post(
        "/stock/adjust",
        json={"sku": "TEST-SKU-011", "amount": 0},
        headers=auth_headers,
    )
    assert sku_response.json()["available_stock"] == 100


def test_get_orders_empty():
    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] == 0


def test_get_orders_pagination(auth_headers):
    client.post(
        "/skus",
        json={"sku": "TEST-SKU-012", "initial_stock": 1000},
        headers=auth_headers,
    )

    for i in range(25):
        create_res_response = client.post(
            "/reservations",
            json={
                "sku": "TEST-SKU-012",
                "quantity": 5,
                "idempotency_key": f"test-idempotency-pagination-{i}",
            },
            headers=auth_headers,
        )
        reservation_id = create_res_response.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=auth_headers,
        )

    page1_response = client.get("/orders?page=1&size=10")
    assert page1_response.status_code == 200
    page1_data = page1_response.json()
    assert len(page1_data["items"]) == 10
    assert page1_data["total"] == 25
    assert page1_data["page"] == 1
    assert page1_data["size"] == 10

    page2_response = client.get("/orders?page=2&size=10")
    page2_data = page2_response.json()
    assert len(page2_data["items"]) == 10
    assert page2_data["page"] == 2

    page3_response = client.get("/orders?page=3&size=10")
    page3_data = page3_response.json()
    assert len(page3_data["items"]) == 5
    assert page3_data["page"] == 3


def test_mutation_endpoints_require_auth():
    endpoints = [
        ("POST", "/skus", {"sku": "TEST", "initial_stock": 100}),
        ("POST", "/stock/adjust", {"sku": "TEST", "amount": 10}),
        ("POST", "/reservations", {"sku": "TEST", "quantity": 5, "idempotency_key": "test"}),
    ]

    for method, path, json_data in endpoints:
        if method == "POST":
            response = client.post(path, json=json_data)
        assert response.status_code == 401
