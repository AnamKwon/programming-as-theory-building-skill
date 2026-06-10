import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base, ReservationStatus
from commerce_service.service import CommerceService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def service(db):
    return CommerceService(db)


def test_create_sku(service):
    sku = service.create_sku(sku_code="SKU001", name="Product 1")
    assert sku.sku_code == "SKU001"
    assert sku.name == "Product 1"


def test_adjust_stock(service):
    sku = service.create_sku(sku_code="SKU001", name="Product 1")
    inv = service.adjust_stock(sku.id, 100)
    assert inv.available_quantity == 100
    assert inv.reserved_quantity == 0

    inv = service.adjust_stock(sku.id, -30)
    assert inv.available_quantity == 70


def test_create_reservation_success(service):
    sku = service.create_sku(sku_code="SKU001", name="Product 1")
    service.adjust_stock(sku.id, 100)

    res = service.create_reservation(
        sku_id=sku.id,
        quantity=50,
        idempotency_key="idem-001",
        ttl_seconds=3600,
    )
    assert res.quantity == 50
    assert res.status == ReservationStatus.PENDING

    # Check inventory is reserved
    inv = service.inventory_repo.get_by_sku_id(sku.id)
    assert inv.available_quantity == 50
    assert inv.reserved_quantity == 50


def test_create_reservation_insufficient_stock(service):
    sku = service.create_sku(sku_code="SKU001", name="Product 1")
    service.adjust_stock(sku.id, 30)

    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation(
            sku_id=sku.id,
            quantity=50,
            idempotency_key="idem-001",
            ttl_seconds=3600,
        )


def test_idempotent_reservation(service):
    sku = service.create_sku(sku_code="SKU001", name="Product 1")
    service.adjust_stock(sku.id, 100)

    res1 = service.create_reservation(
        sku_id=sku.id,
        quantity=50,
        idempotency_key="idem-001",
        ttl_seconds=3600,
    )

    res2 = service.create_reservation(
        sku_id=sku.id,
        quantity=50,
        idempotency_key="idem-001",
        ttl_seconds=3600,
    )

    assert res1.id == res2.id

    # Inventory should still have only 50 reserved
    inv = service.inventory_repo.get_by_sku_id(sku.id)
    assert inv.available_quantity == 50
    assert inv.reserved_quantity == 50


def test_confirm_reservation(service):
    sku = service.create_sku(sku_code="SKU001", name="Product 1")
    service.adjust_stock(sku.id, 100)

    res = service.create_reservation(
        sku_id=sku.id,
        quantity=50,
        idempotency_key="idem-001",
        ttl_seconds=3600,
    )

    order = service.confirm_reservation(res.id)
    assert order.sku_id == sku.id
    assert order.quantity == 50

    # Check reservation is confirmed
    updated_res = service.reservation_repo.get_by_id(res.id)
    assert updated_res.status == ReservationStatus.CONFIRMED

    # Check inventory: reserved_quantity should decrease
    inv = service.inventory_repo.get_by_sku_id(sku.id)
    assert inv.available_quantity == 50
    assert inv.reserved_quantity == 0


def test_confirm_expired_reservation(service):
    sku = service.create_sku(sku_code="SKU001", name="Product 1")
    service.adjust_stock(sku.id, 100)

    # Create a reservation that's already expired
    res = service.reservation_repo.create(
        sku_id=sku.id,
        quantity=50,
        expires_at=datetime.utcnow() - timedelta(hours=1),
        idempotency_key="idem-001",
    )

    # Try to confirm it
    with pytest.raises(ValueError, match="expired"):
        service.confirm_reservation(res.id)

    # Check reservation is marked as expired
    updated_res = service.reservation_repo.get_by_id(res.id)
    assert updated_res.status == ReservationStatus.EXPIRED


def test_cancel_reservation(service):
    sku = service.create_sku(sku_code="SKU001", name="Product 1")
    service.adjust_stock(sku.id, 100)

    res = service.create_reservation(
        sku_id=sku.id,
        quantity=50,
        idempotency_key="idem-001",
        ttl_seconds=3600,
    )

    service.cancel_reservation(res.id)

    # Check reservation is cancelled
    updated_res = service.reservation_repo.get_by_id(res.id)
    assert updated_res.status == ReservationStatus.CANCELLED

    # Check inventory: stock should be released
    inv = service.inventory_repo.get_by_sku_id(sku.id)
    assert inv.available_quantity == 100
    assert inv.reserved_quantity == 0


def test_list_orders_pagination(service):
    sku = service.create_sku(sku_code="SKU001", name="Product 1")
    service.adjust_stock(sku.id, 500)

    # Create multiple orders
    for i in range(25):
        res = service.create_reservation(
            sku_id=sku.id,
            quantity=10,
            idempotency_key=f"idem-{i}",
            ttl_seconds=3600,
        )
        service.confirm_reservation(res.id)

    # Test pagination
    result1 = service.list_orders(limit=10, offset=0)
    assert len(result1["orders"]) == 10
    assert result1["total"] == 25
    assert result1["limit"] == 10
    assert result1["offset"] == 0

    result2 = service.list_orders(limit=10, offset=10)
    assert len(result2["orders"]) == 10

    result3 = service.list_orders(limit=10, offset=20)
    assert len(result3["orders"]) == 5
