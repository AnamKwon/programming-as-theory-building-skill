"""Tests for the service layer."""

import pytest
import tempfile
from decimal import Decimal
from datetime import datetime, timedelta
from pathlib import Path

from src.commerce_service.repository import Repository
from src.commerce_service.service import CommerceService
from src.commerce_service.models import (
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield str(db_path)


@pytest.fixture
def repo(temp_db):
    """Create a repository with temporary database."""
    return Repository(db_path=temp_db)


@pytest.fixture
def service(repo):
    """Create a service instance."""
    return CommerceService(repo)


class TestSKUOperations:
    def test_create_sku(self, service):
        request = CreateSKURequest(
            sku_id="WIDGET-001",
            name="Standard Widget",
            unit_price=Decimal("19.99"),
        )
        result = service.create_sku(request)

        assert result["sku_id"] == "WIDGET-001"
        assert result["name"] == "Standard Widget"
        assert result["unit_price"] == Decimal("19.99")
        assert result["stock_quantity"] == 0

    def test_create_duplicate_sku_fails(self, service):
        request = CreateSKURequest(
            sku_id="WIDGET-001",
            name="Widget",
            unit_price=Decimal("19.99"),
        )
        service.create_sku(request)

        with pytest.raises(Exception):  # HTTPException with 409
            service.create_sku(request)

    def test_get_sku(self, service):
        request = CreateSKURequest(
            sku_id="WIDGET-001",
            name="Widget",
            unit_price=Decimal("19.99"),
        )
        service.create_sku(request)

        result = service.get_sku("WIDGET-001")
        assert result["sku_id"] == "WIDGET-001"
        assert result["name"] == "Widget"

    def test_get_nonexistent_sku_fails(self, service):
        with pytest.raises(Exception):  # HTTPException with 404
            service.get_sku("NONEXISTENT")

    def test_adjust_stock_increase(self, service):
        service.create_sku(CreateSKURequest(sku_id="SKU-001", name="Item", unit_price=Decimal("10.00")))
        result = service.adjust_stock(AdjustStockRequest(sku_id="SKU-001", quantity_delta=50))

        assert result["previous_quantity"] == 0
        assert result["new_quantity"] == 50

    def test_adjust_stock_negative_fails(self, service):
        service.create_sku(CreateSKURequest(sku_id="SKU-001", name="Item", unit_price=Decimal("10.00")))

        with pytest.raises(Exception):  # HTTPException with 400
            service.adjust_stock(AdjustStockRequest(sku_id="SKU-001", quantity_delta=-100))


class TestReservations:
    def test_create_reservation_success(self, service):
        service.create_sku(CreateSKURequest(sku_id="SKU-001", name="Item", unit_price=Decimal("10.00")))
        service.adjust_stock(AdjustStockRequest(sku_id="SKU-001", quantity_delta=100))

        result = service.create_reservation(
            CreateReservationRequest(
                sku_id="SKU-001",
                quantity=50,
                idempotency_key="order-123",
            )
        )

        assert result.sku_id == "SKU-001"
        assert result.quantity == 50
        assert result.status.value == "pending"
        assert result.reservation_id is not None

    def test_create_reservation_insufficient_stock(self, service):
        service.create_sku(CreateSKURequest(sku_id="SKU-001", name="Item", unit_price=Decimal("10.00")))
        service.adjust_stock(AdjustStockRequest(sku_id="SKU-001", quantity_delta=20))

        with pytest.raises(Exception):  # HTTPException with 409
            service.create_reservation(
                CreateReservationRequest(
                    sku_id="SKU-001",
                    quantity=50,
                    idempotency_key="order-123",
                )
            )

    def test_create_reservation_nonexistent_sku(self, service):
        with pytest.raises(Exception):  # HTTPException with 404
            service.create_reservation(
                CreateReservationRequest(
                    sku_id="NONEXISTENT",
                    quantity=50,
                    idempotency_key="order-123",
                )
            )

    def test_idempotent_reservation_creation(self, service):
        service.create_sku(CreateSKURequest(sku_id="SKU-001", name="Item", unit_price=Decimal("10.00")))
        service.adjust_stock(AdjustStockRequest(sku_id="SKU-001", quantity_delta=100))

        req = CreateReservationRequest(
            sku_id="SKU-001",
            quantity=50,
            idempotency_key="order-123",
        )
        result1 = service.create_reservation(req)
        result2 = service.create_reservation(req)

        assert result1.reservation_id == result2.reservation_id

    def test_confirm_reservation_success(self, service):
        service.create_sku(CreateSKURequest(sku_id="SKU-001", name="Item", unit_price=Decimal("10.00")))
        service.adjust_stock(AdjustStockRequest(sku_id="SKU-001", quantity_delta=100))

        res = service.create_reservation(
            CreateReservationRequest(
                sku_id="SKU-001",
                quantity=50,
                idempotency_key="order-123",
            )
        )

        confirmed = service.confirm_reservation(res.reservation_id)
        assert confirmed.status.value == "confirmed"

        # Verify stock was reserved
        sku = service.get_sku("SKU-001")
        assert sku["stock_quantity"] == 50  # 100 - 50

    def test_confirm_nonexistent_reservation_fails(self, service):
        with pytest.raises(Exception):  # HTTPException with 404
            service.confirm_reservation("nonexistent-id")

    def test_confirm_expired_reservation_fails(self, service, repo):
        service.create_sku(CreateSKURequest(sku_id="SKU-001", name="Item", unit_price=Decimal("10.00")))
        service.adjust_stock(AdjustStockRequest(sku_id="SKU-001", quantity_delta=100))

        # Create reservation and manually expire it
        res = service.create_reservation(
            CreateReservationRequest(
                sku_id="SKU-001",
                quantity=50,
                idempotency_key="order-123",
            )
        )

        # Manually set expiration to past
        repo_res = repo.get_reservation(res.reservation_id)
        repo._get_connection().execute(
            "UPDATE reservations SET expires_at = ? WHERE reservation_id = ?",
            ((datetime.now() - timedelta(minutes=1)).isoformat(), res.reservation_id),
        )
        repo._get_connection().commit()

        with pytest.raises(Exception):  # HTTPException with 410
            service.confirm_reservation(res.reservation_id)

    def test_cancel_pending_reservation(self, service):
        service.create_sku(CreateSKURequest(sku_id="SKU-001", name="Item", unit_price=Decimal("10.00")))
        service.adjust_stock(AdjustStockRequest(sku_id="SKU-001", quantity_delta=100))

        res = service.create_reservation(
            CreateReservationRequest(
                sku_id="SKU-001",
                quantity=50,
                idempotency_key="order-123",
            )
        )

        cancelled = service.cancel_reservation(res.reservation_id)
        assert cancelled.status.value == "cancelled"

    def test_cancel_confirmed_reservation_fails(self, service):
        service.create_sku(CreateSKURequest(sku_id="SKU-001", name="Item", unit_price=Decimal("10.00")))
        service.adjust_stock(AdjustStockRequest(sku_id="SKU-001", quantity_delta=100))

        res = service.create_reservation(
            CreateReservationRequest(
                sku_id="SKU-001",
                quantity=50,
                idempotency_key="order-123",
            )
        )
        service.confirm_reservation(res.reservation_id)

        with pytest.raises(Exception):  # HTTPException with 400
            service.cancel_reservation(res.reservation_id)


class TestOrders:
    def test_list_orders_empty(self, service):
        result = service.list_orders(page=1, page_size=20)
        assert result["total"] == 0
        assert len(result["items"]) == 0
        assert result["has_more"] is False

    def test_list_orders_pagination(self, service):
        service.create_sku(CreateSKURequest(sku_id="SKU-001", name="Item", unit_price=Decimal("10.00")))
        service.adjust_stock(AdjustStockRequest(sku_id="SKU-001", quantity_delta=1000))

        # Create and confirm multiple reservations
        for i in range(25):
            res = service.create_reservation(
                CreateReservationRequest(
                    sku_id="SKU-001",
                    quantity=10,
                    idempotency_key=f"order-{i}",
                )
            )
            service.confirm_reservation(res.reservation_id)

        # Page 1
        page1 = service.list_orders(page=1, page_size=20)
        assert len(page1["items"]) == 20
        assert page1["total"] == 25
        assert page1["has_more"] is True
        assert page1["page"] == 1

        # Page 2
        page2 = service.list_orders(page=2, page_size=20)
        assert len(page2["items"]) == 5
        assert page2["has_more"] is False
        assert page2["page"] == 2

    def test_get_order(self, service):
        service.create_sku(CreateSKURequest(sku_id="SKU-001", name="Item", unit_price=Decimal("10.00")))
        service.adjust_stock(AdjustStockRequest(sku_id="SKU-001", quantity_delta=100))

        res = service.create_reservation(
            CreateReservationRequest(
                sku_id="SKU-001",
                quantity=50,
                idempotency_key="order-123",
            )
        )
        confirmed = service.confirm_reservation(res.reservation_id)

        # Find order (we need to list them since confirm doesn't return order_id)
        orders = service.list_orders(page=1, page_size=20)
        assert orders["total"] == 1
        order = orders["items"][0]

        # Get the order
        fetched = service.get_order(order.order_id)
        assert fetched.reservation_id == res.reservation_id
        assert fetched.sku_id == "SKU-001"
        assert fetched.quantity == 50
