import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.app import app, get_db
from src.commerce_service.models import Base

VALID_TOKEN = "test-token-12345"
INVALID_TOKEN = "invalid-token"


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
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


class TestSKUManagement:
    def test_create_sku_success(self, client):
        response = client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "SKU-001"
        assert data["available_stock"] == 100

    def test_create_sku_missing_token(self, client):
        response = client.post(
            "/skus",
            json={"sku": "SKU-002", "initial_stock": 100},
        )
        assert response.status_code == 403

    def test_create_sku_invalid_token(self, client):
        response = client.post(
            "/skus",
            json={"sku": "SKU-003", "initial_stock": 100},
            headers={"Authorization": f"Bearer {INVALID_TOKEN}"},
        )
        assert response.status_code == 401

    def test_adjust_stock_success(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-004", "initial_stock": 100},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU-004", "amount": 25},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["available_stock"] == 125

    def test_adjust_stock_negative(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-005", "initial_stock": 100},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU-005", "amount": -30},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["available_stock"] == 70


class TestReservations:
    def test_create_reservation_success(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-006", "initial_stock": 100},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        response = client.post(
            "/reservations",
            json={"sku": "SKU-006", "quantity": 30, "idempotency_key": "idem-001"},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "SKU-006"
        assert data["quantity"] == 30
        assert data["status"] == "PENDING"

    def test_create_reservation_insufficient_stock(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-007", "initial_stock": 20},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        response = client.post(
            "/reservations",
            json={"sku": "SKU-007", "quantity": 30, "idempotency_key": "idem-002"},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Insufficient stock"

    def test_create_reservation_idempotency(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-008", "initial_stock": 100},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        response1 = client.post(
            "/reservations",
            json={"sku": "SKU-008", "quantity": 25, "idempotency_key": "idem-003"},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert response1.status_code == 201
        data1 = response1.json()

        response2 = client.post(
            "/reservations",
            json={"sku": "SKU-008", "quantity": 25, "idempotency_key": "idem-003"},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert response2.status_code == 201
        data2 = response2.json()

        assert data1["id"] == data2["id"]
        assert data1["created_at"] == data2["created_at"]

        sku_response = client.get(
            "/health",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert sku_response.status_code == 200

    def test_create_reservation_missing_auth(self, client):
        response = client.post(
            "/reservations",
            json={"sku": "SKU-009", "quantity": 10, "idempotency_key": "idem-004"},
        )
        assert response.status_code == 403


class TestConfirmReservation:
    def test_confirm_reservation_success(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-010", "initial_stock": 100},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        res_response = client.post(
            "/reservations",
            json={"sku": "SKU-010", "quantity": 20, "idempotency_key": "idem-005"},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        reservation_id = res_response.json()["id"]

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku"] == "SKU-010"
        assert data["quantity"] == 20

    def test_confirm_reservation_invalid_state(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-011", "initial_stock": 100},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        res_response = client.post(
            "/reservations",
            json={"sku": "SKU-011", "quantity": 20, "idempotency_key": "idem-006"},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        reservation_id = res_response.json()["id"]

        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert response.status_code == 400


class TestCancelReservation:
    def test_cancel_reservation_success(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-012", "initial_stock": 100},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        res_response = client.post(
            "/reservations",
            json={"sku": "SKU-012", "quantity": 15, "idempotency_key": "idem-007"},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        reservation_id = res_response.json()["id"]

        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "CANCELLED"

    def test_cancel_reservation_restores_stock(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-013", "initial_stock": 100},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        res_response = client.post(
            "/reservations",
            json={"sku": "SKU-013", "quantity": 25, "idempotency_key": "idem-008"},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        reservation_id = res_response.json()["id"]

        client.post(
            f"/reservations/{reservation_id}/cancel",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        res_response2 = client.post(
            "/reservations",
            json={"sku": "SKU-013", "quantity": 30, "idempotency_key": "idem-008b"},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert res_response2.status_code == 201


class TestOrders:
    def test_get_orders_empty(self, client):
        response = client.get(
            "/orders",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert len(data["items"]) == 0

    def test_get_orders_pagination(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-014", "initial_stock": 1000},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        for i in range(25):
            res_response = client.post(
                "/reservations",
                json={"sku": "SKU-014", "quantity": 10, "idempotency_key": f"idem-{2000 + i}"},
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            )
            reservation_id = res_response.json()["id"]
            client.post(
                f"/reservations/{reservation_id}/confirm",
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            )

        response1 = client.get(
            "/orders?page=1&size=10",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["total"] == 25
        assert data1["page"] == 1
        assert len(data1["items"]) == 10

        response2 = client.get(
            "/orders?page=2&size=10",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        data2 = response2.json()
        assert len(data2["items"]) == 10

        response3 = client.get(
            "/orders?page=3&size=10",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        data3 = response3.json()
        assert len(data3["items"]) == 5

    def test_get_orders_missing_auth(self, client):
        response = client.get("/orders")
        assert response.status_code == 403


class TestExpiredReservation:
    def test_confirm_expired_reservation(self, client, db_session):
        from datetime import datetime, timedelta
        from src.commerce_service.models import ReservationModel

        client.post(
            "/skus",
            json={"sku": "SKU-015", "initial_stock": 100},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        res_response = client.post(
            "/reservations",
            json={"sku": "SKU-015", "quantity": 20, "idempotency_key": "idem-009"},
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        reservation_id = res_response.json()["id"]

        reservation = db_session.query(ReservationModel).filter_by(id=reservation_id).first()
        reservation.created_at = datetime.utcnow() - timedelta(seconds=301)
        db_session.commit()

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )
        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()

        updated_reservation = db_session.query(ReservationModel).filter_by(id=reservation_id).first()
        assert updated_reservation.status == "EXPIRED"
