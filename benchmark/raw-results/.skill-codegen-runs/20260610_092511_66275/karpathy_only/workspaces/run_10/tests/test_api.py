import pytest
from fastapi.testclient import TestClient

from src.commerce_service.app import app
from src.commerce_service.repository import Repository
from src.commerce_service.service import CommerceService

# Override dependencies for testing
test_repo = Repository("sqlite:///:memory:")
test_service = CommerceService(test_repo)


def override_get_service():
    return test_service


@app.dependency_overrides[CommerceService] = override_get_service


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_db():
    """Reset database between tests."""
    global test_repo, test_service
    test_repo = Repository("sqlite:///:memory:")
    test_service = CommerceService(test_repo)
    yield


HEADERS = {"X-API-Key": "test-key-123"}


class TestHealth:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestSKUEndpoints:
    def test_create_sku(self, client):
        response = client.post(
            "/skus",
            json={
                "sku": "SKU-001",
                "description": "Laptop",
                "quantity": 10,
            },
            headers=HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sku"] == "SKU-001"
        assert data["quantity"] == 10

    def test_create_sku_missing_auth(self, client):
        response = client.post(
            "/skus",
            json={
                "sku": "SKU-001",
                "description": "Laptop",
                "quantity": 10,
            },
        )
        assert response.status_code == 403

    def test_create_duplicate_sku(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "description": "Laptop", "quantity": 10},
            headers=HEADERS,
        )
        response = client.post(
            "/skus",
            json={"sku": "SKU-001", "description": "Desktop", "quantity": 5},
            headers=HEADERS,
        )
        assert response.status_code == 409

    def test_get_sku(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "description": "Laptop", "quantity": 10},
            headers=HEADERS,
        )
        response = client.get("/skus/SKU-001")
        assert response.status_code == 200
        assert response.json()["sku"] == "SKU-001"

    def test_get_nonexistent_sku(self, client):
        response = client.get("/skus/NONEXISTENT")
        assert response.status_code == 404

    def test_adjust_stock(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "description": "Laptop", "quantity": 10},
            headers=HEADERS,
        )
        response = client.post(
            "/skus/SKU-001/adjust",
            json={"adjustment": 5},
            headers=HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["quantity"] == 15

    def test_adjust_nonexistent_sku(self, client):
        response = client.post(
            "/skus/NONEXISTENT/adjust",
            json={"adjustment": 5},
            headers=HEADERS,
        )
        assert response.status_code == 404


class TestReservationEndpoints:
    def test_create_reservation_happy_path(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "description": "Laptop", "quantity": 10},
            headers=HEADERS,
        )
        response = client.post(
            "/reservations",
            json={
                "order_id": "ORD-001",
                "sku": "SKU-001",
                "quantity": 5,
                "idempotency_key": "IDEMPOTENT-001",
            },
            headers=HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["order_id"] == "ORD-001"
        assert data["status"] == "pending"

    def test_create_reservation_insufficient_stock(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "description": "Laptop", "quantity": 5},
            headers=HEADERS,
        )
        response = client.post(
            "/reservations",
            json={
                "order_id": "ORD-001",
                "sku": "SKU-001",
                "quantity": 10,
                "idempotency_key": "IDEMPOTENT-001",
            },
            headers=HEADERS,
        )
        assert response.status_code == 409

    def test_create_reservation_idempotency(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "description": "Laptop", "quantity": 10},
            headers=HEADERS,
        )
        response1 = client.post(
            "/reservations",
            json={
                "order_id": "ORD-001",
                "sku": "SKU-001",
                "quantity": 5,
                "idempotency_key": "IDEMPOTENT-001",
            },
            headers=HEADERS,
        )
        response2 = client.post(
            "/reservations",
            json={
                "order_id": "ORD-001",
                "sku": "SKU-001",
                "quantity": 5,
                "idempotency_key": "IDEMPOTENT-001",
            },
            headers=HEADERS,
        )
        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response1.json()["reservation_id"] == response2.json()["reservation_id"]

    def test_confirm_reservation(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "description": "Laptop", "quantity": 10},
            headers=HEADERS,
        )
        res_response = client.post(
            "/reservations",
            json={
                "order_id": "ORD-001",
                "sku": "SKU-001",
                "quantity": 5,
                "idempotency_key": "IDEMPOTENT-001",
            },
            headers=HEADERS,
        )
        reservation_id = res_response.json()["reservation_id"]

        response = client.post(
            f"/reservations/{reservation_id}/confirm",
            json={},
            headers=HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"

    def test_confirm_nonexistent_reservation(self, client):
        response = client.post(
            "/reservations/NONEXISTENT/confirm",
            json={},
            headers=HEADERS,
        )
        assert response.status_code == 404

    def test_cancel_reservation(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "description": "Laptop", "quantity": 10},
            headers=HEADERS,
        )
        res_response = client.post(
            "/reservations",
            json={
                "order_id": "ORD-001",
                "sku": "SKU-001",
                "quantity": 5,
                "idempotency_key": "IDEMPOTENT-001",
            },
            headers=HEADERS,
        )
        reservation_id = res_response.json()["reservation_id"]

        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            json={},
            headers=HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_cancel_confirmed_reservation_fails(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "description": "Laptop", "quantity": 10},
            headers=HEADERS,
        )
        res_response = client.post(
            "/reservations",
            json={
                "order_id": "ORD-001",
                "sku": "SKU-001",
                "quantity": 5,
                "idempotency_key": "IDEMPOTENT-001",
            },
            headers=HEADERS,
        )
        reservation_id = res_response.json()["reservation_id"]

        client.post(
            f"/reservations/{reservation_id}/confirm",
            json={},
            headers=HEADERS,
        )

        response = client.post(
            f"/reservations/{reservation_id}/cancel",
            json={},
            headers=HEADERS,
        )
        assert response.status_code == 409

    def test_reservation_requires_auth(self, client):
        response = client.post(
            "/reservations",
            json={
                "order_id": "ORD-001",
                "sku": "SKU-001",
                "quantity": 5,
                "idempotency_key": "IDEMPOTENT-001",
            },
        )
        assert response.status_code == 403


class TestOrderEndpoints:
    def test_list_orders_empty(self, client):
        response = client.get("/orders", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["orders"] == []

    def test_list_orders_with_data(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "description": "Laptop", "quantity": 10},
            headers=HEADERS,
        )
        client.post(
            "/reservations",
            json={
                "order_id": "ORD-001",
                "sku": "SKU-001",
                "quantity": 5,
                "idempotency_key": "IDEMPOTENT-001",
            },
            headers=HEADERS,
        )

        response = client.get("/orders", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["orders"]) == 1
        assert data["orders"][0]["order_id"] == "ORD-001"

    def test_list_orders_pagination(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "description": "Laptop", "quantity": 100},
            headers=HEADERS,
        )
        for i in range(15):
            client.post(
                "/reservations",
                json={
                    "order_id": f"ORD-{i:03d}",
                    "sku": "SKU-001",
                    "quantity": 1,
                    "idempotency_key": f"IDEMPOTENT-{i:03d}",
                },
                headers=HEADERS,
            )

        response1 = client.get("/orders?limit=10&offset=0", headers=HEADERS)
        response2 = client.get("/orders?limit=10&offset=10", headers=HEADERS)

        assert response1.status_code == 200
        assert response2.status_code == 200
        data1 = response1.json()
        data2 = response2.json()

        assert data1["total"] == 15
        assert len(data1["orders"]) == 10
        assert data1["offset"] == 0
        assert len(data2["orders"]) == 5
        assert data2["offset"] == 10

    def test_list_orders_requires_auth(self, client):
        response = client.get("/orders")
        assert response.status_code == 403

    def test_get_order(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "description": "Laptop", "quantity": 10},
            headers=HEADERS,
        )
        client.post(
            "/reservations",
            json={
                "order_id": "ORD-001",
                "sku": "SKU-001",
                "quantity": 5,
                "idempotency_key": "IDEMPOTENT-001",
            },
            headers=HEADERS,
        )

        response = client.get("/orders/ORD-001", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["order_id"] == "ORD-001"
        assert len(data["items"]) == 1

    def test_get_nonexistent_order(self, client):
        response = client.get("/orders/NONEXISTENT", headers=HEADERS)
        assert response.status_code == 404

    def test_get_order_requires_auth(self, client):
        response = client.get("/orders/ORD-001")
        assert response.status_code == 403

    def test_order_status_confirmed_when_all_reservations_confirmed(self, client):
        client.post(
            "/skus",
            json={"sku": "SKU-001", "description": "Laptop", "quantity": 10},
            headers=HEADERS,
        )

        # Create two reservations for same order
        res1 = client.post(
            "/reservations",
            json={
                "order_id": "ORD-001",
                "sku": "SKU-001",
                "quantity": 3,
                "idempotency_key": "IDEMPOTENT-001",
            },
            headers=HEADERS,
        ).json()

        res2 = client.post(
            "/reservations",
            json={
                "order_id": "ORD-001",
                "sku": "SKU-001",
                "quantity": 2,
                "idempotency_key": "IDEMPOTENT-002",
            },
            headers=HEADERS,
        ).json()

        # Order should be pending
        order = client.get("/orders/ORD-001", headers=HEADERS).json()
        assert order["status"] == "pending"

        # Confirm first reservation
        client.post(
            f"/reservations/{res1['reservation_id']}/confirm",
            json={},
            headers=HEADERS,
        )
        order = client.get("/orders/ORD-001", headers=HEADERS).json()
        assert order["status"] == "pending"

        # Confirm second reservation
        client.post(
            f"/reservations/{res2['reservation_id']}/confirm",
            json={},
            headers=HEADERS,
        )
        order = client.get("/orders/ORD-001", headers=HEADERS).json()
        assert order["status"] == "confirmed"
