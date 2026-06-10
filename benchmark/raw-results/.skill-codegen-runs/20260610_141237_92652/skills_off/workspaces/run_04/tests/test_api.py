import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.app import app, get_db
from src.commerce_service.models import Base


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client(test_db):
    return TestClient(app)


API_KEY = "test-key-123"
HEADERS = {"X-API-Key": API_KEY}


class TestHealth:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    def test_create_sku_success(self, client):
        response = client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=HEADERS,
        )
        assert response.status_code == 201
        assert response.json()["sku"] == "SKU-001"
        assert response.json()["stock"] == 100

    def test_create_sku_missing_api_key(self, client):
        response = client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
        )
        assert response.status_code == 403

    def test_create_sku_invalid_api_key(self, client):
        response = client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 401

    def test_adjust_stock_success(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=HEADERS,
        )
        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU-001", "amount": 50},
            headers=HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["stock"] == 150

    def test_adjust_stock_missing_api_key(self, client):
        response = client.post(
            "/stock/adjust",
            json={"sku": "SKU-001", "amount": 50},
        )
        assert response.status_code == 403


class TestReservationEndpoints:
    def test_create_reservation_success(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=HEADERS,
        )
        response = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "key-1"},
            headers=HEADERS,
        )
        assert response.status_code == 201
        assert response.json()["sku"] == "SKU-001"
        assert response.json()["quantity"] == 30
        assert response.json()["status"] == "PENDING"

    def test_create_reservation_insufficient_stock(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 20},
            headers=HEADERS,
        )
        response = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "key-1"},
            headers=HEADERS,
        )
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_create_reservation_missing_api_key(self, client):
        response = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "key-1"},
        )
        assert response.status_code == 403

    def test_idempotent_reservation_returns_same_data(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=HEADERS,
        )
        response1 = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "key-1"},
            headers=HEADERS,
        )
        response2 = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "key-1"},
            headers=HEADERS,
        )
        assert response1.json()["id"] == response2.json()["id"]
        assert response1.json()["quantity"] == response2.json()["quantity"]

    def test_idempotent_reservation_no_double_deduction(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=HEADERS,
        )
        client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "key-1"},
            headers=HEADERS,
        )

        stock_after_first = client.post(
            "/stock/adjust",
            json={"sku": "SKU-001", "amount": 0},
            headers=HEADERS,
        ).json()["stock"]

        client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "key-1"},
            headers=HEADERS,
        )

        stock_after_second = client.post(
            "/stock/adjust",
            json={"sku": "SKU-001", "amount": 0},
            headers=HEADERS,
        ).json()["stock"]

        assert stock_after_first == stock_after_second

    def test_confirm_reservation_success(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=HEADERS,
        )
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "key-1"},
            headers=HEADERS,
        )
        res_id = res_response.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers=HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "CONFIRMED"

    def test_confirm_creates_order(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=HEADERS,
        )
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "key-1"},
            headers=HEADERS,
        )
        res_id = res_response.json()["id"]

        client.post(f"/reservations/{res_id}/confirm", headers=HEADERS)

        orders_response = client.get("/orders")
        assert orders_response.status_code == 200
        assert len(orders_response.json()["orders"]) == 1

    def test_confirm_missing_api_key(self, client):
        response = client.post("/reservations/1/confirm")
        assert response.status_code == 403

    def test_cancel_reservation_success(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=HEADERS,
        )
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "key-1"},
            headers=HEADERS,
        )
        res_id = res_response.json()["id"]

        response = client.post(
            f"/reservations/{res_id}/cancel",
            headers=HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "CANCELLED"

    def test_cancel_restores_stock(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 100},
            headers=HEADERS,
        )
        res_response = client.post(
            "/reservations",
            json={"sku": "SKU-001", "quantity": 30, "idempotency_key": "key-1"},
            headers=HEADERS,
        )
        res_id = res_response.json()["id"]

        stock_before_cancel = client.post(
            "/stock/adjust",
            json={"sku": "SKU-001", "amount": 0},
            headers=HEADERS,
        ).json()["stock"]

        assert stock_before_cancel == 70

        client.post(f"/reservations/{res_id}/cancel", headers=HEADERS)

        stock_after_cancel = client.post(
            "/stock/adjust",
            json={"sku": "SKU-001", "amount": 0},
            headers=HEADERS,
        ).json()["stock"]

        assert stock_after_cancel == 100

    def test_cancel_missing_api_key(self, client):
        response = client.post("/reservations/1/cancel")
        assert response.status_code == 403


class TestOrderEndpoints:
    def test_get_orders_pagination_default(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 200},
            headers=HEADERS,
        )
        for i in range(5):
            res_response = client.post(
                "/reservations",
                json={"sku": "SKU-001", "quantity": 10, "idempotency_key": f"key-{i}"},
                headers=HEADERS,
            )
            res_id = res_response.json()["id"]
            client.post(f"/reservations/{res_id}/confirm", headers=HEADERS)

        response = client.get("/orders")
        assert response.status_code == 200
        assert response.json()["total"] == 5
        assert len(response.json()["orders"]) == 5

    def test_get_orders_pagination_offset(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "initial_stock": 500},
            headers=HEADERS,
        )
        for i in range(15):
            res_response = client.post(
                "/reservations",
                json={"sku": "SKU-001", "quantity": 10, "idempotency_key": f"key-{i}"},
                headers=HEADERS,
            )
            res_id = res_response.json()["id"]
            client.post(f"/reservations/{res_id}/confirm", headers=HEADERS)

        response_page1 = client.get("/orders?page=1&size=10")
        response_page2 = client.get("/orders?page=2&size=10")

        assert len(response_page1.json()["orders"]) == 10
        assert len(response_page2.json()["orders"]) == 5
        assert response_page1.json()["orders"][0]["id"] != response_page2.json()["orders"][0]["id"]

    def test_get_orders_no_auth_required(self, client):
        response = client.get("/orders")
        assert response.status_code == 200
