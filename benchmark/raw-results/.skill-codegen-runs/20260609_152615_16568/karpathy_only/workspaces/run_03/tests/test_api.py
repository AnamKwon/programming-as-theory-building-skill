import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.app import app, get_db
from commerce_service.models import Base


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_create_sku_without_api_key(client):
    response = client.post("/skus", json={"code": "TEST001", "name": "Test", "initial_stock": 100})
    assert response.status_code == 403


def test_create_sku_with_valid_api_key(client):
    response = client.post(
        "/skus",
        json={"code": "TEST001", "name": "Test Product", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["code"] == "TEST001"
    assert data["name"] == "Test Product"
    assert data["available_stock"] == 100


def test_get_sku(client):
    create_resp = client.post(
        "/skus",
        json={"code": "TEST002", "name": "Test", "initial_stock": 50},
        headers={"X-API-Key": "test-api-key"},
    )
    sku_id = create_resp.json()["id"]

    get_resp = client.get(f"/skus/{sku_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["code"] == "TEST002"


def test_get_sku_not_found(client):
    response = client.get("/skus/9999")
    assert response.status_code == 404


def test_adjust_stock_unauthorized(client):
    response = client.post("/stock/adjust", json={"sku_id": 1, "quantity_change": 10})
    assert response.status_code == 403


def test_adjust_stock_success(client):
    create_resp = client.post(
        "/skus",
        json={"code": "TEST003", "name": "Test", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )
    sku_id = create_resp.json()["id"]

    adjust_resp = client.post(
        "/stock/adjust",
        json={"sku_id": sku_id, "quantity_change": 25},
        headers={"X-API-Key": "test-api-key"},
    )
    assert adjust_resp.status_code == 200
    data = adjust_resp.json()
    assert data["available_stock"] == 125


def test_create_reservation_success(client):
    create_resp = client.post(
        "/skus",
        json={"code": "TEST004", "name": "Test", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )
    sku_id = create_resp.json()["id"]

    res_resp = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 30, "idempotency_key": "key1", "ttl_seconds": 3600},
        headers={"X-API-Key": "test-api-key"},
    )
    assert res_resp.status_code == 201
    data = res_resp.json()
    assert data["quantity"] == 30
    assert data["status"] == "pending"


def test_create_reservation_insufficient_stock(client):
    create_resp = client.post(
        "/skus",
        json={"code": "TEST005", "name": "Test", "initial_stock": 50},
        headers={"X-API-Key": "test-api-key"},
    )
    sku_id = create_resp.json()["id"]

    res_resp = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 100, "idempotency_key": "key2", "ttl_seconds": 3600},
        headers={"X-API-Key": "test-api-key"},
    )
    assert res_resp.status_code == 400
    assert "Insufficient stock" in res_resp.json()["detail"]


def test_reservation_idempotency(client):
    create_resp = client.post(
        "/skus",
        json={"code": "TEST006", "name": "Test", "initial_stock": 200},
        headers={"X-API-Key": "test-api-key"},
    )
    sku_id = create_resp.json()["id"]

    res_resp1 = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 40, "idempotency_key": "idempotent-key", "ttl_seconds": 3600},
        headers={"X-API-Key": "test-api-key"},
    )
    res_resp2 = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 40, "idempotency_key": "idempotent-key", "ttl_seconds": 3600},
        headers={"X-API-Key": "test-api-key"},
    )

    assert res_resp1.status_code == 201
    assert res_resp2.status_code == 201
    assert res_resp1.json()["id"] == res_resp2.json()["id"]


def test_confirm_reservation(client):
    create_resp = client.post(
        "/skus",
        json={"code": "TEST007", "name": "Test", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )
    sku_id = create_resp.json()["id"]

    res_resp = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 50, "idempotency_key": "key3", "ttl_seconds": 3600},
        headers={"X-API-Key": "test-api-key"},
    )
    reservation_id = res_resp.json()["id"]

    confirm_resp = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "test-api-key"},
    )
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["status"] == "confirmed"


def test_cancel_reservation(client):
    create_resp = client.post(
        "/skus",
        json={"code": "TEST008", "name": "Test", "initial_stock": 100},
        headers={"X-API-Key": "test-api-key"},
    )
    sku_id = create_resp.json()["id"]

    res_resp = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 35, "idempotency_key": "key4", "ttl_seconds": 3600},
        headers={"X-API-Key": "test-api-key"},
    )
    reservation_id = res_resp.json()["id"]

    cancel_resp = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"X-API-Key": "test-api-key"},
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"


def test_list_orders_empty(client):
    response = client.get("/orders")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["limit"] == 20
    assert data["offset"] == 0
    assert data["items"] == []


def test_list_orders_with_pagination(client):
    create_resp = client.post(
        "/skus",
        json={"code": "TEST009", "name": "Test", "initial_stock": 500},
        headers={"X-API-Key": "test-api-key"},
    )
    sku_id = create_resp.json()["id"]

    for i in range(5):
        res_resp = client.post(
            "/reservations",
            json={
                "sku_id": sku_id,
                "quantity": 20,
                "idempotency_key": f"key-{i}",
                "ttl_seconds": 3600,
            },
            headers={"X-API-Key": "test-api-key"},
        )
        reservation_id = res_resp.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"X-API-Key": "test-api-key"},
        )

    list_resp = client.get("/orders?limit=2&offset=0")
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total"] == 5
    assert data["limit"] == 2
    assert data["offset"] == 0
    assert len(data["items"]) == 2


def test_list_orders_invalid_limit(client):
    response = client.get("/orders?limit=101")
    assert response.status_code == 400


def test_list_orders_invalid_offset(client):
    response = client.get("/orders?offset=-1")
    assert response.status_code == 400


def test_unauthorized_mutation(client):
    response = client.post(
        "/skus",
        json={"code": "TEST010", "name": "Test", "initial_stock": 100},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 403
