import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from commerce_service.app import app, get_db
from commerce_service.models import Base
from commerce_service.repository import Repository, get_session_factory


@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = get_session_factory(engine)
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
def client(test_db: Session):
    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def api_key():
    return "test-api-key-123"


def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    def test_create_sku_unauthorized(self, client: TestClient):
        response = client.post(
            "/skus",
            json={"id": "sku-001", "name": "Widget A"},
        )
        assert response.status_code == 401

    def test_create_sku_invalid_key(self, client: TestClient):
        response = client.post(
            "/skus",
            json={"id": "sku-001", "name": "Widget A"},
            headers={"X-API-Key": "invalid-key"},
        )
        assert response.status_code == 403

    def test_create_sku_success(self, client: TestClient, api_key: str):
        response = client.post(
            "/skus",
            json={"id": "sku-001", "name": "Widget A"},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "sku-001"
        assert data["name"] == "Widget A"

    def test_create_duplicate_sku_fails(self, client: TestClient, api_key: str):
        client.post(
            "/skus",
            json={"id": "sku-001", "name": "Widget A"},
            headers={"X-API-Key": api_key},
        )
        response = client.post(
            "/skus",
            json={"id": "sku-001", "name": "Widget B"},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 409

    def test_adjust_stock_success(self, client: TestClient, api_key: str):
        client.post(
            "/skus",
            json={"id": "sku-001", "name": "Widget A"},
            headers={"X-API-Key": api_key},
        )
        response = client.post(
            "/skus/sku-001/stock",
            json={"quantity": 100},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["quantity"] == 100
        assert data["reserved"] == 0
        assert data["available"] == 100

    def test_adjust_stock_nonexistent_sku(self, client: TestClient, api_key: str):
        response = client.post(
            "/skus/sku-invalid/stock",
            json={"quantity": 100},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 404


class TestReservationEndpoints:
    @pytest.fixture
    def sku_with_stock(self, client: TestClient, api_key: str):
        client.post(
            "/skus",
            json={"id": "sku-001", "name": "Widget A"},
            headers={"X-API-Key": api_key},
        )
        client.post(
            "/skus/sku-001/stock",
            json={"quantity": 1000},
            headers={"X-API-Key": api_key},
        )
        return "sku-001"

    def test_create_reservation_success(self, client: TestClient, api_key: str, sku_with_stock: str):
        response = client.post(
            "/reservations",
            json={
                "sku_id": sku_with_stock,
                "quantity": 10,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 201
        data = response.json()
        assert "reservation_id" in data
        assert "order_id" in data
        assert data["quantity"] == 10
        assert data["status"] == "pending"

    def test_create_reservation_insufficient_stock(
        self, client: TestClient, api_key: str, sku_with_stock: str
    ):
        response = client.post(
            "/reservations",
            json={
                "sku_id": sku_with_stock,
                "quantity": 2000,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]

    def test_create_reservation_idempotency(
        self, client: TestClient, api_key: str, sku_with_stock: str
    ):
        resp1 = client.post(
            "/reservations",
            json={
                "sku_id": sku_with_stock,
                "quantity": 10,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": api_key},
        )
        resp2 = client.post(
            "/reservations",
            json={
                "sku_id": sku_with_stock,
                "quantity": 20,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": api_key},
        )
        assert resp1.status_code == 201
        assert resp2.status_code == 201
        data1 = resp1.json()
        data2 = resp2.json()
        assert data1["reservation_id"] == data2["reservation_id"]
        assert data1["order_id"] == data2["order_id"]

    def test_confirm_reservation_success(
        self, client: TestClient, api_key: str, sku_with_stock: str
    ):
        res_resp = client.post(
            "/reservations",
            json={
                "sku_id": sku_with_stock,
                "quantity": 10,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": api_key},
        )
        res_id = res_resp.json()["reservation_id"]

        conf_resp = client.post(
            f"/reservations/{res_id}/confirm",
            headers={"X-API-Key": api_key},
        )
        assert conf_resp.status_code == 200
        data = conf_resp.json()
        assert data["status"] == "confirmed"

    def test_cancel_reservation_success(
        self, client: TestClient, api_key: str, sku_with_stock: str
    ):
        res_resp = client.post(
            "/reservations",
            json={
                "sku_id": sku_with_stock,
                "quantity": 10,
                "idempotency_key": "key-1",
            },
            headers={"X-API-Key": api_key},
        )
        res_id = res_resp.json()["reservation_id"]

        cancel_resp = client.post(
            f"/reservations/{res_id}/cancel",
            headers={"X-API-Key": api_key},
        )
        assert cancel_resp.status_code == 200
        data = cancel_resp.json()
        assert data["status"] == "cancelled"

    def test_confirm_nonexistent_reservation(self, client: TestClient, api_key: str):
        response = client.post(
            "/reservations/nonexistent/confirm",
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 404


class TestOrderEndpoints:
    @pytest.fixture
    def orders_setup(self, client: TestClient, api_key: str):
        client.post(
            "/skus",
            json={"id": "sku-001", "name": "Widget A"},
            headers={"X-API-Key": api_key},
        )
        client.post(
            "/skus/sku-001/stock",
            json={"quantity": 1000},
            headers={"X-API-Key": api_key},
        )

        for i in range(15):
            client.post(
                "/reservations",
                json={
                    "sku_id": "sku-001",
                    "quantity": 1,
                    "idempotency_key": f"key-{i}",
                },
                headers={"X-API-Key": api_key},
            )

    def test_list_orders_empty(self, client: TestClient):
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["size"] == 10
        assert data["pages"] == 0

    def test_list_orders_with_pagination(self, client: TestClient, orders_setup):
        resp1 = client.get("/orders?page=1&size=10")
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert len(data1["items"]) == 10
        assert data1["total"] == 15
        assert data1["pages"] == 2

        resp2 = client.get("/orders?page=2&size=10")
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert len(data2["items"]) == 5

    def test_list_orders_invalid_pagination(self, client: TestClient):
        response = client.get("/orders?page=0&size=10")
        assert response.status_code == 422

        response = client.get("/orders?page=1&size=200")
        assert response.status_code == 422

    def test_list_orders_no_auth_required(self, client: TestClient, orders_setup):
        response = client.get("/orders")
        assert response.status_code == 200


class TestSecurityErrors:
    def test_mutating_endpoints_require_auth(self, client: TestClient):
        endpoints = [
            ("POST", "/skus", {"id": "sku-001", "name": "Widget A"}),
            ("POST", "/skus/sku-001/stock", {"quantity": 100}),
            ("POST", "/reservations", {"sku_id": "sku-001", "quantity": 10, "idempotency_key": "key"}),
        ]

        for method, path, payload in endpoints:
            response = client.post(path, json=payload) if method == "POST" else None
            assert response.status_code == 401, f"Endpoint {path} did not require auth"

    def test_read_endpoints_no_auth(self, client: TestClient):
        response = client.get("/health")
        assert response.status_code == 200

        response = client.get("/orders")
        assert response.status_code == 200
