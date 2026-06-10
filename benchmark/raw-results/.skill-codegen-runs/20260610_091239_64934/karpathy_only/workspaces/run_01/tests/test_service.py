"""Tests for the commerce service."""

import pytest

from src.commerce_service.models import ReservationStatus


def test_create_sku(service):
    result = service.create_sku("Widget", 29.99)
    assert result["id"] is not None
    assert result["name"] == "Widget"
    assert result["price"] == 29.99


def test_adjust_stock(service):
    sku = service.create_sku("Widget", 29.99)
    result = service.adjust_stock(sku["id"], 100)

    assert result["sku_id"] == sku["id"]
    assert result["available_quantity"] == 100
    assert result["reserved_quantity"] == 0


def test_adjust_stock_nonexistent_sku(service):
    with pytest.raises(Exception):  # HTTPException with 404
        service.adjust_stock(999, 100)


def test_create_reservation_happy_path(service):
    sku = service.create_sku("Widget", 29.99)
    service.adjust_stock(sku["id"], 100)

    result = service.create_reservation(sku["id"], 10, "idempotency-1")

    assert result["id"] is not None
    assert result["sku_id"] == sku["id"]
    assert result["quantity"] == 10
    assert result["status"] == ReservationStatus.PENDING


def test_create_reservation_insufficient_stock(service):
    sku = service.create_sku("Widget", 29.99)
    service.adjust_stock(sku["id"], 5)

    with pytest.raises(Exception):  # HTTPException with 409
        service.create_reservation(sku["id"], 10, "idempotency-1")


def test_create_reservation_idempotent(service):
    sku = service.create_sku("Widget", 29.99)
    service.adjust_stock(sku["id"], 100)

    result1 = service.create_reservation(sku["id"], 10, "idempotency-1")
    result2 = service.create_reservation(sku["id"], 10, "idempotency-1")

    assert result1["id"] == result2["id"]


def test_confirm_reservation_happy_path(service):
    sku = service.create_sku("Widget", 29.99)
    service.adjust_stock(sku["id"], 100)

    res = service.create_reservation(sku["id"], 10, "idempotency-1")
    result = service.confirm_reservation(res["id"])

    assert result["status"] == ReservationStatus.CONFIRMED


def test_confirm_reservation_expired(service, monkeypatch):
    from unittest.mock import patch
    from datetime import datetime, timedelta

    sku = service.create_sku("Widget", 29.99)
    service.adjust_stock(sku["id"], 100)

    res = service.create_reservation(sku["id"], 10, "idempotency-1")

    # Mock datetime to simulate expiration
    original_utcnow = datetime.utcnow
    future_time = original_utcnow() + timedelta(minutes=20)

    with patch("src.commerce_service.service.datetime") as mock_dt:
        mock_dt.utcnow.return_value = future_time
        mock_dt.fromisoformat = datetime.fromisoformat

        with pytest.raises(Exception):  # HTTPException with 409
            service.confirm_reservation(res["id"])


def test_cancel_reservation(service):
    sku = service.create_sku("Widget", 29.99)
    service.adjust_stock(sku["id"], 100)

    res = service.create_reservation(sku["id"], 10, "idempotency-1")
    result = service.cancel_reservation(res["id"])

    assert result["status"] == ReservationStatus.CANCELLED


def test_cancel_reservation_already_cancelled(service):
    sku = service.create_sku("Widget", 29.99)
    service.adjust_stock(sku["id"], 100)

    res = service.create_reservation(sku["id"], 10, "idempotency-1")
    service.cancel_reservation(res["id"])

    with pytest.raises(Exception):  # HTTPException with 409
        service.cancel_reservation(res["id"])


def test_list_orders_pagination(service):
    sku = service.create_sku("Widget", 29.99)
    service.adjust_stock(sku["id"], 1000)

    # Create and confirm multiple reservations
    for i in range(5):
        res = service.create_reservation(sku["id"], 10, f"idempotency-{i}")
        service.confirm_reservation(res["id"])

    result = service.list_orders(skip=0, limit=2)
    assert result["total"] == 5
    assert len(result["items"]) == 2

    result2 = service.list_orders(skip=2, limit=2)
    assert len(result2["items"]) == 2


def test_stock_reservation_tracking(service):
    sku = service.create_sku("Widget", 29.99)
    service.adjust_stock(sku["id"], 100)

    # Create reservation - should reserve quantity
    service.create_reservation(sku["id"], 10, "idempotency-1")
    stock1 = service.repo.get_stock(sku["id"])
    assert stock1["reserved_quantity"] == 10

    # Confirm reservation - should move from reserved to committed
    res = service.repo.find_reservation_by_idempotency_key("idempotency-1")
    service.confirm_reservation(res["id"])
    stock2 = service.repo.get_stock(sku["id"])
    assert stock2["reserved_quantity"] == 0
    assert stock2["available_quantity"] == 90
