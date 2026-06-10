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


class TestHealth:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKU:
    def test_create_sku(self, client):
        response = client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "initial_stock": 100},
            headers={"X-API-Key": "dev-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "SKU001"
        assert data["name"] == "Widget"
        assert data["stock_quantity"] == 100

    def test_create_sku_unauthorized(self, client):
        response = client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "initial_stock": 100},
        )
        assert response.status_code == 401

    def test_adjust_stock(self, client):
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "initial_stock": 100},
            headers={"X-API-Key": "dev-key"},
        )
        response = client.post(
            "/skus/SKU001/adjust-stock",
            json={"adjustment": 50},
            headers={"X-API-Key": "dev-key"},
        )
        assert response.status_code == 200
        assert response.json()["stock_quantity"] == 150

    def test_adjust_stock_sku_not_found(self, client):
        response = client.post(
            "/skus/NONEXISTENT/adjust-stock",
            json={"adjustment": 50},
            headers={"X-API-Key": "dev-key"},
        )
        assert response.status_code == 404


class TestReservation:
    def test_create_reservation(self, client):
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "initial_stock": 100},
            headers={"X-API-Key": "dev-key"},
        )
        response = client.post(
            "/reservations",
            json={
                "sku_id": "SKU001",
                "quantity": 50,
                "idempotency_key": "IDEMPOTENCY_1",
            },
            headers={"X-API-Key": "dev-key"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku_id"] == "SKU001"
        assert data["quantity"] == 50

    def test_create_reservation_insufficient_stock(self, client):
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "initial_stock": 30},
            headers={"X-API-Key": "dev-key"},
        )
        response = client.post(
            "/reservations",
            json={
                "sku_id": "SKU001",
                "quantity": 50,
                "idempotency_key": "IDEMPOTENCY_1",
            },
            headers={"X-API-Key": "dev-key"},
        )
        assert response.status_code == 409

    def test_create_reservation_idempotent_retry(self, client):
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "initial_stock": 100},
            headers={"X-API-Key": "dev-key"},
        )
        res1 = client.post(
            "/reservations",
            json={
                "sku_id": "SKU001",
                "quantity": 50,
                "idempotency_key": "IDEMPOTENCY_1",
            },
            headers={"X-API-Key": "dev-key"},
        )
        res2 = client.post(
            "/reservations",
            json={
                "sku_id": "SKU001",
                "quantity": 50,
                "idempotency_key": "IDEMPOTENCY_1",
            },
            headers={"X-API-Key": "dev-key"},
        )
        assert res1.status_code == 201
        assert res2.status_code == 201
        assert res1.json()["id"] == res2.json()["id"]

    def test_confirm_reservation(self, client):
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "initial_stock": 100},
            headers={"X-API-Key": "dev-key"},
        )
        res = client.post(
            "/reservations",
            json={
                "sku_id": "SKU001",
                "quantity": 50,
                "idempotency_key": "IDEMPOTENCY_1",
            },
            headers={"X-API-Key": "dev-key"},
        )
        res_id = res.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": "dev-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["reservation_id"] == res_id
        assert data["status"] == "confirmed"

    def test_cancel_reservation(self, client):
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "initial_stock": 100},
            headers={"X-API-Key": "dev-key"},
        )
        res = client.post(
            "/reservations",
            json={
                "sku_id": "SKU001",
                "quantity": 50,
                "idempotency_key": "IDEMPOTENCY_1",
            },
            headers={"X-API-Key": "dev-key"},
        )
        res_id = res.json()["id"]

        response = client.delete(
            f"/reservations/{res_id}",
            headers={"X-API-Key": "dev-key"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"


class TestOrder:
    def test_list_orders_empty(self, client):
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["orders"] == []

    def test_list_orders_with_pagination(self, client):
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "initial_stock": 100},
            headers={"X-API-Key": "dev-key"},
        )

        for i in range(5):
            res = client.post(
                "/reservations",
                json={
                    "sku_id": "SKU001",
                    "quantity": 10,
                    "idempotency_key": f"IDEMPOTENCY_{i}",
                },
                headers={"X-API-Key": "dev-key"},
            )
            res_id = res.json()["id"]
            client.post(
                f"/reservations/{res_id}/confirm",
                headers={"X-API-Key": "dev-key"},
            )

        response = client.get("/orders?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["orders"]) == 2
        assert data["limit"] == 2
        assert data["offset"] == 0

    def test_list_orders_invalid_limit(self, client):
        response = client.get("/orders?limit=101")
        assert response.status_code == 400

    def test_list_orders_invalid_offset(self, client):
        response = client.get("/orders?offset=-1")
        assert response.status_code == 400

    def test_get_order(self, client):
        client.post(
            "/skus",
            json={"id": "SKU001", "name": "Widget", "initial_stock": 100},
            headers={"X-API-Key": "dev-key"},
        )
        res = client.post(
            "/reservations",
            json={
                "sku_id": "SKU001",
                "quantity": 50,
                "idempotency_key": "IDEMPOTENCY_1",
            },
            headers={"X-API-Key": "dev-key"},
        )
        res_id = res.json()["id"]

        order = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": "dev-key"},
        )
        order_id = order.json()["id"]

        response = client.get(f"/orders/{order_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == order_id

    def test_get_order_not_found(self, client):
        response = client.get("/orders/NONEXISTENT")
        assert response.status_code == 404
