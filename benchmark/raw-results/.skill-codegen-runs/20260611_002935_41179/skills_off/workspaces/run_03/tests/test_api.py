import pytest
import os
import tempfile
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.app import app, get_service
from src.commerce_service.repository import Base, Repository
from src.commerce_service.service import CommerceService, RESERVATION_EXPIRY_SECONDS


@pytest.fixture
def test_db():
    """Create a temporary test database."""
    db_fd, db_path = tempfile.mkstemp()
    database_url = f"sqlite:///{db_path}"
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    yield SessionLocal

    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def service_with_db(test_db):
    """Create a service with test database."""
    session = test_db()
    repository = Repository(session)
    return CommerceService(repository), session


@pytest.fixture
def client(service_with_db):
    """Create a FastAPI test client with test database."""
    service, session = service_with_db

    def override_get_service():
        return service

    app.dependency_overrides[get_service] = override_get_service

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    session.close()


@pytest.fixture
def api_token():
    """Get the API token."""
    return "secret-token"


class TestHealthCheck:
    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUManagement:
    def test_create_sku_success(self, client, api_token):
        """Test creating a SKU."""
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"Authorization": f"Bearer {api_token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "SKU001"
        assert data["available_stock"] == 100

    def test_create_sku_unauthorized(self, client):
        """Test creating SKU without auth fails."""
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
        )
        assert response.status_code == 403  # or 401 depending on security setup

    def test_create_sku_invalid_token(self, client):
        """Test creating SKU with invalid token."""
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert response.status_code == 401

    def test_adjust_stock_success(self, client, api_token):
        """Test adjusting stock."""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"Authorization": f"Bearer {api_token}"},
        )
        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU001", "amount": 50},
            headers={"Authorization": f"Bearer {api_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["available_stock"] == 150

    def test_adjust_stock_negative(self, client, api_token):
        """Test decreasing stock."""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"Authorization": f"Bearer {api_token}"},
        )
        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU001", "amount": -30},
            headers={"Authorization": f"Bearer {api_token}"},
        )
        assert response.status_code == 200
        assert response.json()["available_stock"] == 70


class TestReservations:
    def test_create_reservation_success(self, client, api_token):
        """Test creating a reservation."""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"Authorization": f"Bearer {api_token}"},
        )
        response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
            headers={"Authorization": f"Bearer {api_token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "SKU001"
        assert data["quantity"] == 30
        assert data["status"] == "PENDING"

    def test_create_reservation_insufficient_stock(self, client, api_token):
        """Test reservation fails with insufficient stock."""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 20},
            headers={"Authorization": f"Bearer {api_token}"},
        )
        response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
            headers={"Authorization": f"Bearer {api_token}"},
        )
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_create_reservation_idempotency(self, client, api_token):
        """Test idempotency on reservation creation."""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"Authorization": f"Bearer {api_token}"},
        )

        res1 = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
            headers={"Authorization": f"Bearer {api_token}"},
        )
        res2 = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
            headers={"Authorization": f"Bearer {api_token}"},
        )

        assert res1.status_code == 201
        assert res2.status_code == 201
        assert res1.json()["id"] == res2.json()["id"]

    def test_confirm_reservation_success(self, client, api_token):
        """Test confirming a reservation."""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"Authorization": f"Bearer {api_token}"},
        )
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
            headers={"Authorization": f"Bearer {api_token}"},
        )
        reservation_id = res_response.json()["id"]

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"Authorization": f"Bearer {api_token}"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "CONFIRMED"

    def test_confirm_reservation_expired(self, client, api_token, service_with_db):
        """Test confirming an expired reservation."""
        service, session = service_with_db

        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"Authorization": f"Bearer {api_token}"},
        )
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
            headers={"Authorization": f"Bearer {api_token}"},
        )
        reservation_id = res_response.json()["id"]

        # Manually set reservation as old
        from src.commerce_service.repository import Reservation
        db_res = session.query(Reservation).filter(Reservation.id == reservation_id).first()
        if db_res:
            db_res.created_at = datetime.utcnow() - timedelta(seconds=RESERVATION_EXPIRY_SECONDS + 10)
            session.commit()

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"Authorization": f"Bearer {api_token}"},
        )
        assert response.status_code == 400
        assert "expired" in response.json()["detail"]

    def test_cancel_reservation_success(self, client, api_token):
        """Test cancelling a reservation."""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"Authorization": f"Bearer {api_token}"},
        )
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
            headers={"Authorization": f"Bearer {api_token}"},
        )
        reservation_id = res_response.json()["id"]

        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            headers={"Authorization": f"Bearer {api_token}"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "CANCELLED"


class TestOrders:
    def test_get_orders_pagination(self, client, api_token):
        """Test order pagination."""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 1000},
            headers={"Authorization": f"Bearer {api_token}"},
        )

        # Create and confirm reservations
        for i in range(5):
            res_response = client.post(
                "/reservations",
                json={"sku": "SKU001", "quantity": 10, "idempotency_key": f"key-{i}"},
                headers={"Authorization": f"Bearer {api_token}"},
            )
            reservation_id = res_response.json()["id"]
            client.post(
                f"/reservations/{reservation_id}/confirm",
                headers={"Authorization": f"Bearer {api_token}"},
            )

        response = client.get("/orders?page=1&size=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["size"] == 2

    def test_get_orders_second_page(self, client, api_token):
        """Test getting second page of orders."""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 1000},
            headers={"Authorization": f"Bearer {api_token}"},
        )

        for i in range(5):
            res_response = client.post(
                "/reservations",
                json={"sku": "SKU001", "quantity": 10, "idempotency_key": f"key-{i}"},
                headers={"Authorization": f"Bearer {api_token}"},
            )
            reservation_id = res_response.json()["id"]
            client.post(
                f"/reservations/{reservation_id}/confirm",
                headers={"Authorization": f"Bearer {api_token}"},
            )

        response = client.get("/orders?page=2&size=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2

    def test_get_orders_empty(self, client):
        """Test getting orders when none exist."""
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0
        assert data["total"] == 0


class TestAuthenticationFlow:
    def test_unauthorized_sku_creation(self, client):
        """Test that SKU creation requires auth."""
        response = client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
        )
        assert response.status_code == 403

    def test_unauthorized_stock_adjustment(self, client, api_token):
        """Test that stock adjustment requires auth."""
        client.post(
            "/skus",
            json={"sku": "SKU001", "initial_stock": 100},
            headers={"Authorization": f"Bearer {api_token}"},
        )
        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU001", "amount": 50},
        )
        assert response.status_code == 403

    def test_unauthorized_reservation_creation(self, client):
        """Test that reservation creation requires auth."""
        response = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 30, "idempotency_key": "key-1"},
        )
        assert response.status_code == 403

    def test_health_check_no_auth(self, client):
        """Test that health check doesn't require auth."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestHappyPath:
    def test_full_workflow(self, client, api_token):
        """Test complete workflow: Create SKU -> Reserve -> Confirm -> Get Orders."""
        # Step 1: Create SKU
        sku_response = client.post(
            "/skus",
            json={"sku": "PRODUCT-001", "initial_stock": 100},
            headers={"Authorization": f"Bearer {api_token}"},
        )
        assert sku_response.status_code == 201

        # Step 2: Create Reservation
        res_response = client.post(
            "/reservations",
            json={"sku": "PRODUCT-001", "quantity": 25, "idempotency_key": "order-123"},
            headers={"Authorization": f"Bearer {api_token}"},
        )
        assert res_response.status_code == 201
        reservation_id = res_response.json()["id"]

        # Step 3: Confirm Reservation
        confirm_response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"Authorization": f"Bearer {api_token}"},
        )
        assert confirm_response.status_code == 200
        assert confirm_response.json()["status"] == "CONFIRMED"

        # Step 4: Get Orders
        orders_response = client.get("/orders")
        assert orders_response.status_code == 200
        data = orders_response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["reservation_id"] == reservation_id
