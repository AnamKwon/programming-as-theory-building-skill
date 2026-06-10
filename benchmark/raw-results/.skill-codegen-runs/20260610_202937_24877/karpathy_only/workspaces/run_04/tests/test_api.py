import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.app import app, get_db
from commerce_service.models import Base

VALID_API_KEY = "test-api-key"


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client(db):
    return TestClient(app)


def test_health_no_auth_required(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
    )
    assert response.status_code == 401


def test_create_sku_valid_api_key(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["stock"] == 100


def test_adjust_stock_unauthorized(client):
    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 10},
    )
    assert response.status_code == 401


def test_adjust_stock_happy_path(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 50},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["stock"] == 150


def test_create_reservation_unauthorized(client):
    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
    )
    assert response.status_code == 401


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 50},
        headers={"X-API-Key": VALID_API_KEY},
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 100, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


def test_create_reservation_happy_path(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "SKU001"
    assert data["quantity"] == 50
    assert data["status"] == "PENDING"


def test_create_reservation_idempotent(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )

    response1 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    res_id_1 = response1.json()["id"]

    response2 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    res_id_2 = response2.json()["id"]

    assert res_id_1 == res_id_2
    assert response2.status_code == 201


def test_confirm_reservation_happy_path(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    res_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CONFIRMED"


def test_confirm_reservation_expired(client):
    from datetime import datetime, timezone

    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    res_id = res_response.json()["id"]

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from commerce_service.repository import Repository
    from commerce_service.models import Base

    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    repo = Repository(db)

    reservation = repo.get_reservation_by_id(res_id)
    old_time = datetime.fromtimestamp(
        datetime.now(timezone.utc).timestamp() - 400, tz=timezone.utc
    )
    reservation.created_at = old_time
    repo.session.commit()

    response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 400
    assert "expired" in response.json()["detail"]


def test_cancel_reservation_restores_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    res_id = res_response.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/cancel",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"


def test_get_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 1000},
        headers={"X-API-Key": VALID_API_KEY},
    )

    for i in range(25):
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 10, "idempotency_key": f"key-{i}"},
            headers={"X-API-Key": VALID_API_KEY},
        )
        res_id = res_response.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": VALID_API_KEY},
        )

    response = client.get(
        "/orders?page=1&size=10",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) == 10
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] == 25

    response = client.get(
        "/orders?page=3&size=10",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert len(response.json()["orders"]) == 5


def test_full_workflow(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"X-API-Key": VALID_API_KEY},
    )

    res_response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key-1"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert res_response.status_code == 201
    res_id = res_response.json()["id"]

    confirm_response = client.post(
        f"/reservations/{res_id}/confirm",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "CONFIRMED"

    orders_response = client.get(
        "/orders?page=1&size=10",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert orders_response.status_code == 200
    assert len(orders_response.json()["orders"]) == 1
