import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from commerce_service.models import Base
from commerce_service.repository import Repository
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
def repo(db):
    return Repository(db)


@pytest.fixture
def service(repo):
    return CommerceService(repo)


def test_create_sku(service):
    sku = service.create_sku("Widget", 29.99)
    assert sku.name == "Widget"
    assert sku.price == 29.99
    assert sku.id.startswith("sku_")


def test_adjust_stock_increase(service, repo):
    service.create_sku("Widget", 29.99)
    skus = repo.db.query(repo.db.query(Base.metadata.tables['skus']).first().__class__).all()
    # Get the first SKU created
    sku = repo.get_sku(list(repo.db.execute(repo.db.query(Base.registry.mapped_class.__table__).select()).scalar()))

    # Use direct query to get SKU
    from commerce_service.models import SKUModel
    sku_obj = repo.db.query(SKUModel).first()
    assert sku_obj is not None

    result = service.adjust_stock(sku_obj.id, 100)
    assert result.quantity_available == 100
    assert result.quantity_reserved == 0


def test_adjust_stock_decrease(service):
    sku = service.create_sku("Widget", 29.99)
    service.adjust_stock(sku.id, 100)
    result = service.adjust_stock(sku.id, -30)
    assert result.quantity_available == 70


def test_adjust_stock_negative_fails(service):
    sku = service.create_sku("Widget", 29.99)
    service.adjust_stock(sku.id, 10)
    with pytest.raises(ValueError, match="Quantity cannot be negative"):
        service.adjust_stock(sku.id, -20)


def test_create_reservation_success(service):
    sku = service.create_sku("Widget", 29.99)
    service.adjust_stock(sku.id, 100)

    res = service.create_reservation(sku.id, 10, "idem_001")
    assert res.status == "pending"
    assert res.quantity == 10
    assert res.id.startswith("res_")


def test_create_reservation_insufficient_stock(service):
    sku = service.create_sku("Widget", 29.99)
    service.adjust_stock(sku.id, 10)

    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation(sku.id, 20, "idem_001")


def test_reservation_idempotency(service):
    sku = service.create_sku("Widget", 29.99)
    service.adjust_stock(sku.id, 100)

    res1 = service.create_reservation(sku.id, 10, "idem_001")
    res2 = service.create_reservation(sku.id, 10, "idem_001")

    assert res1.id == res2.id


def test_confirm_reservation(service):
    sku = service.create_sku("Widget", 29.99)
    service.adjust_stock(sku.id, 100)

    res = service.create_reservation(sku.id, 10, "idem_001")
    confirmed = service.confirm_reservation(res.id)

    assert confirmed.status == "confirmed"


def test_confirm_already_confirmed(service):
    sku = service.create_sku("Widget", 29.99)
    service.adjust_stock(sku.id, 100)

    res = service.create_reservation(sku.id, 10, "idem_001")
    service.confirm_reservation(res.id)
    confirmed2 = service.confirm_reservation(res.id)

    assert confirmed2.status == "confirmed"


def test_cancel_pending_reservation(service):
    sku = service.create_sku("Widget", 29.99)
    service.adjust_stock(sku.id, 100)

    res = service.create_reservation(sku.id, 10, "idem_001")
    cancelled = service.cancel_reservation(res.id)

    assert cancelled.status == "cancelled"


def test_cancel_confirmed_fails(service):
    sku = service.create_sku("Widget", 29.99)
    service.adjust_stock(sku.id, 100)

    res = service.create_reservation(sku.id, 10, "idem_001")
    service.confirm_reservation(res.id)

    with pytest.raises(ValueError, match="Cannot cancel a confirmed"):
        service.cancel_reservation(res.id)


def test_confirm_expired_reservation(service, repo):
    sku = service.create_sku("Widget", 29.99)
    service.adjust_stock(sku.id, 100)

    res = service.create_reservation(sku.id, 10, "idem_001")

    # Manually expire the reservation
    expired_time = datetime.utcnow() - timedelta(hours=1)
    res_model = repo.get_reservation(res.id)
    res_model.expires_at = expired_time
    repo.db.commit()

    with pytest.raises(ValueError, match="expired"):
        service.confirm_reservation(res.id)


def test_create_order(service):
    order = service.create_order()
    assert order.status == "pending"
    assert order.id.startswith("ord_")


def test_get_order(service):
    order = service.create_order()
    retrieved = service.get_order(order.id)
    assert retrieved.id == order.id


def test_list_orders(service):
    for _ in range(15):
        service.create_order()

    result = service.list_orders(skip=0, limit=10)
    assert len(result["items"]) == 10
    assert result["total"] == 15

    result2 = service.list_orders(skip=10, limit=10)
    assert len(result2["items"]) == 5


def test_stock_reservation_tracking(service, repo):
    sku = service.create_sku("Widget", 29.99)
    service.adjust_stock(sku.id, 100)

    service.create_reservation(sku.id, 30, "idem_001")

    stock = repo.get_stock(sku.id)
    assert stock.quantity_available == 70
    assert stock.quantity_reserved == 30


def test_stock_release_on_cancel(service, repo):
    sku = service.create_sku("Widget", 29.99)
    service.adjust_stock(sku.id, 100)

    res = service.create_reservation(sku.id, 30, "idem_001")
    service.cancel_reservation(res.id)

    stock = repo.get_stock(sku.id)
    assert stock.quantity_available == 100
    assert stock.quantity_reserved == 0


def test_cleanup_expired_reservations(service, repo):
    sku = service.create_sku("Widget", 29.99)
    service.adjust_stock(sku.id, 100)

    res = service.create_reservation(sku.id, 10, "idem_001")

    # Manually expire
    res_model = repo.get_reservation(res.id)
    res_model.expires_at = datetime.utcnow() - timedelta(hours=1)
    repo.db.commit()

    count = service.cleanup_expired_reservations()
    assert count == 1

    updated = repo.get_reservation(res.id)
    assert updated.status == "expired"
