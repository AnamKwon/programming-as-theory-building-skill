import pytest
import tempfile
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from commerce_service.app import app, db, service


@pytest.fixture(scope="function", autouse=True)
def setup_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    from commerce_service.repository import Database
    from commerce_service.service import ServiceLayer
    from commerce_service import app as app_module

    test_db = Database(db_path=db_path)
    app_module.db = test_db
    app_module.service = ServiceLayer(test_db)
    yield
    import os
    os.unlink(db_path)


@pytest.fixture
def client():
    return TestClient(app)


HEADERS = {"X-API-Key": "test-key-123"}


def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_create_sku(client):
    resp = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "stock_qty": 100},
        headers=HEADERS,
    )
    assert resp.status_code == 201
    assert resp.json()["sku_code"] == "SKU-001"
    assert resp.json()["stock_qty"] == 100


def test_create_sku_no_auth(client):
    resp = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "stock_qty": 100},
    )
    assert resp.status_code == 403


def test_create_sku_invalid_auth(client):
    resp = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "stock_qty": 100},
        headers={"X-API-Key": "invalid-key"},
    )
    assert resp.status_code == 403


def test_create_duplicate_sku(client):
    client.post(
        "/skus",
        json={"sku_code": "SKU-001", "stock_qty": 100},
        headers=HEADERS,
    )
    resp = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "stock_qty": 50},
        headers=HEADERS,
    )
    assert resp.status_code == 409


def test_adjust_stock(client):
    create_resp = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "stock_qty": 100},
        headers=HEADERS,
    )
    sku_id = create_resp.json()["id"]

    resp = client.post(
        f"/skus/{sku_id}/stock",
        json={"adjustment": 50},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["stock_qty"] == 150


def test_adjust_stock_negative(client):
    create_resp = client.post(
        "/skus",
        json={"sku_code": "SKU-001", "stock_qty": 100},
        headers=HEADERS,
    )
    sku_id = create_resp.json()["id"]

    resp = client.post(
        f"/skus/{sku_id}/stock",
        json={"adjustment": -150},
        headers=HEADERS,
    )
    assert resp.status_code == 400


def test_create_reservation(client):
    client.post(
        "/skus",
        json={"sku_code": "SKU-001", "stock_qty": 100},
        headers=HEADERS,
    )
    resp = client.post(
        "/reservations",
        json={"sku_code": "SKU-001", "qty": 25, "idempotency_key": "key-1"},
        headers=HEADERS,
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "pending"
    assert resp.json()["qty"] == 25


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku_code": "SKU-001", "stock_qty": 50},
        headers=HEADERS,
    )
    resp = client.post(
        "/reservations",
        json={"sku_code": "SKU-001", "qty": 100, "idempotency_key": "key-1"},
        headers=HEADERS,
    )
    assert resp.status_code == 400
    assert "Insufficient stock" in resp.json()["detail"]


def test_create_reservation_idempotency(client):
    client.post(
        "/skus",
        json={"sku_code": "SKU-001", "stock_qty": 100},
        headers=HEADERS,
    )
    resp1 = client.post(
        "/reservations",
        json={"sku_code": "SKU-001", "qty": 25, "idempotency_key": "key-1"},
        headers=HEADERS,
    )
    res_id = resp1.json()["id"]

    resp2 = client.post(
        "/reservations",
        json={"sku_code": "SKU-001", "qty": 30, "idempotency_key": "key-1"},
        headers=HEADERS,
    )
    assert resp2.json()["id"] == res_id
    assert resp2.json()["qty"] == 25


def test_confirm_reservation(client):
    client.post(
        "/skus",
        json={"sku_code": "SKU-001", "stock_qty": 100},
        headers=HEADERS,
    )
    res_resp = client.post(
        "/reservations",
        json={"sku_code": "SKU-001", "qty": 25, "idempotency_key": "key-1"},
        headers=HEADERS,
    )
    res_id = res_resp.json()["id"]

    resp = client.post(
        f"/reservations/{res_id}/confirm",
        json={"idempotency_key": "key-1"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "created"


def test_confirm_reservation_invalid_key(client):
    client.post(
        "/skus",
        json={"sku_code": "SKU-001", "stock_qty": 100},
        headers=HEADERS,
    )
    res_resp = client.post(
        "/reservations",
        json={"sku_code": "SKU-001", "qty": 25, "idempotency_key": "key-1"},
        headers=HEADERS,
    )
    res_id = res_resp.json()["id"]

    resp = client.post(
        f"/reservations/{res_id}/confirm",
        json={"idempotency_key": "wrong-key"},
        headers=HEADERS,
    )
    assert resp.status_code == 400


def test_confirm_expired_reservation(client):
    from commerce_service.repository import Database

    client.post(
        "/skus",
        json={"sku_code": "SKU-001", "stock_qty": 100},
        headers=HEADERS,
    )
    res_resp = client.post(
        "/reservations",
        json={"sku_code": "SKU-001", "qty": 25, "idempotency_key": "key-1"},
        headers=HEADERS,
    )
    res_id = res_resp.json()["id"]

    with service.db.get_connection() as conn:
        past = (datetime.utcnow() - timedelta(minutes=20)).isoformat()
        conn.execute(
            "UPDATE reservations SET expires_at = ? WHERE id = ?",
            (past, res_id),
        )
        conn.commit()

    resp = client.post(
        f"/reservations/{res_id}/confirm",
        json={"idempotency_key": "key-1"},
        headers=HEADERS,
    )
    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"]


def test_cancel_reservation(client):
    client.post(
        "/skus",
        json={"sku_code": "SKU-001", "stock_qty": 100},
        headers=HEADERS,
    )
    res_resp = client.post(
        "/reservations",
        json={"sku_code": "SKU-001", "qty": 25, "idempotency_key": "key-1"},
        headers=HEADERS,
    )
    res_id = res_resp.json()["id"]

    resp = client.post(
        f"/reservations/{res_id}/cancel",
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_get_order(client):
    client.post(
        "/skus",
        json={"sku_code": "SKU-001", "stock_qty": 100},
        headers=HEADERS,
    )
    res_resp = client.post(
        "/reservations",
        json={"sku_code": "SKU-001", "qty": 25, "idempotency_key": "key-1"},
        headers=HEADERS,
    )
    res_id = res_resp.json()["id"]

    order_resp = client.post(
        f"/reservations/{res_id}/confirm",
        json={"idempotency_key": "key-1"},
        headers=HEADERS,
    )
    order_id = order_resp.json()["id"]

    resp = client.get(f"/orders/{order_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == order_id
    assert resp.json()["status"] == "created"


def test_get_nonexistent_order(client):
    resp = client.get("/orders/999")
    assert resp.status_code == 404


def test_list_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku_code": "SKU-001", "stock_qty": 1000},
        headers=HEADERS,
    )
    for i in range(5):
        res_resp = client.post(
            "/reservations",
            json={
                "sku_code": "SKU-001",
                "qty": 10,
                "idempotency_key": f"key-{i}",
            },
            headers=HEADERS,
        )
        res_id = res_resp.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            json={"idempotency_key": f"key-{i}"},
            headers=HEADERS,
        )

    resp = client.get("/orders?limit=2&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["orders"]) == 2
    assert data["total"] == 5
    assert data["limit"] == 2
    assert data["offset"] == 0

    resp2 = client.get("/orders?limit=2&offset=2")
    data2 = resp2.json()
    assert len(data2["orders"]) == 2
    assert data["orders"][0]["id"] != data2["orders"][0]["id"]
