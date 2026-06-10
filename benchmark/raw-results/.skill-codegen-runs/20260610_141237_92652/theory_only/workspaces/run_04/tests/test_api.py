import pytest
import tempfile
import os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.commerce_service.app import app
from src.commerce_service.models import Base
from src.commerce_service.repository import get_db


@pytest.fixture
def temp_db():
    db_fd, db_path = tempfile.mkstemp()
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield None
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(temp_db):
    return TestClient(app)


def get_auth_headers():
    return {"Authorization": "Bearer test-api-key"}


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_sku(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=get_auth_headers(),
    )
    assert response.status_code == 201
    assert response.json()["sku"] == "SKU001"
    assert response.json()["available_stock"] == 100


def test_adjust_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=get_auth_headers(),
    )

    response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": -30},
        headers=get_auth_headers(),
    )
    assert response.status_code == 200
    assert response.json()["available_stock"] == 70


def test_create_reservation_success(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=get_auth_headers(),
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key001"},
        headers=get_auth_headers(),
    )
    assert response.status_code == 201
    assert response.json()["sku"] == "SKU001"
    assert response.json()["quantity"] == 50
    assert response.json()["status"] == "PENDING"


def test_insufficient_stock(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 30},
        headers=get_auth_headers(),
    )

    response = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key001"},
        headers=get_auth_headers(),
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock"


def test_idempotent_reservation(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=get_auth_headers(),
    )

    response1 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key001"},
        headers=get_auth_headers(),
    )
    assert response1.status_code == 201
    id1 = response1.json()["id"]

    response2 = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key001"},
        headers=get_auth_headers(),
    )
    # Spec says return previously saved response immediately without mutating again
    # We return 201 for idempotent on creation, but can return the same data
    assert response2.status_code == 201
    assert response2.json()["id"] == id1

    # Stock should only be deducted once
    stock_response = client.post(
        "/stock/adjust",
        json={"sku": "SKU001", "amount": 0},
        headers=get_auth_headers(),
    )
    assert stock_response.json()["available_stock"] == 50


def test_confirm_reservation(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=get_auth_headers(),
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key001"},
        headers=get_auth_headers(),
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=get_auth_headers(),
    )
    assert response.status_code == 200
    assert response.json()["sku"] == "SKU001"
    assert response.json()["quantity"] == 50


def test_expired_reservation(client, temp_db):
    from datetime import datetime, timedelta
    from src.commerce_service.models import ReservationRecord

    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=get_auth_headers(),
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key001"},
        headers=get_auth_headers(),
    )
    reservation_id = res.json()["id"]

    # Get the session from app dependency
    from src.commerce_service.repository import get_db
    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)

    res_record = db.query(ReservationRecord).filter(
        ReservationRecord.id == reservation_id
    ).first()
    res_record.created_at = datetime.utcnow() - timedelta(seconds=301)
    db.commit()

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=get_auth_headers(),
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Reservation expired"


def test_cancel_reservation(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=get_auth_headers(),
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key001"},
        headers=get_auth_headers(),
    )
    reservation_id = res.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=get_auth_headers(),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


def test_cancel_non_pending_reservation(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=get_auth_headers(),
    )

    res = client.post(
        "/reservations",
        json={"sku": "SKU001", "quantity": 50, "idempotency_key": "key001"},
        headers=get_auth_headers(),
    )
    reservation_id = res.json()["id"]

    # Cancel it
    client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=get_auth_headers(),
    )

    # Try to cancel again
    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=get_auth_headers(),
    )
    assert response.status_code == 400


def test_unauthorized_access(client):
    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
    )
    assert response.status_code == 403

    response = client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers={"Authorization": "Bearer invalid-key"},
    )
    assert response.status_code == 401


def test_get_orders_pagination(client):
    client.post(
        "/skus",
        json={"sku": "SKU001", "initial_stock": 100},
        headers=get_auth_headers(),
    )

    for i in range(15):
        res = client.post(
            "/reservations",
            json={"sku": "SKU001", "quantity": 1, "idempotency_key": f"key{i}"},
            headers=get_auth_headers(),
        )
        reservation_id = res.json()["id"]
        client.post(
            f"/reservations/{reservation_id}/confirm",
            headers=get_auth_headers(),
        )

    response = client.get(
        "/orders?page=1&size=10",
        headers=get_auth_headers(),
    )
    assert response.status_code == 200
    assert response.json()["page"] == 1
    assert response.json()["size"] == 10
    assert response.json()["total"] == 15
    assert len(response.json()["orders"]) == 10

    response = client.get(
        "/orders?page=2&size=10",
        headers=get_auth_headers(),
    )
    assert response.json()["page"] == 2
    assert len(response.json()["orders"]) == 5


def test_happy_path_workflow(client):
    # Create SKU
    sku_res = client.post(
        "/skus",
        json={"sku": "LAPTOP", "initial_stock": 10},
        headers=get_auth_headers(),
    )
    assert sku_res.status_code == 201

    # Reserve
    reserve_res = client.post(
        "/reservations",
        json={"sku": "LAPTOP", "quantity": 3, "idempotency_key": "order123"},
        headers=get_auth_headers(),
    )
    assert reserve_res.status_code == 201
    reservation_id = reserve_res.json()["id"]

    # Confirm
    confirm_res = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=get_auth_headers(),
    )
    assert confirm_res.status_code == 200
    order_id = confirm_res.json()["id"]

    # Get orders
    orders_res = client.get(
        "/orders",
        headers=get_auth_headers(),
    )
    assert orders_res.status_code == 200
    orders = orders_res.json()["orders"]
    assert any(o["id"] == order_id for o in orders)
