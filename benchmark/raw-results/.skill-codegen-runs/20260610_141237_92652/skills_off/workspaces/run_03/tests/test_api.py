"""Tests for the API endpoints."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from commerce_service.app import app, db


@pytest.fixture
def client():
    app.dependency_overrides.clear()

    def override_get_session():
        test_db = db.__class__("sqlite:///:memory:")
        session = test_db.get_session()
        yield session
        session.close()

    app.dependency_overrides[db.get_session] = override_get_session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def valid_headers():
    return {"X-API-Token": "test-api-key-12345"}


class TestHealthCheck:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSKUEndpoints:
    def test_create_sku_success(self, client, valid_headers):
        response = client.post(
            "/skus",
            json={"sku": "PRODUCT-001", "initial_stock": 100},
            headers=valid_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "PRODUCT-001"
        assert data["available_stock"] == 100

    def test_create_sku_missing_token(self, client):
        response = client.post(
            "/skus",
            json={"sku": "PRODUCT-001", "initial_stock": 100},
        )
        assert response.status_code == 401

    def test_create_sku_invalid_token(self, client):
        response = client.post(
            "/skus",
            json={"sku": "PRODUCT-001", "initial_stock": 100},
            headers={"X-API-Token": "invalid-token"},
        )
        assert response.status_code == 401

    def test_adjust_stock_success(self, client, valid_headers):
        client.post(
            "/skus",
            json={"sku": "PRODUCT-001", "initial_stock": 100},
            headers=valid_headers,
        )
        response = client.post(
            "/stock/adjust",
            json={"sku": "PRODUCT-001", "amount": 50},
            headers=valid_headers,
        )
        assert response.status_code == 200
        assert response.json()["available_stock"] == 150

    def test_adjust_stock_missing_token(self, client):
        response = client.post(
            "/stock/adjust",
            json={"sku": "PRODUCT-001", "amount": 50},
        )
        assert response.status_code == 401


class TestReservationEndpoints:
    def test_create_reservation_success(self, client, valid_headers):
        client.post(
            "/skus",
            json={"sku": "PRODUCT-001", "initial_stock": 100},
            headers=valid_headers,
        )
        response = client.post(
            "/reservations",
            json={
                "sku": "PRODUCT-001",
                "quantity": 25,
                "idempotency_key": "idem-key-1",
            },
            headers=valid_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "PRODUCT-001"
        assert data["quantity"] == 25
        assert data["status"] == "PENDING"

    def test_create_reservation_insufficient_stock(self, client, valid_headers):
        client.post(
            "/skus",
            json={"sku": "PRODUCT-001", "initial_stock": 100},
            headers=valid_headers,
        )
        response = client.post(
            "/reservations",
            json={
                "sku": "PRODUCT-001",
                "quantity": 150,
                "idempotency_key": "idem-key-1",
            },
            headers=valid_headers,
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Insufficient stock"

    def test_create_reservation_idempotency(self, client, valid_headers):
        client.post(
            "/skus",
            json={"sku": "PRODUCT-001", "initial_stock": 100},
            headers=valid_headers,
        )
        response1 = client.post(
            "/reservations",
            json={
                "sku": "PRODUCT-001",
                "quantity": 25,
                "idempotency_key": "idem-key-1",
            },
            headers=valid_headers,
        )
        response2 = client.post(
            "/reservations",
            json={
                "sku": "PRODUCT-001",
                "quantity": 25,
                "idempotency_key": "idem-key-1",
            },
            headers=valid_headers,
        )
        data1 = response1.json()
        data2 = response2.json()
        assert data1["id"] == data2["id"]
        assert data1["sku"] == data2["sku"]

    def test_create_reservation_missing_token(self, client):
        response = client.post(
            "/reservations",
            json={
                "sku": "PRODUCT-001",
                "quantity": 25,
                "idempotency_key": "idem-key-1",
            },
        )
        assert response.status_code == 401

    def test_confirm_reservation_success(self, client, valid_headers):
        client.post(
            "/skus",
            json={"sku": "PRODUCT-001", "initial_stock": 100},
            headers=valid_headers,
        )
        res_response = client.post(
            "/reservations",
            json={
                "sku": "PRODUCT-001",
                "quantity": 25,
                "idempotency_key": "idem-key-1",
            },
            headers=valid_headers,
        )
        res_id = res_response.json()["id"]
        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers=valid_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "CONFIRMED"

    def test_confirm_reservation_expired(self, client, valid_headers):
        from datetime import datetime, timezone, timedelta
        from commerce_service.repository import Database

        client.post(
            "/skus",
            json={"sku": "PRODUCT-001", "initial_stock": 100},
            headers=valid_headers,
        )
        res_response = client.post(
            "/reservations",
            json={
                "sku": "PRODUCT-001",
                "quantity": 25,
                "idempotency_key": "idem-key-1",
            },
            headers=valid_headers,
        )
        res_id = res_response.json()["id"]

        # Manually update the created_at to be old
        session = db.get_session()
        from commerce_service.repository import ReservationModel
        from sqlalchemy import select

        stmt = select(ReservationModel).where(ReservationModel.id == res_id)
        reservation = session.scalars(stmt).first()
        old_time = datetime.now(timezone.utc) - timedelta(seconds=301)
        reservation.created_at = old_time
        session.commit()
        session.close()

        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers=valid_headers,
        )
        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()

    def test_confirm_non_pending_fails(self, client, valid_headers):
        client.post(
            "/skus",
            json={"sku": "PRODUCT-001", "initial_stock": 100},
            headers=valid_headers,
        )
        res_response = client.post(
            "/reservations",
            json={
                "sku": "PRODUCT-001",
                "quantity": 25,
                "idempotency_key": "idem-key-1",
            },
            headers=valid_headers,
        )
        res_id = res_response.json()["id"]
        client.post(
            f"/reservations/{res_id}/confirm",
            headers=valid_headers,
        )
        response = client.post(
            f"/reservations/{res_id}/confirm",
            headers=valid_headers,
        )
        assert response.status_code == 400

    def test_cancel_reservation_success(self, client, valid_headers):
        client.post(
            "/skus",
            json={"sku": "PRODUCT-001", "initial_stock": 100},
            headers=valid_headers,
        )
        res_response = client.post(
            "/reservations",
            json={
                "sku": "PRODUCT-001",
                "quantity": 25,
                "idempotency_key": "idem-key-1",
            },
            headers=valid_headers,
        )
        res_id = res_response.json()["id"]
        response = client.post(
            f"/reservations/{res_id}/cancel",
            headers=valid_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "CANCELLED"

    def test_cancel_reservation_missing_token(self, client):
        response = client.post(
            "/reservations/1/cancel",
        )
        assert response.status_code == 401


class TestOrderEndpoints:
    def test_list_orders_empty(self, client):
        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_orders_with_data(self, client, valid_headers):
        client.post(
            "/skus",
            json={"sku": "PRODUCT-001", "initial_stock": 1000},
            headers=valid_headers,
        )
        for i in range(5):
            res_response = client.post(
                "/reservations",
                json={
                    "sku": "PRODUCT-001",
                    "quantity": 10,
                    "idempotency_key": f"idem-key-{i}",
                },
                headers=valid_headers,
            )
            res_id = res_response.json()["id"]
            client.post(
                f"/reservations/{res_id}/confirm",
                headers=valid_headers,
            )

        response = client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["size"] == 10

    def test_list_orders_pagination(self, client, valid_headers):
        client.post(
            "/skus",
            json={"sku": "PRODUCT-001", "initial_stock": 1000},
            headers=valid_headers,
        )
        for i in range(15):
            res_response = client.post(
                "/reservations",
                json={
                    "sku": "PRODUCT-001",
                    "quantity": 10,
                    "idempotency_key": f"idem-key-{i}",
                },
                headers=valid_headers,
            )
            res_id = res_response.json()["id"]
            client.post(
                f"/reservations/{res_id}/confirm",
                headers=valid_headers,
            )

        page1 = client.get("/orders?page=1&size=10")
        assert page1.status_code == 200
        data1 = page1.json()
        assert len(data1["items"]) == 10
        assert data1["total"] == 15
        assert data1["page"] == 1

        page2 = client.get("/orders?page=2&size=10")
        assert page2.status_code == 200
        data2 = page2.json()
        assert len(data2["items"]) == 5
        assert data2["page"] == 2

    def test_list_orders_custom_size(self, client, valid_headers):
        client.post(
            "/skus",
            json={"sku": "PRODUCT-001", "initial_stock": 1000},
            headers=valid_headers,
        )
        for i in range(25):
            res_response = client.post(
                "/reservations",
                json={
                    "sku": "PRODUCT-001",
                    "quantity": 10,
                    "idempotency_key": f"idem-key-{i}",
                },
                headers=valid_headers,
            )
            res_id = res_response.json()["id"]
            client.post(
                f"/reservations/{res_id}/confirm",
                headers=valid_headers,
            )

        response = client.get("/orders?page=1&size=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5
        assert data["size"] == 5
        assert data["total"] == 25
