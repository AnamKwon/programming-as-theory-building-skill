import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from commerce_service.models import Base
from commerce_service.app import app, get_db

VALID_API_KEY = {"X-API-Key": "test-key-123"}


@pytest.fixture
def db_engine():
    database_url = "sqlite:///:memory:"
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(db_engine):
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = session_local()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku_requires_api_key(client):
    response = client.post("/skus", json={"code": "TEST", "name": "Test", "initial_stock": 10})
    assert response.status_code == 403


def test_create_sku_success(client):
    response = client.post(
        "/skus",
        json={"code": "WIDGET-001", "name": "Blue Widget", "initial_stock": 100},
        headers=VALID_API_KEY,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == "WIDGET-001"
    assert data["available_stock"] == 100


def test_adjust_stock(client):
    client.post(
        "/skus",
        json={"code": "WIDGET-001", "name": "Blue Widget", "initial_stock": 50},
        headers=VALID_API_KEY,
    )
    response = client.post(
        "/skus/WIDGET-001/adjust", json={"quantity": 25}, headers=VALID_API_KEY
    )
    assert response.status_code == 200
    assert response.json()["available_stock"] == 75


def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"code": "WIDGET-001", "name": "Blue Widget", "initial_stock": 100},
        headers=VALID_API_KEY,
    )
    response = client.post(
        "/reservations",
        json={"sku_code": "WIDGET-001", "quantity": 10, "idempotency_key": "key1"},
        headers=VALID_API_KEY,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku_code"] == "WIDGET-001"
    assert data["quantity"] == 10
    assert data["state"] == "pending"


def test_create_reservation_insufficient_stock(client):
    client.post(
        "/skus",
        json={"code": "WIDGET-001", "name": "Blue Widget", "initial_stock": 5},
        headers=VALID_API_KEY,
    )
    response = client.post(
        "/reservations",
        json={"sku_code": "WIDGET-001", "quantity": 10, "idempotency_key": "key1"},
        headers=VALID_API_KEY,
    )
    assert response.status_code == 409
    assert "Insufficient stock" in response.json()["detail"]


def test_reservation_idempotency(client):
    client.post(
        "/skus",
        json={"code": "WIDGET-001", "name": "Blue Widget", "initial_stock": 100},
        headers=VALID_API_KEY,
    )
    res1 = client.post(
        "/reservations",
        json={"sku_code": "WIDGET-001", "quantity": 10, "idempotency_key": "key1"},
        headers=VALID_API_KEY,
    )
    res2 = client.post(
        "/reservations",
        json={"sku_code": "WIDGET-001", "quantity": 10, "idempotency_key": "key1"},
        headers=VALID_API_KEY,
    )
    assert res1.json()["id"] == res2.json()["id"]


def test_confirm_reservation(client):
    client.post(
        "/skus",
        json={"code": "WIDGET-001", "name": "Blue Widget", "initial_stock": 100},
        headers=VALID_API_KEY,
    )
    res = client.post(
        "/reservations",
        json={"sku_code": "WIDGET-001", "quantity": 10, "idempotency_key": "key1"},
        headers=VALID_API_KEY,
    )
    reservation_id = res.json()["id"]

    response = client.post(f"/reservations/{reservation_id}/confirm", headers=VALID_API_KEY)
    assert response.status_code == 200
    assert response.json()["state"] == "confirmed"


def test_cancel_reservation(client):
    client.post(
        "/skus",
        json={"code": "WIDGET-001", "name": "Blue Widget", "initial_stock": 100},
        headers=VALID_API_KEY,
    )
    res = client.post(
        "/reservations",
        json={"sku_code": "WIDGET-001", "quantity": 10, "idempotency_key": "key1"},
        headers=VALID_API_KEY,
    )
    reservation_id = res.json()["id"]

    response = client.post(f"/reservations/{reservation_id}/cancel", headers=VALID_API_KEY)
    assert response.status_code == 200
    assert response.json()["state"] == "cancelled"


def test_list_orders_pagination(client):
    # Create 15 orders via POST /orders
    for _ in range(15):
        client.post("/orders", headers=VALID_API_KEY)

    response = client.get("/orders?page=1&page_size=10", headers=VALID_API_KEY)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 15
    assert len(data["items"]) == 10
    assert data["page"] == 1

    response = client.get("/orders?page=2&page_size=10", headers=VALID_API_KEY)
    assert len(response.json()["items"]) == 5


def test_unauthorized_mutation(client):
    response = client.post(
        "/skus", json={"code": "WIDGET-001", "name": "Blue Widget", "initial_stock": 100}
    )
    assert response.status_code == 403


def test_get_order(client):
    # Create an order
    res = client.post("/orders", headers=VALID_API_KEY)
    order_id = res.json()["id"]

    response = client.get(f"/orders/{order_id}", headers=VALID_API_KEY)
    assert response.status_code == 200
    assert response.json()["id"] == order_id
