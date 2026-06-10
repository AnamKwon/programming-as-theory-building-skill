import pytest
import tempfile
import os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from commerce_service.app import app, get_db
from commerce_service.models import Base


@pytest.fixture
def db_session():
    """SQLite database for API tests."""
    # Use a temporary file database to avoid threading issues with in-memory SQLite
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.close(tmp_fd)

    db_url = f"sqlite:///{tmp_path}"
    engine = create_engine(db_url)
    Base.metadata.create_all(bind=engine)
    session = Session(bind=engine)

    yield session

    session.close()
    try:
        os.unlink(tmp_path)
    except:
        pass


@pytest.fixture
def client(db_session):
    """FastAPI test client with database."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def api_key():
    """Valid API key for mutation endpoints."""
    return "test-key-12345"


class TestHealth:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    def test_create_sku_success(self, client, api_key):
        response = client.post(
            "/skus",
            json={"name": "WIDGET-A", "initial_stock": 100},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "WIDGET-A"
        assert data["stock_level"] == 100

    def test_create_sku_missing_api_key(self, client):
        response = client.post(
            "/skus",
            json={"name": "WIDGET-B", "initial_stock": 50},
        )
        assert response.status_code == 403
        assert "X-API-Key" in response.json()["detail"]

    def test_create_sku_invalid_api_key(self, client):
        response = client.post(
            "/skus",
            json={"name": "WIDGET-C", "initial_stock": 50},
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 403

    def test_adjust_stock_increase(self, client, api_key):
        client.post(
            "/skus",
            json={"name": "WIDGET-D", "initial_stock": 50},
            headers={"X-API-Key": api_key},
        )
        response = client.patch(
            "/skus/1/stock",
            json={"adjustment": 25},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        assert response.json()["stock_level"] == 75

    def test_adjust_stock_decrease(self, client, api_key):
        client.post(
            "/skus",
            json={"name": "WIDGET-E", "initial_stock": 100},
            headers={"X-API-Key": api_key},
        )
        response = client.patch(
            "/skus/1/stock",
            json={"adjustment": -30},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        assert response.json()["stock_level"] == 70


class TestReservationEndpoints:
    def test_create_reservation_success(self, client, api_key):
        client.post(
            "/skus",
            json={"name": "WIDGET-F", "initial_stock": 100},
            headers={"X-API-Key": api_key},
        )
        response = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 30},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku_id"] == 1
        assert data["quantity"] == 30
        assert data["status"] == "pending"

    def test_create_reservation_insufficient_stock(self, client, api_key):
        client.post(
            "/skus",
            json={"name": "WIDGET-G", "initial_stock": 50},
            headers={"X-API-Key": api_key},
        )
        response = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 100},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 409
        assert "50 in stock" in response.json()["detail"]

    def test_create_reservation_missing_api_key(self, client):
        response = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 30},
        )
        assert response.status_code == 403

    def test_create_reservation_with_idempotency_key(self, client, api_key):
        client.post(
            "/skus",
            json={"name": "WIDGET-H", "initial_stock": 100},
            headers={"X-API-Key": api_key},
        )
        key = "unique-key-789"
        res1 = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 25, "idempotency_key": key},
            headers={"X-API-Key": api_key},
        )
        res2 = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 50, "idempotency_key": key},
            headers={"X-API-Key": api_key},
        )
        assert res1.json()["id"] == res2.json()["id"]
        assert res2.json()["quantity"] == 25

    def test_confirm_reservation(self, client, api_key):
        client.post(
            "/skus",
            json={"name": "WIDGET-I", "initial_stock": 100},
            headers={"X-API-Key": api_key},
        )
        res = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 30},
            headers={"X-API-Key": api_key},
        )
        res_id = res.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        assert data["quantity"] == 30

    def test_confirm_nonexistent_reservation(self, client, api_key):
        response = client.post(
            "/reservations/999/confirm",
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 404

    def test_cancel_reservation(self, client, api_key):
        client.post(
            "/skus",
            json={"name": "WIDGET-J", "initial_stock": 100},
            headers={"X-API-Key": api_key},
        )
        res = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 20},
            headers={"X-API-Key": api_key},
        )
        res_id = res.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/cancel",
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_cancel_nonexistent_reservation(self, client, api_key):
        response = client.post(
            "/reservations/999/cancel",
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 404


class TestExpiredReservation:
    def test_confirm_expired_reservation(self, client, api_key, db_session):
        client.post(
            "/skus",
            json={"name": "WIDGET-K", "initial_stock": 100},
            headers={"X-API-Key": api_key},
        )
        res = client.post(
            "/reservations",
            json={"sku_id": 1, "quantity": 30},
            headers={"X-API-Key": api_key},
        )
        res_id = res.json()["id"]

        from datetime import datetime, timedelta
        from commerce_service.models import Reservation

        reservation = db_session.query(Reservation).filter(Reservation.id == res_id).first()
        reservation.expires_at = datetime.utcnow() - timedelta(minutes=1)
        db_session.commit()

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 410
        assert "expired" in response.json()["detail"].lower()


class TestOrderEndpoints:
    def test_list_orders_empty(self, client):
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_list_orders_with_pagination(self, client, api_key):
        client.post(
            "/skus",
            json={"name": "WIDGET-L", "initial_stock": 500},
            headers={"X-API-Key": api_key},
        )

        for i in range(5):
            res = client.post(
                "/reservations",
                json={"sku_id": 1, "quantity": 20},
                headers={"X-API-Key": api_key},
            )
            res_id = res.json()["id"]
            client.post(
                f"/reservations/{res_id}/confirm",
                headers={"X-API-Key": api_key},
            )

        page1 = client.get("/orders?skip=0&limit=2")
        assert page1.status_code == 200
        data1 = page1.json()
        assert len(data1["items"]) == 2
        assert data1["total"] == 5

        page2 = client.get("/orders?skip=2&limit=2")
        data2 = page2.json()
        assert len(data2["items"]) == 2

        page3 = client.get("/orders?skip=4&limit=2")
        data3 = page3.json()
        assert len(data3["items"]) == 1

    def test_list_orders_default_pagination(self, client, api_key):
        client.post(
            "/skus",
            json={"name": "WIDGET-M", "initial_stock": 300},
            headers={"X-API-Key": api_key},
        )

        for i in range(3):
            res = client.post(
                "/reservations",
                json={"sku_id": 1, "quantity": 20},
                headers={"X-API-Key": api_key},
            )
            res_id = res.json()["id"]
            client.post(
                f"/reservations/{res_id}/confirm",
                headers={"X-API-Key": api_key},
            )

        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["skip"] == 0
        assert data["limit"] == 20
        assert len(data["items"]) == 3

    def test_list_orders_invalid_pagination(self, client):
        response = client.get("/orders?limit=0")
        assert response.status_code == 422

        response = client.get("/orders?limit=101")
        assert response.status_code == 422

        response = client.get("/orders?skip=-1")
        assert response.status_code == 422
