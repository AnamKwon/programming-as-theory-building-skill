import pytest
from datetime import datetime, timedelta
from commerce_service.service import CommerceService


def test_create_sku(db):
    service = CommerceService(db)
    sku = service.create_sku("SKU-001", 100)
    assert sku.sku == "SKU-001"
    assert sku.stock == 100


def test_adjust_stock(db):
    service = CommerceService(db)
    service.create_sku("SKU-001", 100)
    new_stock = service.adjust_stock("SKU-001", 10)
    assert new_stock == 110

    new_stock = service.adjust_stock("SKU-001", -20)
    assert new_stock == 90


def test_create_reservation_happy_path(db):
    service = CommerceService(db)
    service.create_sku("SKU-001", 100)
    reservation, status_code = service.create_reservation("SKU-001", 10, "idempotency-1")
    assert status_code == 201
    assert reservation.quantity == 10
    assert reservation.status == "PENDING"
    assert reservation.idempotency_key == "idempotency-1"

    sku = service.repo.get_sku_by_sku_str("SKU-001")
    assert sku.stock == 90


def test_create_reservation_insufficient_stock(db):
    service = CommerceService(db)
    service.create_sku("SKU-001", 5)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation("SKU-001", 10, "idempotency-1")


def test_create_reservation_idempotency(db):
    service = CommerceService(db)
    service.create_sku("SKU-001", 100)
    reservation1, status_code1 = service.create_reservation("SKU-001", 10, "idempotency-1")
    assert status_code1 == 201
    assert reservation1.id

    initial_stock = service.repo.get_sku_by_sku_str("SKU-001").stock

    reservation2, status_code2 = service.create_reservation("SKU-001", 10, "idempotency-1")
    assert status_code2 == 200
    assert reservation2.id == reservation1.id

    final_stock = service.repo.get_sku_by_sku_str("SKU-001").stock
    assert final_stock == initial_stock


def test_confirm_reservation_happy_path(db):
    service = CommerceService(db)
    service.create_sku("SKU-001", 100)
    reservation, _ = service.create_reservation("SKU-001", 10, "idempotency-1")

    confirmed = service.confirm_reservation(reservation.id)
    assert confirmed.status == "CONFIRMED"

    orders, _ = service.get_orders()
    assert len(orders) == 1
    assert orders[0].reservation_id == reservation.id


def test_confirm_reservation_expired(db):
    service = CommerceService(db)
    service.create_sku("SKU-001", 100)
    reservation, _ = service.create_reservation("SKU-001", 10, "idempotency-1")

    from commerce_service.repository import Reservation
    old_time = datetime.utcnow() - timedelta(seconds=301)
    db.query(Reservation).filter(Reservation.id == reservation.id).update({Reservation.created_at: old_time})
    db.commit()

    with pytest.raises(ValueError, match="expired"):
        service.confirm_reservation(reservation.id)

    updated = service.repo.get_reservation_by_id(reservation.id)
    assert updated.status == "EXPIRED"

    sku = service.repo.get_sku_by_sku_str("SKU-001")
    assert sku.stock == 100


def test_confirm_reservation_not_pending(db):
    service = CommerceService(db)
    service.create_sku("SKU-001", 100)
    reservation, _ = service.create_reservation("SKU-001", 10, "idempotency-1")
    service.confirm_reservation(reservation.id)

    with pytest.raises(ValueError, match="not in PENDING state"):
        service.confirm_reservation(reservation.id)


def test_cancel_reservation(db):
    service = CommerceService(db)
    service.create_sku("SKU-001", 100)
    reservation, _ = service.create_reservation("SKU-001", 10, "idempotency-1")

    sku_before = service.repo.get_sku_by_sku_str("SKU-001")
    assert sku_before.stock == 90

    cancelled = service.cancel_reservation(reservation.id)
    assert cancelled.status == "CANCELLED"

    sku_after = service.repo.get_sku_by_sku_str("SKU-001")
    assert sku_after.stock == 100


def test_cancel_reservation_not_pending(db):
    service = CommerceService(db)
    service.create_sku("SKU-001", 100)
    reservation, _ = service.create_reservation("SKU-001", 10, "idempotency-1")
    service.confirm_reservation(reservation.id)

    with pytest.raises(ValueError, match="not in PENDING state"):
        service.cancel_reservation(reservation.id)


def test_get_orders_pagination(db):
    service = CommerceService(db)
    service.create_sku("SKU-001", 1000)

    for i in range(25):
        res, _ = service.create_reservation("SKU-001", 1, f"key-{i}")
        service.confirm_reservation(res.id)

    orders_page1, total1 = service.get_orders(page=1, size=10)
    assert len(orders_page1) == 10
    assert total1 == 25

    orders_page2, total2 = service.get_orders(page=2, size=10)
    assert len(orders_page2) == 10
    assert total2 == 25

    orders_page3, total3 = service.get_orders(page=3, size=10)
    assert len(orders_page3) == 5
    assert total3 == 25
