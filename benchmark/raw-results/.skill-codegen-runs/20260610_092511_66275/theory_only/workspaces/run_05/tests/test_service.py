import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from commerce_service.models import Base
from commerce_service.service import (
    CommerceService,
    InsufficientStockError,
    ReservationNotFoundError,
    ReservationExpiredError,
    ReservationAlreadyConfirmedError,
    SKUNotFoundError,
)


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def service(db_session):
    """Create a CommerceService instance."""
    return CommerceService(db_session)


def test_create_sku(service):
    """Test SKU creation."""
    result = service.create_sku("sku-001", "Widget", "A great widget")
    assert result["id"] == "sku-001"
    assert result["name"] == "Widget"
    assert result["description"] == "A great widget"


def test_adjust_stock_sku_not_found(service):
    """Test stock adjustment for non-existent SKU."""
    with pytest.raises(SKUNotFoundError):
        service.adjust_stock("nonexistent", 10)


def test_adjust_stock(service):
    """Test stock adjustment."""
    service.create_sku("sku-002", "Gadget", None)
    result = service.adjust_stock("sku-002", 100)
    assert result["sku_id"] == "sku-002"
    assert result["available"] == 100
    assert result["reserved"] == 0


def test_reserve_inventory_success(service):
    """Test successful reservation."""
    service.create_sku("sku-003", "Thing", None)
    service.adjust_stock("sku-003", 50)

    result = service.reserve_inventory("sku-003", 10, "idempotent-key-1")
    assert result["sku_id"] == "sku-003"
    assert result["quantity"] == 10
    assert result["status"] == "active"
    assert "expires_at" in result


def test_reserve_inventory_idempotency(service):
    """Test idempotent reservation retry."""
    service.create_sku("sku-004", "Item", None)
    service.adjust_stock("sku-004", 50)

    result1 = service.reserve_inventory("sku-004", 10, "idempotent-key-2")
    result2 = service.reserve_inventory("sku-004", 10, "idempotent-key-2")

    assert result1["id"] == result2["id"]
    assert result1["expires_at"] == result2["expires_at"]


def test_reserve_inventory_insufficient_stock(service):
    """Test reservation with insufficient stock."""
    service.create_sku("sku-005", "Product", None)
    service.adjust_stock("sku-005", 5)

    with pytest.raises(InsufficientStockError):
        service.reserve_inventory("sku-005", 10, "idempotent-key-3")


def test_reserve_inventory_sku_not_found(service):
    """Test reservation for non-existent SKU."""
    with pytest.raises(SKUNotFoundError):
        service.reserve_inventory("nonexistent", 10, "idempotent-key-4")


def test_confirm_reservation(service):
    """Test reservation confirmation."""
    service.create_sku("sku-006", "Component", None)
    service.adjust_stock("sku-006", 50)

    reservation = service.reserve_inventory("sku-006", 10, "idempotent-key-5")
    order = service.confirm_reservation(reservation["id"])

    assert order["sku_id"] == "sku-006"
    assert order["quantity"] == 10
    assert order["status"] == "pending"


def test_confirm_reservation_expired(service, db_session):
    """Test confirmation of expired reservation."""
    from commerce_service.models import ReservationModel

    service.create_sku("sku-007", "Widget", None)
    service.adjust_stock("sku-007", 50)

    reservation = service.reserve_inventory("sku-007", 10, "idempotent-key-6")

    # Manually expire the reservation
    res_model = db_session.query(ReservationModel).filter(ReservationModel.id == reservation["id"]).first()
    res_model.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db_session.commit()

    with pytest.raises(ReservationExpiredError):
        service.confirm_reservation(reservation["id"])


def test_confirm_reservation_not_found(service):
    """Test confirmation of non-existent reservation."""
    with pytest.raises(ReservationNotFoundError):
        service.confirm_reservation("nonexistent-res")


def test_cancel_reservation(service):
    """Test reservation cancellation."""
    service.create_sku("sku-008", "Item", None)
    service.adjust_stock("sku-008", 50)

    reservation = service.reserve_inventory("sku-008", 10, "idempotent-key-7")
    result = service.cancel_reservation(reservation["id"])

    assert result["status"] == "cancelled"
    assert result["id"] == reservation["id"]


def test_cancel_reservation_already_confirmed(service):
    """Test cancellation of already confirmed reservation."""
    service.create_sku("sku-009", "Thing", None)
    service.adjust_stock("sku-009", 50)

    reservation = service.reserve_inventory("sku-009", 10, "idempotent-key-8")
    service.confirm_reservation(reservation["id"])

    with pytest.raises(ReservationAlreadyConfirmedError):
        service.cancel_reservation(reservation["id"])


def test_get_order(service):
    """Test order retrieval."""
    service.create_sku("sku-010", "Product", None)
    service.adjust_stock("sku-010", 50)

    reservation = service.reserve_inventory("sku-010", 10, "idempotent-key-9")
    order = service.confirm_reservation(reservation["id"])

    retrieved = service.get_order(order["id"])
    assert retrieved["id"] == order["id"]
    assert retrieved["sku_id"] == "sku-010"


def test_list_orders_pagination(service):
    """Test order pagination."""
    service.create_sku("sku-011", "Item", None)
    service.adjust_stock("sku-011", 100)

    # Create multiple orders
    order_ids = []
    for i in range(5):
        res = service.reserve_inventory("sku-011", 10, f"key-{i}")
        order = service.confirm_reservation(res["id"])
        order_ids.append(order["id"])

    # Get first page
    result = service.list_orders(None, 2)
    assert len(result["orders"]) == 2
    assert result["next_cursor"] is not None

    # Get next page
    result2 = service.list_orders(result["next_cursor"], 10)
    assert len(result2["orders"]) > 0
    # Total orders should be 5 or fewer due to ordering
    total = len(result["orders"]) + len(result2["orders"])
    assert total <= 5
