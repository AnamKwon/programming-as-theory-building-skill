import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.app import app, get_db
from src.commerce_service.models import Base

API_KEY = "test-key-123"


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


@pytest.fixture
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


@pytest.fixture
def sku(client):
    response = client.post(
        "/skus",
        json={
            "code": "SKU-001",
            "name": "Test Product",
            "initial_stock": 100,
        },
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    return response.json()


class TestHealth:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    def test_create_sku_requires_auth(self, client):
        response = client.post(
            "/skus",
            json={
                "code": "SKU-001",
                "name": "Product",
                "initial_stock": 100,
            },
        )
        assert response.status_code == 403

    def test_create_sku_success(self, client):
        response = client.post(
            "/skus",
            json={
                "code": "SKU-001",
                "name": "Test Product",
                "initial_stock": 100,
            },
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "SKU-001"
        assert data["name"] == "Test Product"
        assert data["available_stock"] == 100

    def test_create_duplicate_sku_code_fails(self, client):
        client.post(
            "/skus",
            json={
                "code": "SKU-001",
                "name": "Product",
                "initial_stock": 100,
            },
            headers={"X-API-Key": API_KEY},
        )

        response = client.post(
            "/skus",
            json={
                "code": "SKU-001",
                "name": "Different Product",
                "initial_stock": 50,
            },
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 409

    def test_adjust_stock(self, client, sku):
        sku_id = sku["id"]
        response = client.post(
            f"/skus/{sku_id}/stock/adjust",
            json={"amount": 50},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["available_stock"] == 150

    def test_adjust_stock_negative(self, client, sku):
        sku_id = sku["id"]
        response = client.post(
            f"/skus/{sku_id}/stock/adjust",
            json={"amount": -30},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["available_stock"] == 70


class TestReservationEndpoints:
    def test_create_reservation_requires_auth(self, client, sku):
        response = client.post(
            "/reservations",
            json={
                "sku_id": sku["id"],
                "amount": 10,
                "idempotency_key": "key-1",
            },
        )
        assert response.status_code == 403

    def test_create_reservation_success(self, client, sku):
        response = client.post(
            "/reservations",
            json={
                "sku_id": sku["id"],
                "amount": 50,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku_id"] == sku["id"]
        assert data["amount"] == 50
        assert data["status"] == "pending"

    def test_create_reservation_insufficient_stock(self, client, sku):
        response = client.post(
            "/reservations",
            json={
                "sku_id": sku["id"],
                "amount": 150,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_create_reservation_idempotent(self, client, sku):
        response1 = client.post(
            "/reservations",
            json={
                "sku_id": sku["id"],
                "amount": 50,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": API_KEY},
        )
        assert response1.status_code == 200
        reservation_id = response1.json()["id"]

        response2 = client.post(
            "/reservations",
            json={
                "sku_id": sku["id"],
                "amount": 50,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": API_KEY},
        )
        assert response2.status_code == 200
        assert response2.json()["id"] == reservation_id

    def test_confirm_reservation_success(self, client, sku):
        res = client.post(
            "/reservations",
            json={
                "sku_id": sku["id"],
                "amount": 50,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": API_KEY},
        )
        reservation_id = res.json()["id"]

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            json={},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "confirmed"

    def test_confirm_nonexistent_reservation(self, client):
        response = client.post(
            "/reservations/999/confirm",
            json={},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 404

    def test_cancel_reservation_success(self, client, sku):
        res = client.post(
            "/reservations",
            json={
                "sku_id": sku["id"],
                "amount": 50,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": API_KEY},
        )
        reservation_id = res.json()["id"]

        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            json={},
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"


class TestOrderEndpoints:
    def test_list_orders_requires_auth(self, client):
        response = client.get("/orders")
        assert response.status_code == 403

    def test_list_orders_empty(self, client):
        response = client.get("/orders", headers={"X-API-Key": API_KEY})
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_orders_with_pagination(self, client, sku):
        for i in range(15):
            client.post(
                "/reservations",
                json={
                    "sku_id": sku["id"],
                    "amount": 10,
                    "idempotency_key": f"key-{i}",
                },
                headers={"X-API-Key": API_KEY},
            )

        response = client.get(
            "/orders?page=1&page_size=10",
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["total"] == 15
        assert data["total_pages"] == 2

        response = client.get(
            "/orders?page=2&page_size=10",
            headers={"X-API-Key": API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5


class TestIntegrationFlow:
    def test_end_to_end_reservation_flow(self, client):
        sku_res = client.post(
            "/skus",
            json={
                "code": "WIDGET-A",
                "name": "Awesome Widget",
                "initial_stock": 50,
            },
            headers={"X-API-Key": API_KEY},
        )
        sku_id = sku_res.json()["id"]

        res_res = client.post(
            "/reservations",
            json={
                "sku_id": sku_id,
                "amount": 20,
                "idempotency_key": "order-123",
            },
            headers={"X-API-Key": API_KEY},
        )
        assert res_res.status_code == 200
        reservation_id = res_res.json()["id"]

        confirm_res = client.post(
            f"/reservations/{reservation_id}/confirm",
            json={},
            headers={"X-API-Key": API_KEY},
        )
        assert confirm_res.status_code == 200

        orders_res = client.get(
            "/orders",
            headers={"X-API-Key": API_KEY},
        )
        assert orders_res.status_code == 200
        orders = orders_res.json()["items"]
        assert len(orders) == 1
        assert orders[0]["amount"] == 20
        assert orders[0]["status"] == "confirmed"
