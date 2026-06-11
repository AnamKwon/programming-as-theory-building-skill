import pytest
from fastapi.testclient import TestClient
from commerce_service.app import app, repository, service


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_db():
    from commerce_service.repository import Repository, Base
    repository.engine.execute("DROP TABLE IF EXISTS orders")
    repository.engine.execute("DROP TABLE IF EXISTS reservations")
    repository.engine.execute("DROP TABLE IF EXISTS skus")
    Base.metadata.create_all(repository.engine)
    yield


VALID_API_KEY = "test-api-key-123"


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["initial_stock"] == 100


def test_create_sku_missing_api_key(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100}
    )
    assert response.status_code == 401


def test_create_sku_invalid_api_key(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": "invalid-key"}
    )
    assert response.status_code == 401


def test_adjust_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU-001", "amount": -20},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 80


def test_create_reservation_happy_path(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "idem-1"
        },
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["quantity"] == 50
    assert data["status"] == "PENDING"


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 30},
        headers={"X-API-Key": VALID_API_KEY}
    )

    response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "idem-1"
        },
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_idempotency(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    response1 = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "idem-1"
        },
        headers={"X-API-Key": VALID_API_KEY}
    )
    data1 = response1.json()

    response2 = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 60,
            "idempotency_key": "idem-1"
        },
        headers={"X-API-Key": VALID_API_KEY}
    )
    data2 = response2.json()

    assert data1["id"] == data2["id"]
    assert data1["quantity"] == data2["quantity"] == 50


def test_confirm_reservation(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "idem-1"
        },
        headers={"X-API-Key": VALID_API_KEY}
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "SKU-001"
    assert data["quantity"] == 50


def test_cancel_reservation(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "idem-1"
        },
        headers={"X-API-Key": VALID_API_KEY}
    )
    reservation_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"


def test_get_orders(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    for i in range(15):
        res_response = client.post(
            "/reservations",
            json={
                "sku": "SKU-001",
                "quantity": 1,
                "idempotency_key": f"idem-{i}"
            },
            headers={"X-API-Key": VALID_API_KEY}
        )
        reservation_id = res_response.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": VALID_API_KEY}
        )

    response = client.get("/orders?page=1&size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["total"] == 15
    assert data["page"] == 1
    assert data["size"] == 10

    response = client.get("/orders?page=2&size=10")
    data = response.json()
    assert len(data["items"]) == 5


def test_unauthorized_mutations(client):
    endpoints = [
        ("POST", "/skus", {"sku": "SKU-001", "initial_stock": 100}),
        ("POST", "/stock/adjust", {"sku": "SKU-001", "amount": 10}),
        ("POST", "/reservations", {"sku": "SKU-001", "quantity": 50, "idempotency_key": "idem-1"}),
        ("POST", "/reservations/1/confirm", None),
        ("POST", "/reservations/1/cancel", None),
    ]

    for method, path, body in endpoints:
        if method == "POST" and body:
            response = client.post(path, json=body)
        else:
            response = client.post(path)
        assert response.status_code == 401, f"Failed for {method} {path}"
        assert "Missing API Key" in response.json()["detail"]


def test_confirm_non_pending_reservation(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "idem-1"
        },
        headers={"X-API-Key": VALID_API_KEY}
    )
    reservation_id = res_response.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY}
    )

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 400
    assert "Cannot confirm" in response.json()["detail"]


def test_cancel_non_pending_reservation(client):
    client.post(
        "/skus",
        json={"sku": "SKU-001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )

    res_response = client.post(
        "/reservations",
        json={
            "sku": "SKU-001",
            "quantity": 50,
            "idempotency_key": "idem-1"
        },
        headers={"X-API-Key": VALID_API_KEY}
    )
    reservation_id = res_response.json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY}
    )

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 400
    assert "Cannot cancel" in response.json()["detail"]
