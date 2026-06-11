import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
from commerce_service.app import app
from commerce_service.repository import Repository

client = TestClient(app)

VALID_API_KEY = "test-key-123"


@pytest.fixture(autouse=True)
def reset_db():
    # Reset app database before each test
    app.dependency_overrides.clear()
    from commerce_service import app as app_module
    app_module.repo = Repository()
    app_module.service = app_module.CommerceService(app_module.repo)
    yield


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_missing_api_key():
    response = client.post("/skus", json={"sku": "SKU001", "initial_stock": 100})
    assert response.status_code == 401


def test_create_sku_success():
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["available_stock"] == 100


def test_adjust_stock_success():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": -50},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available_stock"] == 50


def test_create_reservation_insufficient_stock():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 50},
        headers={"X-API-Key": VALID_API_KEY}
    )
    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 100, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_create_reservation_success():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "PENDING"
    assert data["quantity"] == 50


def test_idempotent_reservation():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    res1 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY}
    )
    res2 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY}
    )

    assert res1.json()["id"] == res2.json()["id"]
    assert res1.json()["created_at"] == res2.json()["created_at"]


def test_confirm_reservation_success():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY}
    ).json()

    response = client.post(
        f"/reservations/{res['id']}/confirm",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["quantity"] == 50


def test_confirm_expired_reservation(repo=None):
    if repo is None:
        from commerce_service.app import repo as app_repo
        repo = app_repo

    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY}
    ).json()

    # Manually set created_at to past
    conn = repo._get_connection()
    cursor = conn.cursor()
    old_time = (datetime.utcnow() - timedelta(seconds=310)).isoformat()
    cursor.execute("UPDATE reservations SET created_at = ? WHERE id = ?", (old_time, res["id"]))
    conn.commit()
    conn.close()

    response = client.post(
        f"/reservations/{res['id']}/confirm",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 400
    assert "expired" in response.json()["detail"].lower()


def test_cancel_reservation():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY}
    ).json()

    response = client.post(
        f"/reservations/{res['id']}/cancel",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


def test_list_orders_pagination():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 1000},
        headers={"X-API-Key": VALID_API_KEY}
    )

    # Create 15 orders
    for i in range(15):
        res = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 10, "idempotency_key": f"key-{i}"},
            headers={"X-API-Key": VALID_API_KEY}
        ).json()

        client.post(
            f"/reservations/{res['id']}/confirm",
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
    assert data["page"] == 2


def test_confirm_non_pending_reservation():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY}
    ).json()

    client.post(
        f"/reservations/{res['id']}/confirm",
        headers={"X-API-Key": VALID_API_KEY}
    )

    response = client.post(
        f"/reservations/{res['id']}/confirm",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 400


def test_cancel_non_pending_reservation():
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY}
    )
    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY}
    ).json()

    client.post(
        f"/reservations/{res['id']}/confirm",
        headers={"X-API-Key": VALID_API_KEY}
    )

    response = client.post(
        f"/reservations/{res['id']}/cancel",
        headers={"X-API-Key": VALID_API_KEY}
    )
    assert response.status_code == 400
