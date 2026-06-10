import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.app import app, get_db
from src.commerce_service.models import Base


@pytest.fixture(autouse=True)
def reset_db():
    engine = create_engine(
        "sqlite:///test_commerce.db",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(reset_db):
    return TestClient(app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget A"},
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_id"] == "SKU-001"
    assert data["name"] == "Widget A"


def test_create_sku_unauthorized(client):
    response = client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget A"},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 401


def test_create_sku_missing_api_key(client):
    response = client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget A"},
    )
    assert response.status_code == 422


def test_adjust_stock_success(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget A"},
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )

    response = client.post(
        "/stock/SKU-001/adjust",
        json={"quantity": 100},
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available"] == 100
    assert data["reserved"] == 0
    assert data["total"] == 100


def test_adjust_stock_not_found(client):
    response = client.post(
        "/stock/SKU-999/adjust",
        json={"quantity": 100},
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )
    assert response.status_code == 404


def test_create_reservation_happy_path(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget A"},
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )

    client.post(
        "/stock/SKU-001/adjust",
        json={"quantity": 100},
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )

    response = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 10, "idempotency_key": "idem-1"},
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_id"] == "SKU-001"
    assert data["quantity"] == 10
    assert data["status"] == "pending"


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget A"},
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )

    client.post(
        "/stock/SKU-001/adjust",
        json={"quantity": 5},
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )

    response = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 10, "idempotency_key": "idem-1"},
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )
    assert response.status_code == 409


def test_create_reservation_idempotent_retry(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget A"},
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )

    client.post(
        "/stock/SKU-001/adjust",
        json={"quantity": 100},
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )

    res1 = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 10, "idempotency_key": "idem-1"},
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )
    res1_data = res1.json()

    res2 = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 10, "idempotency_key": "idem-1"},
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )
    res2_data = res2.json()

    assert res1_data["reservation_id"] == res2_data["reservation_id"]
    assert res1.status_code == 201
    assert res2.status_code == 201


def test_confirm_reservation_happy_path(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget A"},
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )

    client.post(
        "/stock/SKU-001/adjust",
        json={"quantity": 100},
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )

    res_resp = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 10, "idempotency_key": "idem-1"},
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )
    reservation_id = res_resp.json()["reservation_id"]

    order_resp = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )
    assert order_resp.status_code == 200
    data = order_resp.json()
    assert data["sku_id"] == "SKU-001"
    assert data["quantity"] == 10
    assert data["reservation_id"] == reservation_id


def test_confirm_reservation_already_confirmed(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget A"},
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )

    client.post(
        "/stock/SKU-001/adjust",
        json={"quantity": 100},
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )

    res_resp = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 10, "idempotency_key": "idem-1"},
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )
    reservation_id = res_resp.json()["reservation_id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )

    resp = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )
    assert resp.status_code == 400


def test_cancel_reservation_happy_path(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget A"},
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )

    client.post(
        "/stock/SKU-001/adjust",
        json={"quantity": 100},
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )

    res_resp = client.post(
        "/reservations",
        json={"sku_id": "SKU-001", "quantity": 10, "idempotency_key": "idem-1"},
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )
    reservation_id = res_resp.json()["reservation_id"]

    resp = client.delete(
        f"/reservations/{reservation_id}",
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "cancelled"


def test_cancel_reservation_not_found(client):
    resp = client.delete(
        "/reservations/non-existent-id",
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )
    assert resp.status_code == 404


def test_list_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget A"},
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )

    client.post(
        "/stock/SKU-001/adjust",
        json={"quantity": 100},
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )

    reservation_ids = []
    for i in range(15):
        res_resp = client.post(
            "/reservations",
            json={"sku_id": "SKU-001", "quantity": 1, "idempotency_key": f"idem-{i}"},
            headers={"X-API-Key": "sk-dev-test-key-12345"},
        )
        reservation_ids.append(res_resp.json()["reservation_id"])

    for res_id in reservation_ids:
        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": "sk-dev-test-key-12345"},
        )

    resp = client.get(
        "/orders?offset=0&limit=10",
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 10
    assert data["total"] == 15
    assert data["offset"] == 0
    assert data["limit"] == 10

    resp = client.get(
        "/orders?offset=10&limit=10",
        headers={"X-API-Key": "sk-dev-test-key-12345"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 5
    assert data["total"] == 15


def test_mutation_requires_api_key(client):
    response = client.post(
        "/skus",
        json={"sku_id": "SKU-001", "name": "Widget A"},
    )
    assert response.status_code == 422
