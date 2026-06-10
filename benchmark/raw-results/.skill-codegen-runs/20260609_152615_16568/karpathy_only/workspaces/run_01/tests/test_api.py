import pytest
import tempfile
import os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.app import app, Base, get_db
from commerce_service.models import OrderStatus, ReservationStatus


@pytest.fixture
def client():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)

    try:
        database_url = f"sqlite:///{db_path}"
        engine = create_engine(database_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine)

        def override_get_db():
            session = SessionLocal()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_get_db
        yield TestClient(app)
        app.dependency_overrides.clear()
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


class TestHealth:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    def test_create_sku_requires_api_key(self, client):
        response = client.post("/skus", json={"sku_id": "PROD-001", "quantity": 100})
        assert response.status_code == 403

    def test_create_sku_with_api_key(self, client):
        response = client.post(
            "/skus",
            json={"sku_id": "PROD-001", "quantity": 100},
            headers={"api_key": "test-api-key-123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku_id"] == "PROD-001"
        assert data["quantity"] == 100

    def test_create_duplicate_sku_fails(self, client):
        headers = {"api_key": "test-api-key-123"}
        client.post("/skus", json={"sku_id": "PROD-001", "quantity": 100}, headers=headers)
        response = client.post("/skus", json={"sku_id": "PROD-001", "quantity": 50}, headers=headers)
        assert response.status_code == 400

    def test_adjust_stock(self, client):
        headers = {"api_key": "test-api-key-123"}
        client.post("/skus", json={"sku_id": "PROD-001", "quantity": 100}, headers=headers)

        response = client.patch(
            "/skus/PROD-001/stock",
            json={"adjustment": -30},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["quantity"] == 70


class TestReservationEndpoints:
    @pytest.fixture
    def sku_setup(self, client):
        headers = {"api_key": "test-api-key-123"}
        client.post("/skus", json={"sku_id": "PROD-001", "quantity": 100}, headers=headers)
        return headers

    def test_create_reservation_requires_api_key(self, client, sku_setup):
        response = client.post(
            "/reservations",
            json={"sku_id": "PROD-001", "quantity": 50},
        )
        assert response.status_code == 403

    def test_create_reservation_happy_path(self, client, sku_setup):
        response = client.post(
            "/reservations",
            json={"sku_id": "PROD-001", "quantity": 50},
            headers=sku_setup,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku_id"] == "PROD-001"
        assert data["quantity"] == 50
        assert data["status"] == ReservationStatus.PENDING

    def test_create_reservation_insufficient_stock(self, client, sku_setup):
        response = client.post(
            "/reservations",
            json={"sku_id": "PROD-001", "quantity": 150},
            headers=sku_setup,
        )
        assert response.status_code == 409

    def test_idempotent_reservation_retry(self, client, sku_setup):
        res1 = client.post(
            "/reservations",
            json={"sku_id": "PROD-001", "quantity": 50, "idempotency_key": "idem-1"},
            headers=sku_setup,
        )
        res1_id = res1.json()["reservation_id"]

        res2 = client.post(
            "/reservations",
            json={"sku_id": "PROD-001", "quantity": 50, "idempotency_key": "idem-1"},
            headers=sku_setup,
        )
        res2_id = res2.json()["reservation_id"]

        assert res1_id == res2_id

    def test_cancel_reservation(self, client, sku_setup):
        res = client.post(
            "/reservations",
            json={"sku_id": "PROD-001", "quantity": 50},
            headers=sku_setup,
        )
        res_id = res.json()["reservation_id"]

        response = client.delete(f"/reservations/{res_id}", headers=sku_setup)
        assert response.status_code == 200
        assert response.json()["status"] == ReservationStatus.CANCELLED


class TestOrderEndpoints:
    @pytest.fixture
    def sku_and_reservation(self, client):
        headers = {"api_key": "test-api-key-123"}
        client.post("/skus", json={"sku_id": "PROD-001", "quantity": 100}, headers=headers)

        res = client.post(
            "/reservations",
            json={"sku_id": "PROD-001", "quantity": 50},
            headers=headers,
        )
        return headers, res.json()["reservation_id"]

    def test_confirm_reservation_creates_order(self, client, sku_and_reservation):
        headers, res_id = sku_and_reservation

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku_id"] == "PROD-001"
        assert data["quantity"] == 50
        assert data["status"] == OrderStatus.PENDING

    def test_unauthorized_order_lookup(self, client, sku_and_reservation):
        response = client.get("/orders")
        assert response.status_code == 403

    def test_order_list_pagination(self, client, sku_and_reservation):
        headers, _ = sku_and_reservation

        for i in range(15):
            res = client.post(
                "/reservations",
                json={"sku_id": "PROD-001", "quantity": 1},
                headers=headers,
            )
            res_id = res.json()["reservation_id"]
            client.post(f"/reservations/{res_id}/confirm", headers=headers)

        response = client.get("/orders?limit=10", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 10
        assert data["next_cursor"] is not None

        response2 = client.get(f"/orders?limit=10&cursor={data['next_cursor']}", headers=headers)
        assert response2.status_code == 200
        data2 = response2.json()
        assert len(data2["orders"]) == 5
        assert data2["next_cursor"] is None

    def test_get_order(self, client, sku_and_reservation):
        headers, res_id = sku_and_reservation

        order_res = client.post(f"/reservations/{res_id}/confirm", headers=headers)
        order_id = order_res.json()["order_id"]

        response = client.get(f"/orders/{order_id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["order_id"] == order_id
