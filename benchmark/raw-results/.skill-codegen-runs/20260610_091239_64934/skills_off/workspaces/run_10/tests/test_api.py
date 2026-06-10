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


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_requires_auth(client):
    response = client.post(
        "/skus", json={"code": "SKU-001", "description": "Product"}
    )
    assert response.status_code == 403


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"code": "SKU-001", "description": "Test Product"},
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == "SKU-001"
    assert data["description"] == "Test Product"
    assert data["id"] is not None


def test_adjust_stock_success(client):
    sku_res = client.post(
        "/skus",
        json={"code": "SKU-002", "description": "Product"},
        headers={"X-API-Key": "test-key-123"},
    )
    sku_id = sku_res.json()["id"]

    response = client.patch(
        f"/stock/{sku_id}",
        json={"adjustment": 100},
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["quantity"] == 100


def test_adjust_stock_negative_fails(client):
    sku_res = client.post(
        "/skus",
        json={"code": "SKU-003", "description": "Product"},
        headers={"X-API-Key": "test-key-123"},
    )
    sku_id = sku_res.json()["id"]

    response = client.patch(
        f"/stock/{sku_id}",
        json={"adjustment": -10},
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 400


def test_create_reservation_success(client):
    sku_res = client.post(
        "/skus",
        json={"code": "SKU-004", "description": "Product"},
        headers={"X-API-Key": "test-key-123"},
    )
    sku_id = sku_res.json()["id"]

    client.patch(
        f"/stock/{sku_id}",
        json={"adjustment": 100},
        headers={"X-API-Key": "test-key-123"},
    )

    response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10},
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_id"] == sku_id
    assert data["quantity"] == 10
    assert data["status"] == "pending"
    assert data["id"] is not None


def test_create_reservation_insufficient_stock(client):
    sku_res = client.post(
        "/skus",
        json={"code": "SKU-005", "description": "Product"},
        headers={"X-API-Key": "test-key-123"},
    )
    sku_id = sku_res.json()["id"]

    client.patch(
        f"/stock/{sku_id}",
        json={"adjustment": 5},
        headers={"X-API-Key": "test-key-123"},
    )

    response = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10},
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 409


def test_create_reservation_idempotent(client):
    sku_res = client.post(
        "/skus",
        json={"code": "SKU-006", "description": "Product"},
        headers={"X-API-Key": "test-key-123"},
    )
    sku_id = sku_res.json()["id"]

    client.patch(
        f"/stock/{sku_id}",
        json={"adjustment": 100},
        headers={"X-API-Key": "test-key-123"},
    )

    res1 = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-key-123"},
    )
    res2 = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "key-1"},
        headers={"X-API-Key": "test-key-123"},
    )

    assert res1.json()["id"] == res2.json()["id"]


def test_confirm_reservation_success(client):
    sku_res = client.post(
        "/skus",
        json={"code": "SKU-007", "description": "Product"},
        headers={"X-API-Key": "test-key-123"},
    )
    sku_id = sku_res.json()["id"]

    client.patch(
        f"/stock/{sku_id}",
        json={"adjustment": 100},
        headers={"X-API-Key": "test-key-123"},
    )

    res_res = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10},
        headers={"X-API-Key": "test-key-123"},
    )
    res_id = res_res.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/confirm",
        json={},
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["order_id"] is not None
    assert data["status"] == "confirmed"


def test_confirm_expired_reservation(client, db_session):
    from commerce_service.models import ReservationRow
    from datetime import datetime, timedelta

    sku_res = client.post(
        "/skus",
        json={"code": "SKU-008", "description": "Product"},
        headers={"X-API-Key": "test-key-123"},
    )
    sku_id = sku_res.json()["id"]

    client.patch(
        f"/stock/{sku_id}",
        json={"adjustment": 100},
        headers={"X-API-Key": "test-key-123"},
    )

    res_res = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10},
        headers={"X-API-Key": "test-key-123"},
    )
    res_id = res_res.json()["id"]

    # Make reservation expired
    reservation = db_session.query(ReservationRow).filter(ReservationRow.id == res_id).first()
    reservation.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db_session.commit()

    response = client.post(
        f"/reservations/{res_id}/confirm",
        json={},
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 410


def test_cancel_reservation_success(client):
    sku_res = client.post(
        "/skus",
        json={"code": "SKU-009", "description": "Product"},
        headers={"X-API-Key": "test-key-123"},
    )
    sku_id = sku_res.json()["id"]

    client.patch(
        f"/stock/{sku_id}",
        json={"adjustment": 100},
        headers={"X-API-Key": "test-key-123"},
    )

    res_res = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10},
        headers={"X-API-Key": "test-key-123"},
    )
    res_id = res_res.json()["id"]

    response = client.post(
        f"/reservations/{res_id}/cancel",
        json={},
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_list_orders(client):
    sku_res = client.post(
        "/skus",
        json={"code": "SKU-010", "description": "Product"},
        headers={"X-API-Key": "test-key-123"},
    )
    sku_id = sku_res.json()["id"]

    client.patch(
        f"/stock/{sku_id}",
        json={"adjustment": 500},
        headers={"X-API-Key": "test-key-123"},
    )

    for i in range(15):
        res_res = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 10},
            headers={"X-API-Key": "test-key-123"},
        )
        res_id = res_res.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            json={},
            headers={"X-API-Key": "test-key-123"},
        )

    response = client.get(
        "/orders?offset=0&limit=10",
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 15
    assert len(data["items"]) == 10
    assert data["offset"] == 0
    assert data["limit"] == 10


def test_list_orders_pagination(client):
    sku_res = client.post(
        "/skus",
        json={"code": "SKU-011", "description": "Product"},
        headers={"X-API-Key": "test-key-123"},
    )
    sku_id = sku_res.json()["id"]

    client.patch(
        f"/stock/{sku_id}",
        json={"adjustment": 500},
        headers={"X-API-Key": "test-key-123"},
    )

    for i in range(25):
        res_res = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 10},
            headers={"X-API-Key": "test-key-123"},
        )
        res_id = res_res.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            json={},
            headers={"X-API-Key": "test-key-123"},
        )

    page1 = client.get(
        "/orders?offset=0&limit=10",
        headers={"X-API-Key": "test-key-123"},
    ).json()
    page2 = client.get(
        "/orders?offset=10&limit=10",
        headers={"X-API-Key": "test-key-123"},
    ).json()
    page3 = client.get(
        "/orders?offset=20&limit=10",
        headers={"X-API-Key": "test-key-123"},
    ).json()

    assert page1["total"] == 25
    assert len(page1["items"]) == 10
    assert len(page2["items"]) == 10
    assert len(page3["items"]) == 5


def test_get_order(client):
    sku_res = client.post(
        "/skus",
        json={"code": "SKU-012", "description": "Product"},
        headers={"X-API-Key": "test-key-123"},
    )
    sku_id = sku_res.json()["id"]

    client.patch(
        f"/stock/{sku_id}",
        json={"adjustment": 100},
        headers={"X-API-Key": "test-key-123"},
    )

    res_res = client.post(
        "/reservations",
        json={"sku_id": sku_id, "quantity": 10},
        headers={"X-API-Key": "test-key-123"},
    )
    res_id = res_res.json()["id"]

    order_res = client.post(
        f"/reservations/{res_id}/confirm",
        json={},
        headers={"X-API-Key": "test-key-123"},
    )
    order_id = order_res.json()["order_id"]

    response = client.get(
        f"/orders/{order_id}",
        headers={"X-API-Key": "test-key-123"},
    )
    assert response.status_code == 200
    assert response.json()["id"] == order_id


def test_unauthorized_mutation(client):
    response = client.post(
        "/skus",
        json={"code": "SKU-013", "description": "Product"},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 403
