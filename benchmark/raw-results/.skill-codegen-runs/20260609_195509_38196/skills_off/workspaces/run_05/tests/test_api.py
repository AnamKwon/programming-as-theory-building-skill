import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.app import app, get_db
from src.commerce_service.models import Base


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def get_headers(api_key="commerce-api-key-prod"):
    return {"X-API-Key": api_key}


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"sku_id": "SKU001", "initial_stock": 100},
        headers=get_headers(),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_id"] == "SKU001"
    assert data["stock_level"] == 100


def test_create_sku_no_auth(client):
    response = client.post(
        "/skus",
        json={"sku_id": "SKU001", "initial_stock": 100},
    )
    assert response.status_code == 401


def test_create_sku_invalid_auth(client):
    response = client.post(
        "/skus",
        json={"sku_id": "SKU001", "initial_stock": 100},
        headers=get_headers("wrong-key"),
    )
    assert response.status_code == 403


def test_adjust_stock_success(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "initial_stock": 100},
        headers=get_headers(),
    )
    response = client.put(
        "/skus/SKU001/stock",
        json={"quantity_delta": 50},
        headers=get_headers(),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["stock_level"] == 150


def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "initial_stock": 100},
        headers=get_headers(),
    )
    response = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 20,
            "idempotency_key": "req-1",
        },
        headers=get_headers(),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku_id"] == "SKU001"
    assert data["quantity"] == 20
    assert "reservation_id" in data
    assert "expires_at" in data


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "initial_stock": 10},
        headers=get_headers(),
    )
    response = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 20,
            "idempotency_key": "req-1",
        },
        headers=get_headers(),
    )
    assert response.status_code == 409
    assert "Insufficient stock" in response.json()["error"]


def test_create_reservation_idempotency(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "initial_stock": 100},
        headers=get_headers(),
    )
    response1 = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 20,
            "idempotency_key": "req-1",
        },
        headers=get_headers(),
    )
    response2 = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 20,
            "idempotency_key": "req-1",
        },
        headers=get_headers(),
    )
    assert response1.status_code == 201
    assert response2.status_code == 201
    assert response1.json()["reservation_id"] == response2.json()["reservation_id"]


def test_confirm_reservation_success(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "initial_stock": 100},
        headers=get_headers(),
    )
    res = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 20,
            "idempotency_key": "req-1",
        },
        headers=get_headers(),
    )
    reservation_id = res.json()["reservation_id"]

    response = client.put(
        f"/reservations/{reservation_id}/confirm",
        headers=get_headers(),
    )
    assert response.status_code == 200
    data = response.json()
    assert "order_id" in data
    assert data["sku_id"] == "SKU001"
    assert data["quantity"] == 20


def test_confirm_expired_reservation(client, db_session):
    from datetime import datetime, timedelta
    from src.commerce_service.models import ReservationOrm, OrderState

    client.post(
        "/skus",
        json={"sku_id": "SKU001", "initial_stock": 100},
        headers=get_headers(),
    )
    res = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 20,
            "idempotency_key": "req-1",
        },
        headers=get_headers(),
    )
    reservation_id = res.json()["reservation_id"]

    reservation = db_session.query(ReservationOrm).filter(
        ReservationOrm.reservation_id == reservation_id
    ).first()
    reservation.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db_session.commit()

    response = client.put(
        f"/reservations/{reservation_id}/confirm",
        headers=get_headers(),
    )
    assert response.status_code == 410
    assert "expired" in response.json()["error"].lower()


def test_cancel_reservation_success(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "initial_stock": 100},
        headers=get_headers(),
    )
    res = client.post(
        "/reservations",
        json={
            "sku_id": "SKU001",
            "quantity": 20,
            "idempotency_key": "req-1",
        },
        headers=get_headers(),
    )
    reservation_id = res.json()["reservation_id"]

    response = client.put(
        f"/reservations/{reservation_id}/cancel",
        headers=get_headers(),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reservation_id"] == reservation_id


def test_list_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku_id": "SKU001", "initial_stock": 1000},
        headers=get_headers(),
    )

    for i in range(15):
        res = client.post(
            "/reservations",
            json={
                "sku_id": "SKU001",
                "quantity": 10,
                "idempotency_key": f"req-{i}",
            },
            headers=get_headers(),
        )
        reservation_id = res.json()["reservation_id"]
        client.put(
            f"/reservations/{reservation_id}/confirm",
            headers=get_headers(),
        )

    response1 = client.get("/orders?limit=10", headers=get_headers())
    assert response1.status_code == 200
    data1 = response1.json()
    assert len(data1["orders"]) == 10
    assert data1["has_more"] is True
    assert data1["next_cursor"] is not None

    response2 = client.get(
        f"/orders?limit=10&cursor={data1['next_cursor']}",
        headers=get_headers(),
    )
    data2 = response2.json()
    assert len(data2["orders"]) == 5
    assert data2["has_more"] is False


def test_list_orders_no_auth(client):
    response = client.get("/orders")
    assert response.status_code == 401
