from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.commerce_service.models import Base, ReservationStatus
from src.commerce_service.repository import Repository
from src.commerce_service.service import CommerceService


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def service(db_session: Session) -> CommerceService:
    repo = Repository(db_session)
    return CommerceService(repo, reservation_ttl_minutes=1)


def test_create_sku(service: CommerceService) -> None:
    result = service.create_sku("SKU-001", "Widget", 100)
    assert result["sku_id"] == "SKU-001"
    assert result["name"] == "Widget"
    assert result["total_stock"] == 100
    assert result["reserved_stock"] == 0
    assert result["available_stock"] == 100


def test_create_duplicate_sku(service: CommerceService) -> None:
    service.create_sku("SKU-001", "Widget", 100)
    with pytest.raises(Exception) as exc:
        service.create_sku("SKU-001", "Widget", 50)
    assert "already exists" in str(exc.value)


def test_adjust_stock(service: CommerceService) -> None:
    service.create_sku("SKU-001", "Widget", 100)
    result = service.adjust_stock("SKU-001", 50)
    assert result["total_stock"] == 150
    assert result["available_stock"] == 150


def test_adjust_stock_negative(service: CommerceService) -> None:
    service.create_sku("SKU-001", "Widget", 100)
    with pytest.raises(Exception) as exc:
        service.adjust_stock("SKU-001", -150)
    assert "negative" in str(exc.value)


def test_create_reservation(service: CommerceService) -> None:
    service.create_sku("SKU-001", "Widget", 100)
    result = service.create_reservation("SKU-001", 10, "idempotency-key-1")
    assert result["sku_id"] == "SKU-001"
    assert result["quantity"] == 10
    assert result["status"] == ReservationStatus.PENDING


def test_create_reservation_insufficient_stock(service: CommerceService) -> None:
    service.create_sku("SKU-001", "Widget", 10)
    with pytest.raises(Exception) as exc:
        service.create_reservation("SKU-001", 20, "idempotency-key-1")
    assert "Insufficient stock" in str(exc.value)


def test_create_reservation_idempotent(service: CommerceService) -> None:
    service.create_sku("SKU-001", "Widget", 100)
    result1 = service.create_reservation("SKU-001", 10, "idempotency-key-1")
    result2 = service.create_reservation("SKU-001", 10, "idempotency-key-1")
    assert result1["reservation_id"] == result2["reservation_id"]


def test_confirm_reservation(service: CommerceService) -> None:
    service.create_sku("SKU-001", "Widget", 100)
    res = service.create_reservation("SKU-001", 10, "idempotency-key-1")
    result = service.confirm_reservation(res["reservation_id"])
    assert result["status"] == ReservationStatus.CONFIRMED
    assert result["confirmed_at"] is not None


def test_confirm_expired_reservation(
    service: CommerceService, db_session: Session
) -> None:
    service.create_sku("SKU-001", "Widget", 100)
    res = service.create_reservation("SKU-001", 10, "idempotency-key-1")

    repo = Repository(db_session)
    reservation = repo.get_reservation(res["reservation_id"])
    reservation.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db_session.commit()

    with pytest.raises(Exception) as exc:
        service.confirm_reservation(res["reservation_id"])
    assert "expired" in str(exc.value)


def test_cancel_reservation(service: CommerceService) -> None:
    service.create_sku("SKU-001", "Widget", 100)
    res = service.create_reservation("SKU-001", 10, "idempotency-key-1")
    result = service.cancel_reservation(res["reservation_id"])
    assert result["status"] == ReservationStatus.CANCELLED


def test_cancel_confirmed_reservation(service: CommerceService) -> None:
    service.create_sku("SKU-001", "Widget", 100)
    res = service.create_reservation("SKU-001", 10, "idempotency-key-1")
    service.confirm_reservation(res["reservation_id"])
    with pytest.raises(Exception) as exc:
        service.cancel_reservation(res["reservation_id"])
    assert "cannot cancel" in str(exc.value).lower()


def test_reserved_stock_tracking(service: CommerceService) -> None:
    service.create_sku("SKU-001", "Widget", 100)
    service.create_reservation("SKU-001", 30, "idempotency-key-1")

    repo = service.repo
    sku = repo.get_sku("SKU-001")
    assert sku.reserved_stock == 30
    assert sku.total_stock - sku.reserved_stock == 70


def test_list_orders(service: CommerceService) -> None:
    service.create_sku("SKU-001", "Widget", 100)
    res = service.create_reservation("SKU-001", 10, "idempotency-key-1")
    service.confirm_reservation(res["reservation_id"])

    result = service.list_orders(limit=10, offset=0)
    assert result["total"] == 1
    assert len(result["orders"]) == 1
    assert result["limit"] == 10
    assert result["offset"] == 0


def test_list_orders_pagination(service: CommerceService) -> None:
    service.create_sku("SKU-001", "Widget", 100)
    for i in range(5):
        res = service.create_reservation("SKU-001", 10, f"idempotency-key-{i}")
        service.confirm_reservation(res["reservation_id"])

    result = service.list_orders(limit=2, offset=0)
    assert result["total"] == 5
    assert len(result["orders"]) == 2

    result = service.list_orders(limit=2, offset=2)
    assert result["total"] == 5
    assert len(result["orders"]) == 2
