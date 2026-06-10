import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.app import app
from src.commerce_service.models import Base

# Override database for testing
TEST_DB_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DB_URL)
Base.metadata.create_all(bind=engine)
TestSessionLocal = sessionmaker(bind=engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


from src.commerce_service.app import get_db_session

app.dependency_overrides[get_db_session] = override_get_db

client = TestClient(app)
API_KEY = "test-key-123"
HEADERS = {"X-API-Key": API_KEY}


@pytest.fixture(autouse=True)
def reset_db():
    """Reset database before each test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


class TestHealth:
    def test_health_check(self):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKU:
    def test_create_sku(self):
        """Test creating a new SKU."""
        payload = {"name": "Widget", "quantity": 100}
        response = client.post("/skus", json=payload, headers=HEADERS)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Widget"
        assert data["available_stock"] == 100
        assert data["reserved_stock"] == 0

    def test_create_sku_unauthorized(self):
        """Test that missing API key is rejected."""
        payload = {"name": "Widget", "quantity": 100}
        response = client.post("/skus", json=payload)

        assert response.status_code == 403

    def test_adjust_stock_increase(self):
        """Test increasing stock."""
        # Create SKU first
        client.post("/skus", json={"name": "Widget", "quantity": 100}, headers=HEADERS)

        # Get the SKU ID (need to extract from list or use hardcoded for this test)
        # For simplicity, let's adjust by creating with a predictable ID scenario
        response = client.post(
            "/skus", json={"name": "Gadget", "quantity": 50}, headers=HEADERS
        )
        sku_id = response.json()["id"]

        response = client.post(
            f"/skus/{sku_id}/adjust-stock", json={"quantity": 25}, headers=HEADERS
        )

        assert response.status_code == 200
        assert response.json()["available_stock"] == 75

    def test_adjust_stock_sku_not_found(self):
        """Test adjusting stock for nonexistent SKU."""
        response = client.post(
            "/skus/sku-missing/adjust-stock", json={"quantity": 10}, headers=HEADERS
        )

        assert response.status_code == 404


class TestReservation:
    def test_create_reservation_happy_path(self):
        """Test successful reservation creation."""
        # Create SKU
        sku_response = client.post(
            "/skus", json={"name": "Widget", "quantity": 100}, headers=HEADERS
        )
        sku_id = sku_response.json()["id"]

        # Create reservation
        payload = {
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "key-1",
        }
        response = client.post("/reservations", json=payload, headers=HEADERS)

        assert response.status_code == 201
        data = response.json()
        assert data["quantity"] == 10
        assert data["state"] == "pending"

    def test_create_reservation_insufficient_stock(self):
        """Test reservation fails with insufficient stock."""
        # Create SKU with limited stock
        sku_response = client.post(
            "/skus", json={"name": "Widget", "quantity": 5}, headers=HEADERS
        )
        sku_id = sku_response.json()["id"]

        # Try to reserve more than available
        payload = {
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "key-1",
        }
        response = client.post("/reservations", json=payload, headers=HEADERS)

        assert response.status_code == 409

    def test_create_reservation_idempotent(self):
        """Test idempotent reservation retry."""
        # Create SKU
        sku_response = client.post(
            "/skus", json={"name": "Widget", "quantity": 100}, headers=HEADERS
        )
        sku_id = sku_response.json()["id"]

        # Create reservation
        payload = {
            "sku_id": sku_id,
            "quantity": 10,
            "idempotency_key": "key-1",
        }
        response1 = client.post("/reservations", json=payload, headers=HEADERS)
        response2 = client.post("/reservations", json=payload, headers=HEADERS)

        assert response1.json()["id"] == response2.json()["id"]

    def test_confirm_reservation(self):
        """Test reservation confirmation."""
        # Create SKU and reservation
        sku_response = client.post(
            "/skus", json={"name": "Widget", "quantity": 100}, headers=HEADERS
        )
        sku_id = sku_response.json()["id"]

        res_response = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "key-1"},
            headers=HEADERS,
        )
        res_id = res_response.json()["id"]

        # Confirm reservation
        response = client.post(f"/reservations/{res_id}/confirm", headers=HEADERS)

        assert response.status_code == 200
        assert response.json()["state"] == "confirmed"

    def test_cancel_reservation(self):
        """Test reservation cancellation."""
        # Create SKU and reservation
        sku_response = client.post(
            "/skus", json={"name": "Widget", "quantity": 100}, headers=HEADERS
        )
        sku_id = sku_response.json()["id"]

        res_response = client.post(
            "/reservations",
            json={"sku_id": sku_id, "quantity": 10, "idempotency_key": "key-1"},
            headers=HEADERS,
        )
        res_id = res_response.json()["id"]

        # Cancel reservation
        response = client.post(f"/reservations/{res_id}/cancel", headers=HEADERS)

        assert response.status_code == 200
        assert response.json()["state"] == "cancelled"

    def test_authorize_mutation_endpoints(self):
        """Test that mutation endpoints require API key."""
        payload = {"name": "Widget", "quantity": 100}
        response = client.post("/reservations", json=payload)

        assert response.status_code == 403


class TestOrder:
    def test_list_orders_empty(self):
        """Test listing orders when none exist."""
        response = client.get("/orders")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["size"] == 20

    def test_list_orders_pagination(self):
        """Test order list pagination."""
        # Create multiple SKUs and reservations to simulate orders
        for i in range(25):
            sku_response = client.post(
                "/skus", json={"name": f"Widget{i}", "quantity": 100}, headers=HEADERS
            )
            sku_id = sku_response.json()["id"]

            client.post(
                "/reservations",
                json={"sku_id": sku_id, "quantity": 10, "idempotency_key": f"key-{i}"},
                headers=HEADERS,
            )

        # Get first page
        response = client.get("/orders?page=1&size=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["total"] == 0  # No orders created, only reservations

    def test_get_order_not_found(self):
        """Test getting nonexistent order."""
        response = client.get("/orders/order-missing")

        assert response.status_code == 404
