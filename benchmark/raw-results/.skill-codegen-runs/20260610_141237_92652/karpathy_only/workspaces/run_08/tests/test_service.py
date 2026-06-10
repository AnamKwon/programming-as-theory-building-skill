import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.commerce_service.models import Base
from src.commerce_service.service import CommerceService
from fastapi import HTTPException

SQLALCHEMY_DATABASE_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(bind=engine)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture
def db():
    """Get fresh database session for each test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def service(db):
    """Get service instance."""
    return CommerceService(db)

def test_create_sku(service):
    """Test SKU creation."""
    result = service.create_sku("PROD-001", 100)
    assert result["sku"] == "PROD-001"
    assert result["available_stock"] == 100

def test_adjust_stock_increase(service):
    """Test stock increase."""
    service.create_sku("PROD-001", 100)
    result = service.adjust_stock("PROD-001", 50)
    assert result["available_stock"] == 150

def test_adjust_stock_decrease(service):
    """Test stock decrease."""
    service.create_sku("PROD-001", 100)
    result = service.adjust_stock("PROD-001", -30)
    assert result["available_stock"] == 70

def test_adjust_stock_nonexistent_sku(service):
    """Test stock adjustment for nonexistent SKU."""
    with pytest.raises(HTTPException) as exc_info:
        service.adjust_stock("NONEXISTENT", 50)
    assert exc_info.value.status_code == 404

def test_create_reservation_success(service):
    """Test successful reservation creation."""
    service.create_sku("PROD-001", 100)
    result, status_code = service.create_reservation("PROD-001", 10, "key-001")
    assert status_code == 201
    assert result["sku"] == "PROD-001"
    assert result["quantity"] == 10
    assert result["status"] == "PENDING"

def test_create_reservation_insufficient_stock(service):
    """Test reservation with insufficient stock."""
    service.create_sku("PROD-001", 100)
    with pytest.raises(HTTPException) as exc_info:
        service.create_reservation("PROD-001", 150, "key-001")
    assert exc_info.value.status_code == 400
    assert "Insufficient stock" in exc_info.value.detail

def test_create_reservation_nonexistent_sku(service):
    """Test reservation for nonexistent SKU."""
    with pytest.raises(HTTPException) as exc_info:
        service.create_reservation("NONEXISTENT", 10, "key-001")
    assert exc_info.value.status_code == 404

def test_create_reservation_idempotency(service):
    """Test reservation idempotency."""
    service.create_sku("PROD-001", 100)

    result1, status1 = service.create_reservation("PROD-001", 10, "key-001")
    res_id = result1["id"]

    result2, status2 = service.create_reservation("PROD-001", 10, "key-001")

    assert result1 == result2
    assert result2["id"] == res_id

def test_confirm_reservation_success(service):
    """Test successful reservation confirmation."""
    service.create_sku("PROD-001", 100)
    res, _ = service.create_reservation("PROD-001", 10, "key-001")
    res_id = res["id"]

    result = service.confirm_reservation(res_id)
    assert "id" in result
    assert result["reservation_id"] == res_id

def test_confirm_reservation_nonexistent(service):
    """Test confirmation of nonexistent reservation."""
    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(999)
    assert exc_info.value.status_code == 404

def test_confirm_reservation_not_pending(service):
    """Test confirmation of non-PENDING reservation."""
    service.create_sku("PROD-001", 100)
    res, _ = service.create_reservation("PROD-001", 10, "key-001")
    res_id = res["id"]

    service.confirm_reservation(res_id)

    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(res_id)
    assert exc_info.value.status_code == 400
    assert "not PENDING" in exc_info.value.detail

def test_confirm_reservation_expired(service, db):
    """Test confirmation of expired reservation."""
    service.create_sku("PROD-001", 100)
    res, _ = service.create_reservation("PROD-001", 10, "key-001")
    res_id = res["id"]

    reservation = db.query(Base.registry.mappers[0].class_).filter_by(id=res_id).first()
    old_time = datetime.now(timezone.utc) - timedelta(seconds=301)
    reservation.created_at = old_time.replace(tzinfo=None)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(res_id)
    assert exc_info.value.status_code == 400
    assert "expired" in exc_info.value.detail.lower()

def test_cancel_reservation_success(service):
    """Test successful reservation cancellation."""
    service.create_sku("PROD-001", 100)
    res, _ = service.create_reservation("PROD-001", 10, "key-001")
    res_id = res["id"]

    result = service.cancel_reservation(res_id)
    assert result["status"] == "CANCELLED"
    assert result["restored_quantity"] == 10

def test_cancel_reservation_nonexistent(service):
    """Test cancellation of nonexistent reservation."""
    with pytest.raises(HTTPException) as exc_info:
        service.cancel_reservation(999)
    assert exc_info.value.status_code == 404

def test_cancel_reservation_not_pending(service):
    """Test cancellation of non-PENDING reservation."""
    service.create_sku("PROD-001", 100)
    res, _ = service.create_reservation("PROD-001", 10, "key-001")
    res_id = res["id"]

    service.confirm_reservation(res_id)

    with pytest.raises(HTTPException) as exc_info:
        service.cancel_reservation(res_id)
    assert exc_info.value.status_code == 400
    assert "not PENDING" in exc_info.value.detail

def test_list_orders_empty(service):
    """Test listing orders when empty."""
    result = service.list_orders(1, 10)
    assert result["total"] == 0
    assert result["items"] == []
    assert result["page"] == 1
    assert result["size"] == 10

def test_list_orders_with_items(service):
    """Test listing orders."""
    service.create_sku("PROD-001", 100)

    for i in range(5):
        res, _ = service.create_reservation("PROD-001", 1, f"key-{i}")
        res_id = res["id"]
        service.confirm_reservation(res_id)

    result = service.list_orders(1, 10)
    assert result["total"] == 5
    assert len(result["items"]) == 5

def test_list_orders_pagination(service):
    """Test orders pagination."""
    service.create_sku("PROD-001", 100)

    for i in range(15):
        res, _ = service.create_reservation("PROD-001", 1, f"key-{i}")
        res_id = res["id"]
        service.confirm_reservation(res_id)

    result1 = service.list_orders(1, 10)
    assert result1["page"] == 1
    assert result1["size"] == 10
    assert result1["total"] == 15
    assert len(result1["items"]) == 10

    result2 = service.list_orders(2, 10)
    assert result2["page"] == 2
    assert len(result2["items"]) == 5

def test_stock_deduction_on_reservation(service):
    """Test that stock is deducted on reservation."""
    service.create_sku("PROD-001", 100)
    service.create_reservation("PROD-001", 30, "key-001")

    stock = service.adjust_stock("PROD-001", 0)
    assert stock["available_stock"] == 70

def test_stock_restoration_on_cancel(service):
    """Test that stock is restored on cancellation."""
    service.create_sku("PROD-001", 100)
    res, _ = service.create_reservation("PROD-001", 30, "key-001")
    res_id = res["id"]

    service.cancel_reservation(res_id)

    stock = service.adjust_stock("PROD-001", 0)
    assert stock["available_stock"] == 100

def test_stock_not_restored_on_confirm(service):
    """Test that stock is not restored on confirmation."""
    service.create_sku("PROD-001", 100)
    res, _ = service.create_reservation("PROD-001", 30, "key-001")
    res_id = res["id"]

    service.confirm_reservation(res_id)

    stock = service.adjust_stock("PROD-001", 0)
    assert stock["available_stock"] == 70
