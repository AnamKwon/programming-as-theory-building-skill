import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.app import app, get_db
from commerce_service.models import Base


@pytest.fixture
def test_db_path(tmp_path):
    """Create a temporary database file for testing."""
    return str(tmp_path / "test.db")


@pytest.fixture
def db(test_db_path):
    """Create file-based SQLite database for testing."""
    engine = create_engine(f"sqlite:///{test_db_path}")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def client(db, test_db_path):
    """Create test client with test database."""
    import commerce_service.app as app_module
    from commerce_service.models import get_session_factory

    # Override the get_db dependency to use test database
    SessionLocal = get_session_factory(db.get_bind())

    def override_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    # Set the override before creating the test client
    app.dependency_overrides[get_db] = override_get_db

    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


API_KEY = "commerce-service-key"


class TestHealth:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestSKUEndpoints:
    def test_create_sku(self, client):
        response = client.post(
            "/skus",
            json={"sku": "WIDGET-001", "name": "Widget A", "stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "WIDGET-001"
        assert data["stock"] == 100
        assert data["reserved"] == 0

    def test_create_sku_unauthorized(self, client):
        response = client.post(
            "/skus",
            json={"sku": "WIDGET-001", "name": "Widget A", "stock": 100},
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 401

    def test_create_sku_no_api_key(self, client):
        response = client.post(
            "/skus",
            json={"sku": "WIDGET-001", "name": "Widget A", "stock": 100},
        )
        assert response.status_code == 403

    def test_create_sku_duplicate(self, client):
        client.post(
            "/skus",
            json={"sku": "WIDGET-001", "name": "Widget A", "stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        response = client.post(
            "/skus",
            json={"sku": "WIDGET-001", "name": "Widget A", "stock": 50},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 409

    def test_get_sku(self, client):
        client.post(
            "/skus",
            json={"sku": "WIDGET-001", "name": "Widget A", "stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        response = client.get("/skus/WIDGET-001")
        assert response.status_code == 200
        data = response.json()
        assert data["sku"] == "WIDGET-001"
        assert data["stock"] == 100

    def test_get_sku_not_found(self, client):
        response = client.get("/skus/NONEXISTENT")
        assert response.status_code == 404

    def test_adjust_stock(self, client):
        client.post(
            "/skus",
            json={"sku": "WIDGET-001", "name": "Widget A", "stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        response = client.patch(
            "/skus/WIDGET-001/stock",
            json={"quantity": 50},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["stock"] == 150

    def test_adjust_stock_unauthorized(self, client):
        client.post(
            "/skus",
            json={"sku": "WIDGET-001", "name": "Widget A", "stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        response = client.patch(
            "/skus/WIDGET-001/stock",
            json={"quantity": 50},
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 401


class TestReservationEndpoints:
    def test_create_reservation(self, client):
        client.post(
            "/skus",
            json={"sku": "WIDGET-001", "name": "Widget A", "stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        response = client.post(
            "/reservations",
            json={"sku": "WIDGET-001", "quantity": 10, "idempotency_key": "idem-1"},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "WIDGET-001"
        assert data["quantity"] == 10
        assert data["status"] == "PENDING"

    def test_create_reservation_insufficient_stock(self, client):
        client.post(
            "/skus",
            json={"sku": "WIDGET-001", "name": "Widget A", "stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        response = client.post(
            "/reservations",
            json={"sku": "WIDGET-001", "quantity": 150, "idempotency_key": "idem-1"},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 409

    def test_create_reservation_idempotent(self, client):
        client.post(
            "/skus",
            json={"sku": "WIDGET-001", "name": "Widget A", "stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        response1 = client.post(
            "/reservations",
            json={"sku": "WIDGET-001", "quantity": 10, "idempotency_key": "idem-1"},
            headers={"X-API-Key": API_KEY},
        )
        response2 = client.post(
            "/reservations",
            json={"sku": "WIDGET-001", "quantity": 10, "idempotency_key": "idem-1"},
            headers={"X-API-Key": API_KEY},
        )
        assert response1.status_code == 201
        assert response2.status_code == 201
        assert response1.json()["reservation_id"] == response2.json()["reservation_id"]

    def test_create_reservation_sku_not_found(self, client):
        response = client.post(
            "/reservations",
            json={"sku": "NONEXISTENT", "quantity": 10, "idempotency_key": "idem-1"},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 404

    def test_confirm_reservation(self, client):
        client.post(
            "/skus",
            json={"sku": "WIDGET-001", "name": "Widget A", "stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        res_response = client.post(
            "/reservations",
            json={"sku": "WIDGET-001", "quantity": 10, "idempotency_key": "idem-1"},
            headers={"X-API-Key": API_KEY},
        )
        res_id = res_response.json()["reservation_id"]

        response = client.post(
            f"/reservations/{res_id}/confirm",
            json={},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "CONFIRMED"

    def test_confirm_reservation_unauthorized(self, client):
        client.post(
            "/skus",
            json={"sku": "WIDGET-001", "name": "Widget A", "stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        res_response = client.post(
            "/reservations",
            json={"sku": "WIDGET-001", "quantity": 10, "idempotency_key": "idem-1"},
            headers={"X-API-Key": API_KEY},
        )
        res_id = res_response.json()["reservation_id"]

        response = client.post(
            f"/reservations/{res_id}/confirm",
            json={},
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 401

    def test_cancel_reservation(self, client):
        client.post(
            "/skus",
            json={"sku": "WIDGET-001", "name": "Widget A", "stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        res_response = client.post(
            "/reservations",
            json={"sku": "WIDGET-001", "quantity": 10, "idempotency_key": "idem-1"},
            headers={"X-API-Key": API_KEY},
        )
        res_id = res_response.json()["reservation_id"]

        response = client.post(
            f"/reservations/{res_id}/cancel",
            json={},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "CANCELLED"


class TestOrderEndpoints:
    def test_list_orders_empty(self, client):
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["orders"] == []
        assert data["total"] == 0
        assert data["offset"] == 0
        assert data["limit"] == 50

    def test_list_orders_pagination(self, client):
        client.post(
            "/skus",
            json={"sku": "WIDGET-001", "name": "Widget A", "stock": 100},
            headers={"X-API-Key": API_KEY},
        )

        # Create and confirm 5 reservations
        for i in range(5):
            res_response = client.post(
                "/reservations",
                json={"sku": "WIDGET-001", "quantity": 10, "idempotency_key": f"idem-{i}"},
                headers={"X-API-Key": API_KEY},
            )
            res_id = res_response.json()["reservation_id"]
            client.post(
                f"/reservations/{res_id}/confirm",
                json={},
                headers={"X-API-Key": API_KEY},
            )

        response = client.get("/orders?offset=0&limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 2
        assert data["total"] == 5
        assert data["offset"] == 0
        assert data["limit"] == 2

        response2 = client.get("/orders?offset=2&limit=2")
        data2 = response2.json()
        assert len(data2["orders"]) == 2
        assert data2["offset"] == 2

    def test_list_orders_invalid_limit(self, client):
        response = client.get("/orders?limit=101")
        assert response.status_code == 422

    def test_list_orders_negative_offset(self, client):
        response = client.get("/orders?offset=-1")
        assert response.status_code == 422
