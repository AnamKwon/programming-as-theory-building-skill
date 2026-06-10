import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.commerce_service.app import app
from src.commerce_service.repository import Base, SessionLocal, engine


@pytest.fixture(autouse=True)
def setup_database():
    """Create fresh database for each test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


API_KEY = "test-api-key"


class TestHealthCheck:
    def test_health_check(self, client: TestClient):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestSKUEndpoints:
    def test_create_sku_success(self, client: TestClient):
        response = client.post(
            "/skus",
            json={
                "sku_id": "SKU001",
                "name": "Test Product",
                "initial_stock": 100,
            },
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku_id"] == "SKU001"
        assert data["stock"] == 100

    def test_create_sku_missing_api_key(self, client: TestClient):
        response = client.post(
            "/skus",
            json={
                "sku_id": "SKU002",
                "name": "Test Product 2",
                "initial_stock": 50,
            },
        )
        assert response.status_code == 403

    def test_adjust_stock_success(self, client: TestClient):
        client.post(
            "/skus",
            json={"sku_id": "SKU003", "name": "Product", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        response = client.post(
            "/skus/SKU003/stock",
            json={"delta": 25},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["stock"] == 125

    def test_adjust_stock_sku_not_found(self, client: TestClient):
        response = client.post(
            "/skus/MISSING/stock",
            json={"delta": 10},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 404


class TestReservationEndpoints:
    def test_create_reservation_success(self, client: TestClient):
        client.post(
            "/skus",
            json={"sku_id": "SKU004", "name": "Product", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        response = client.post(
            "/reservations",
            json={
                "sku_id": "SKU004",
                "quantity": 20,
                "idempotency_key": "unique-key-1",
            },
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "pending"
        assert data["quantity"] == 20

    def test_create_reservation_idempotent(self, client: TestClient):
        client.post(
            "/skus",
            json={"sku_id": "SKU005", "name": "Product", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        response1 = client.post(
            "/reservations",
            json={
                "sku_id": "SKU005",
                "quantity": 20,
                "idempotency_key": "unique-key-2",
            },
            headers={"X-API-Key": API_KEY},
        )
        response2 = client.post(
            "/reservations",
            json={
                "sku_id": "SKU005",
                "quantity": 30,
                "idempotency_key": "unique-key-2",
            },
            headers={"X-API-Key": API_KEY},
        )
        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response1.json()["reservation_id"] == response2.json()["reservation_id"]

    def test_create_reservation_insufficient_stock(self, client: TestClient):
        client.post(
            "/skus",
            json={"sku_id": "SKU006", "name": "Product", "initial_stock": 10},
            headers={"X-API-Key": API_KEY},
        )
        response = client.post(
            "/reservations",
            json={
                "sku_id": "SKU006",
                "quantity": 20,
                "idempotency_key": "unique-key-3",
            },
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 409
        assert "Insufficient stock" in response.json()["detail"]

    def test_confirm_reservation_success(self, client: TestClient):
        client.post(
            "/skus",
            json={"sku_id": "SKU007", "name": "Product", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        res = client.post(
            "/reservations",
            json={
                "sku_id": "SKU007",
                "quantity": 30,
                "idempotency_key": "unique-key-4",
            },
            headers={"X-API-Key": API_KEY},
        )
        reservation_id = res.json()["reservation_id"]
        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            json={"idempotency_key": "unique-key-4"},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["state"] == "confirmed"

    def test_confirm_reservation_unauthorized(self, client: TestClient):
        client.post(
            "/skus",
            json={"sku_id": "SKU008", "name": "Product", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        res = client.post(
            "/reservations",
            json={
                "sku_id": "SKU008",
                "quantity": 20,
                "idempotency_key": "unique-key-5",
            },
            headers={"X-API-Key": API_KEY},
        )
        reservation_id = res.json()["reservation_id"]
        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            json={"idempotency_key": "unique-key-5"},
        )
        assert response.status_code == 403

    def test_cancel_reservation_success(self, client: TestClient):
        client.post(
            "/skus",
            json={"sku_id": "SKU009", "name": "Product", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        res = client.post(
            "/reservations",
            json={
                "sku_id": "SKU009",
                "quantity": 20,
                "idempotency_key": "unique-key-6",
            },
            headers={"X-API-Key": API_KEY},
        )
        reservation_id = res.json()["reservation_id"]
        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            json={"idempotency_key": "unique-key-6"},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["state"] == "cancelled"


class TestOrderEndpoints:
    def test_create_order_success(self, client: TestClient):
        client.post(
            "/skus",
            json={"sku_id": "SKU010", "name": "Product", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        res = client.post(
            "/reservations",
            json={
                "sku_id": "SKU010",
                "quantity": 20,
                "idempotency_key": "unique-key-7",
            },
            headers={"X-API-Key": API_KEY},
        )
        reservation_id = res.json()["reservation_id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            json={"idempotency_key": "unique-key-7"},
            headers={"X-API-Key": API_KEY},
        )
        response = client.post(
            "/orders",
            json={
                "reservation_id": reservation_id,
                "idempotency_key": "order-key-1",
            },
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        assert response.json()["state"] == "pending"

    def test_create_order_unauthorized(self, client: TestClient):
        client.post(
            "/skus",
            json={"sku_id": "SKU011", "name": "Product", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        res = client.post(
            "/reservations",
            json={
                "sku_id": "SKU011",
                "quantity": 20,
                "idempotency_key": "unique-key-8",
            },
            headers={"X-API-Key": API_KEY},
        )
        reservation_id = res.json()["reservation_id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            json={"idempotency_key": "unique-key-8"},
            headers={"X-API-Key": API_KEY},
        )
        response = client.post(
            "/orders",
            json={
                "reservation_id": reservation_id,
                "idempotency_key": "order-key-2",
            },
        )
        assert response.status_code == 403

    def test_get_order_success(self, client: TestClient):
        client.post(
            "/skus",
            json={"sku_id": "SKU012", "name": "Product", "initial_stock": 100},
            headers={"X-API-Key": API_KEY},
        )
        res = client.post(
            "/reservations",
            json={
                "sku_id": "SKU012",
                "quantity": 20,
                "idempotency_key": "unique-key-9",
            },
            headers={"X-API-Key": API_KEY},
        )
        reservation_id = res.json()["reservation_id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            json={"idempotency_key": "unique-key-9"},
            headers={"X-API-Key": API_KEY},
        )
        order = client.post(
            "/orders",
            json={
                "reservation_id": reservation_id,
                "idempotency_key": "order-key-3",
            },
            headers={"X-API-Key": API_KEY},
        )
        order_id = order.json()["order_id"]
        response = client.get(f"/orders/{order_id}")
        assert response.status_code == 200
        assert response.json()["order_id"] == order_id

    def test_list_orders_pagination(self, client: TestClient):
        client.post(
            "/skus",
            json={"sku_id": "SKU013", "name": "Product", "initial_stock": 500},
            headers={"X-API-Key": API_KEY},
        )
        for i in range(15):
            res = client.post(
                "/reservations",
                json={
                    "sku_id": "SKU013",
                    "quantity": 10,
                    "idempotency_key": f"unique-key-{200+i}",
                },
                headers={"X-API-Key": API_KEY},
            )
            reservation_id = res.json()["reservation_id"]
            client.post(
                f"/reservations/{reservation_id}/confirm",
                json={"idempotency_key": f"unique-key-{200+i}"},
                headers={"X-API-Key": API_KEY},
            )
            client.post(
                "/orders",
                json={
                    "reservation_id": reservation_id,
                    "idempotency_key": f"order-key-{200+i}",
                },
                headers={"X-API-Key": API_KEY},
            )

        response = client.get("/orders?limit=10&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 10
        assert data["total"] == 15
        assert data["limit"] == 10
        assert data["offset"] == 0

        response = client.get("/orders?limit=10&offset=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 5
