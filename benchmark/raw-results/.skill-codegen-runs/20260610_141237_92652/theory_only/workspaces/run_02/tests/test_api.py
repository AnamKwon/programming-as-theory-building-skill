import pytest
import tempfile
import os
from fastapi.testclient import TestClient
from src.commerce_service.app import app, repository, service
from src.commerce_service.repository import Repository
from src.commerce_service.service import CommerceService

API_KEY = "test-api-key-123"
INVALID_KEY = "invalid-key"


@pytest.fixture(autouse=True)
def setup_test_db():
    global repository, service
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    test_repo = Repository(db_path=db_path)
    test_service = CommerceService(test_repo)

    app.dependency_overrides[service.repository.__class__] = lambda: test_repo
    app.dependency_overrides[service.__class__] = lambda: test_service

    yield

    if os.path.exists(db_path):
        os.unlink(db_path)

    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


class TestHealth:
    def test_health_no_auth(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUManagement:
    def test_create_sku_with_valid_key(self, client):
        response = client.post(
            "/skus",
            json={"sku": "SKU-API-001", "initial_stock": 100},
            headers={"x-api-key": API_KEY}
        )
        assert response.status_code == 201
        data = response.json()
        assert data['sku'] == "SKU-API-001"
        assert data['available_stock'] == 100

    def test_create_sku_without_key(self, client):
        response = client.post(
            "/skus",
            json={"sku": "SKU-API-002", "initial_stock": 100}
        )
        assert response.status_code == 401

    def test_create_sku_with_invalid_key(self, client):
        response = client.post(
            "/skus",
            json={"sku": "SKU-API-003", "initial_stock": 100},
            headers={"x-api-key": INVALID_KEY}
        )
        assert response.status_code == 401

    def test_adjust_stock_with_valid_key(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-API-004", "initial_stock": 100},
            headers={"x-api-key": API_KEY}
        )

        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU-API-004", "amount": 25},
            headers={"x-api-key": API_KEY}
        )
        assert response.status_code == 200
        assert response.json()['available_stock'] == 125

    def test_adjust_stock_without_key(self, client):
        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU-API-005", "amount": 25}
        )
        assert response.status_code == 401


class TestReservations:
    def test_create_reservation_success(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-API-006", "initial_stock": 100},
            headers={"x-api-key": API_KEY}
        )

        response = client.post(
            "/reservations",
            json={"sku": "SKU-API-006", "quantity": 30, "idempotency_key": "key-001"},
            headers={"x-api-key": API_KEY}
        )
        assert response.status_code == 201
        data = response.json()
        assert data['status'] == 'PENDING'
        assert data['quantity'] == 30

    def test_create_reservation_insufficient_stock(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-API-007", "initial_stock": 50},
            headers={"x-api-key": API_KEY}
        )

        response = client.post(
            "/reservations",
            json={"sku": "SKU-API-007", "quantity": 100, "idempotency_key": "key-002"},
            headers={"x-api-key": API_KEY}
        )
        assert response.status_code == 400
        assert response.json()['detail'] == "Insufficient stock"

    def test_create_reservation_without_key(self, client):
        response = client.post(
            "/reservations",
            json={"sku": "SKU-API-008", "quantity": 10, "idempotency_key": "key-003"}
        )
        assert response.status_code == 401

    def test_idempotent_reservation_retry(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-API-009", "initial_stock": 100},
            headers={"x-api-key": API_KEY}
        )

        response1 = client.post(
            "/reservations",
            json={"sku": "SKU-API-009", "quantity": 20, "idempotency_key": "key-004"},
            headers={"x-api-key": API_KEY}
        )
        res_id_1 = response1.json()['id']

        response2 = client.post(
            "/reservations",
            json={"sku": "SKU-API-009", "quantity": 20, "idempotency_key": "key-004"},
            headers={"x-api-key": API_KEY}
        )
        res_id_2 = response2.json()['id']

        assert response2.status_code == 201
        assert res_id_1 == res_id_2

        sku_response = client.post(
            "/stock/adjust",
            json={"sku": "SKU-API-009", "amount": 0},
            headers={"x-api-key": API_KEY}
        )
        sku_data = sku_response.json()
        assert sku_data['available_stock'] == 80


class TestReservationConfirmation:
    def test_confirm_reservation_success(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-API-010", "initial_stock": 100},
            headers={"x-api-key": API_KEY}
        )

        res_resp = client.post(
            "/reservations",
            json={"sku": "SKU-API-010", "quantity": 25, "idempotency_key": "key-005"},
            headers={"x-api-key": API_KEY}
        )
        res_id = res_resp.json()['id']

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"x-api-key": API_KEY}
        )
        assert response.status_code == 200
        data = response.json()
        assert data['id'] is not None
        assert data['reservation_id'] == res_id

    def test_confirm_reservation_without_key(self, client):
        response = client.post(
            "/reservations/999/confirm"
        )
        assert response.status_code == 401

    def test_confirm_nonpending_reservation(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-API-011", "initial_stock": 100},
            headers={"x-api-key": API_KEY}
        )

        res_resp = client.post(
            "/reservations",
            json={"sku": "SKU-API-011", "quantity": 15, "idempotency_key": "key-006"},
            headers={"x-api-key": API_KEY}
        )
        res_id = res_resp.json()['id']

        client.post(
            f"/reservations/{res_id}/confirm",
            headers={"x-api-key": API_KEY}
        )

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"x-api-key": API_KEY}
        )
        assert response.status_code == 400


class TestReservationCancellation:
    def test_cancel_reservation_success(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-API-012", "initial_stock": 100},
            headers={"x-api-key": API_KEY}
        )

        res_resp = client.post(
            "/reservations",
            json={"sku": "SKU-API-012", "quantity": 35, "idempotency_key": "key-007"},
            headers={"x-api-key": API_KEY}
        )
        res_id = res_resp.json()['id']

        response = client.post(
            f"/reservations/{res_id}/cancel",
            headers={"x-api-key": API_KEY}
        )
        assert response.status_code == 200
        assert response.json()['status'] == 'CANCELLED'

    def test_cancel_reservation_without_key(self, client):
        response = client.post(
            "/reservations/999/cancel"
        )
        assert response.status_code == 401


class TestOrders:
    def test_get_orders_pagination(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-API-013", "initial_stock": 500},
            headers={"x-api-key": API_KEY}
        )

        for i in range(5):
            res_resp = client.post(
                "/reservations",
                json={"sku": "SKU-API-013", "quantity": 10, "idempotency_key": f"key-order-{i}"},
                headers={"x-api-key": API_KEY}
            )
            res_id = res_resp.json()['id']
            client.post(
                f"/reservations/{res_id}/confirm",
                headers={"x-api-key": API_KEY}
            )

        response = client.get("/orders?page=1&size=10")
        assert response.status_code == 200
        data = response.json()
        assert data['total'] == 5
        assert len(data['orders']) == 5
        assert data['page'] == 1

    def test_get_orders_no_auth_required(self, client):
        response = client.get("/orders")
        assert response.status_code == 200

    def test_get_orders_pagination_offset(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-API-014", "initial_stock": 1000},
            headers={"x-api-key": API_KEY}
        )

        for i in range(25):
            res_resp = client.post(
                "/reservations",
                json={"sku": "SKU-API-014", "quantity": 5, "idempotency_key": f"key-offset-{i}"},
                headers={"x-api-key": API_KEY}
            )
            res_id = res_resp.json()['id']
            client.post(
                f"/reservations/{res_id}/confirm",
                headers={"x-api-key": API_KEY}
            )

        page1 = client.get("/orders?page=1&size=10")
        page2 = client.get("/orders?page=2&size=10")
        page3 = client.get("/orders?page=3&size=10")

        data1 = page1.json()
        data2 = page2.json()
        data3 = page3.json()

        assert len(data1['orders']) == 10
        assert len(data2['orders']) == 10
        assert len(data3['orders']) == 5
        assert data1['total'] == 25


class TestExpiredReservation:
    def test_expired_reservation_returns_400(self, client):
        import sqlite3
        from datetime import datetime, timedelta

        client.post(
            "/skus",
            json={"sku": "SKU-API-015", "initial_stock": 100},
            headers={"x-api-key": API_KEY}
        )

        res_resp = client.post(
            "/reservations",
            json={"sku": "SKU-API-015", "quantity": 30, "idempotency_key": "key-expire"},
            headers={"x-api-key": API_KEY}
        )
        res_id = res_resp.json()['id']

        conn = sqlite3.connect("commerce.db")
        cursor = conn.cursor()
        old_time = (datetime.utcnow() - timedelta(seconds=310)).isoformat()
        cursor.execute(
            'UPDATE reservations SET created_at = ? WHERE id = ?',
            (old_time, res_id)
        )
        conn.commit()
        conn.close()

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"x-api-key": API_KEY}
        )
        assert response.status_code == 400
        assert response.json()['detail'] == "Reservation expired"
