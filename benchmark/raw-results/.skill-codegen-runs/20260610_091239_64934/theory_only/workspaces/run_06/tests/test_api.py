import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.app import app, get_db
from src.commerce_service.models import Base


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


@pytest.fixture
def api_headers():
    return {"Authorization": "Bearer test-key"}


class TestHealthCheck:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    def test_create_sku(self, client, api_headers):
        response = client.post(
            "/skus",
            json={"sku": "TEST-001", "name": "Test Product", "initial_stock": 100},
            headers=api_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku"] == "TEST-001"
        assert data["name"] == "Test Product"
        assert data["total_stock"] == 100
        assert data["available_stock"] == 100

    def test_create_sku_unauthorized(self, client):
        response = client.post(
            "/skus",
            json={"sku": "TEST-001", "name": "Test Product", "initial_stock": 100},
        )
        assert response.status_code == 403

    def test_create_sku_invalid_key(self, client):
        response = client.post(
            "/skus",
            json={"sku": "TEST-001", "name": "Test Product", "initial_stock": 100},
            headers={"Authorization": "Bearer invalid-key"},
        )
        assert response.status_code == 401


class TestStockAdjustment:
    def test_adjust_stock_increase(self, client, api_headers):
        client.post(
            "/skus",
            json={"sku": "TEST-001", "name": "Test Product", "initial_stock": 100},
            headers=api_headers,
        )
        response = client.post(
            "/stock/adjust",
            json={"sku": "TEST-001", "quantity": 50},
            headers=api_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_stock"] == 150

    def test_adjust_stock_decrease(self, client, api_headers):
        client.post(
            "/skus",
            json={"sku": "TEST-001", "name": "Test Product", "initial_stock": 100},
            headers=api_headers,
        )
        response = client.post(
            "/stock/adjust",
            json={"sku": "TEST-001", "quantity": -30},
            headers=api_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_stock"] == 70

    def test_adjust_stock_below_zero_fails(self, client, api_headers):
        client.post(
            "/skus",
            json={"sku": "TEST-001", "name": "Test Product", "initial_stock": 100},
            headers=api_headers,
        )
        response = client.post(
            "/stock/adjust",
            json={"sku": "TEST-001", "quantity": -150},
            headers=api_headers,
        )
        assert response.status_code == 400


class TestReservationEndpoints:
    def test_create_reservation(self, client, api_headers):
        client.post(
            "/skus",
            json={"sku": "TEST-001", "name": "Test Product", "initial_stock": 100},
            headers=api_headers,
        )
        response = client.post(
            "/reservations",
            json={"sku": "TEST-001", "quantity": 50, "idempotency_key": "key-1"},
            headers=api_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku"] == "TEST-001"
        assert data["quantity"] == 50
        assert data["status"] == "pending"

    def test_create_reservation_insufficient_stock(self, client, api_headers):
        client.post(
            "/skus",
            json={"sku": "TEST-001", "name": "Test Product", "initial_stock": 30},
            headers=api_headers,
        )
        response = client.post(
            "/reservations",
            json={"sku": "TEST-001", "quantity": 50, "idempotency_key": "key-1"},
            headers=api_headers,
        )
        assert response.status_code == 409

    def test_create_reservation_idempotent(self, client, api_headers):
        client.post(
            "/skus",
            json={"sku": "TEST-001", "name": "Test Product", "initial_stock": 100},
            headers=api_headers,
        )
        res1 = client.post(
            "/reservations",
            json={"sku": "TEST-001", "quantity": 50, "idempotency_key": "key-1"},
            headers=api_headers,
        )
        res2 = client.post(
            "/reservations",
            json={"sku": "TEST-001", "quantity": 50, "idempotency_key": "key-1"},
            headers=api_headers,
        )
        assert res1.status_code == 200
        assert res2.status_code == 200
        assert res1.json()["reservation_id"] == res2.json()["reservation_id"]

    def test_cancel_reservation(self, client, api_headers):
        client.post(
            "/skus",
            json={"sku": "TEST-001", "name": "Test Product", "initial_stock": 100},
            headers=api_headers,
        )
        res = client.post(
            "/reservations",
            json={"sku": "TEST-001", "quantity": 50, "idempotency_key": "key-1"},
            headers=api_headers,
        )
        reservation_id = res.json()["reservation_id"]
        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            headers=api_headers,
        )
        assert response.status_code == 200

    def test_cancel_nonexistent_reservation(self, client, api_headers):
        response = client.post(
            "/reservations/nonexistent-id/cancel",
            headers=api_headers,
        )
        assert response.status_code == 404


class TestOrderEndpoints:
    def test_confirm_reservation(self, client, api_headers):
        client.post(
            "/skus",
            json={"sku": "TEST-001", "name": "Test Product", "initial_stock": 100},
            headers=api_headers,
        )
        res = client.post(
            "/reservations",
            json={"sku": "TEST-001", "quantity": 50, "idempotency_key": "key-1"},
            headers=api_headers,
        )
        reservation_id = res.json()["reservation_id"]
        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            json={"idempotency_key": "key-1"},
            headers=api_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku"] == "TEST-001"
        assert data["quantity"] == 50

    def test_confirm_reservation_idempotent(self, client, api_headers):
        client.post(
            "/skus",
            json={"sku": "TEST-001", "name": "Test Product", "initial_stock": 100},
            headers=api_headers,
        )
        res = client.post(
            "/reservations",
            json={"sku": "TEST-001", "quantity": 50, "idempotency_key": "key-1"},
            headers=api_headers,
        )
        reservation_id = res.json()["reservation_id"]
        order1 = client.post(
            f"/reservations/{reservation_id}/confirm",
            json={"idempotency_key": "key-1"},
            headers=api_headers,
        )
        order2 = client.post(
            f"/reservations/{reservation_id}/confirm",
            json={"idempotency_key": "key-1"},
            headers=api_headers,
        )
        assert order1.status_code == 200
        assert order2.status_code == 200
        assert order1.json()["order_id"] == order2.json()["order_id"]

    def test_get_order(self, client, api_headers):
        client.post(
            "/skus",
            json={"sku": "TEST-001", "name": "Test Product", "initial_stock": 100},
            headers=api_headers,
        )
        res = client.post(
            "/reservations",
            json={"sku": "TEST-001", "quantity": 50, "idempotency_key": "key-1"},
            headers=api_headers,
        )
        reservation_id = res.json()["reservation_id"]
        order = client.post(
            f"/reservations/{reservation_id}/confirm",
            json={"idempotency_key": "key-1"},
            headers=api_headers,
        )
        order_id = order.json()["order_id"]
        response = client.get(f"/orders/{order_id}", headers=api_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["order_id"] == order_id

    def test_list_orders_pagination(self, client, api_headers):
        client.post(
            "/skus",
            json={"sku": "TEST-001", "name": "Test Product", "initial_stock": 1000},
            headers=api_headers,
        )
        for i in range(15):
            res = client.post(
                "/reservations",
                json={"sku": "TEST-001", "quantity": 10, "idempotency_key": f"key-{i}"},
                headers=api_headers,
            )
            reservation_id = res.json()["reservation_id"]
            client.post(
                f"/reservations/{reservation_id}/confirm",
                json={"idempotency_key": f"key-{i}"},
                headers=api_headers,
            )

        response1 = client.get("/orders?page=1&page_size=10", headers=api_headers)
        assert response1.status_code == 200
        data1 = response1.json()
        assert len(data1["orders"]) == 10
        assert data1["total"] == 15
        assert data1["page"] == 1

        response2 = client.get("/orders?page=2&page_size=10", headers=api_headers)
        assert response2.status_code == 200
        data2 = response2.json()
        assert len(data2["orders"]) == 5
        assert data2["total"] == 15
        assert data2["page"] == 2

    def test_get_nonexistent_order(self, client, api_headers):
        response = client.get("/orders/nonexistent-id", headers=api_headers)
        assert response.status_code == 404


class TestUnauthorizedAccess:
    def test_mutations_require_api_key(self, client):
        endpoints = [
            ("POST", "/skus", {"sku": "TEST-001", "name": "Test", "initial_stock": 100}),
            ("POST", "/stock/adjust", {"sku": "TEST-001", "quantity": 10}),
            ("POST", "/reservations", {"sku": "TEST-001", "quantity": 10, "idempotency_key": "key"}),
        ]
        for method, path, json_data in endpoints:
            response = client.request(method, path, json=json_data)
            assert response.status_code in (401, 403)

    def test_queries_require_api_key(self, client, api_headers):
        client.post(
            "/skus",
            json={"sku": "TEST-001", "name": "Test Product", "initial_stock": 100},
            headers=api_headers,
        )
        response = client.get("/orders")
        assert response.status_code in (401, 403)
