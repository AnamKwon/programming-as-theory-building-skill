import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock
from fastapi import HTTPException
from commerce_service.service import CommerceService
from commerce_service.repository import Repository


class MockReservation:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.sku_id = kwargs.get("sku_id", 1)
        self.quantity = kwargs.get("quantity", 10)
        self.state = kwargs.get("state", "pending")
        self.expires_at = kwargs.get("expires_at", datetime.utcnow() + timedelta(hours=1))
        self.created_at = kwargs.get("created_at", datetime.utcnow())


class MockSKU:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.sku_code = kwargs.get("sku_code", "ABC123")
        self.name = kwargs.get("name", "Test Product")
        self.stock_count = kwargs.get("stock_count", 100)


class MockOrder:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.sku_id = kwargs.get("sku_id", 1)
        self.quantity = kwargs.get("quantity", 10)
        self.state = kwargs.get("state", "reserved")
        self.created_at = kwargs.get("created_at", datetime.utcnow())


@pytest.fixture
def mock_repo():
    return Mock(spec=Repository)


@pytest.fixture
def service(mock_repo):
    return CommerceService(mock_repo)


def test_create_sku_success(service, mock_repo):
    sku = MockSKU(id=1, sku_code="SKU001", name="Widget")
    mock_repo.create_sku.return_value = sku

    result = service.create_sku("SKU001", "Widget", 100)

    assert result.id == 1
    assert result.sku_code == "SKU001"
    assert result.name == "Widget"
    mock_repo.create_sku.assert_called_once_with("SKU001", "Widget", 100)


def test_adjust_stock_success(service, mock_repo):
    sku = MockSKU(id=1, stock_count=110)
    mock_repo.update_sku_stock.return_value = sku

    result = service.adjust_stock(1, 10)

    assert result.stock_count == 110
    mock_repo.update_sku_stock.assert_called_once_with(1, 10)


def test_adjust_stock_sku_not_found(service, mock_repo):
    mock_repo.update_sku_stock.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        service.adjust_stock(999, 10)
    assert exc_info.value.status_code == 404


def test_create_reservation_success(service, mock_repo):
    sku = MockSKU(id=1, stock_count=100)
    reservation = MockReservation(id=1, sku_id=1, quantity=10)

    mock_repo.get_reservation_by_idempotency_key.return_value = None
    mock_repo.get_sku.return_value = sku
    mock_repo.create_reservation.return_value = reservation

    result = service.create_reservation(1, 10, "idempotency-123")

    assert result.id == 1
    assert result.state == "pending"
    assert result.quantity == 10
    mock_repo.create_reservation.assert_called_once()


def test_create_reservation_idempotent_retry(service, mock_repo):
    reservation = MockReservation(id=1, sku_id=1, quantity=10)
    mock_repo.get_reservation_by_idempotency_key.return_value = reservation

    result = service.create_reservation(1, 10, "idempotency-123")

    assert result.id == 1
    mock_repo.create_reservation.assert_not_called()


def test_create_reservation_idempotency_key_conflict(service, mock_repo):
    existing = MockReservation(id=1, sku_id=1, quantity=10)
    mock_repo.get_reservation_by_idempotency_key.return_value = existing

    with pytest.raises(HTTPException) as exc_info:
        service.create_reservation(2, 10, "idempotency-123")
    assert exc_info.value.status_code == 409


def test_create_reservation_insufficient_stock(service, mock_repo):
    sku = MockSKU(id=1, stock_count=5)
    mock_repo.get_reservation_by_idempotency_key.return_value = None
    mock_repo.get_sku.return_value = sku

    with pytest.raises(HTTPException) as exc_info:
        service.create_reservation(1, 10, "idempotency-123")
    assert exc_info.value.status_code == 400
    assert "Insufficient stock" in exc_info.value.detail


def test_create_reservation_sku_not_found(service, mock_repo):
    mock_repo.get_reservation_by_idempotency_key.return_value = None
    mock_repo.get_sku.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        service.create_reservation(999, 10, "idempotency-123")
    assert exc_info.value.status_code == 404


def test_confirm_reservation_success(service, mock_repo):
    sku = MockSKU(id=1, stock_count=100)
    reservation = MockReservation(id=1, sku_id=1, quantity=10, state="pending")
    order = MockOrder(id=1, sku_id=1, quantity=10, state="confirmed")

    mock_repo.get_reservation.return_value = reservation
    mock_repo.get_sku.return_value = sku
    mock_repo.create_order.return_value = order
    mock_repo.update_sku_stock.return_value = sku
    mock_repo.update_reservation_state.return_value = reservation

    res, order_resp = service.confirm_reservation(1)

    assert res.state == "pending"
    assert order_resp.state == "confirmed"
    mock_repo.update_sku_stock.assert_called_with(1, -10)


def test_confirm_reservation_expired(service, mock_repo):
    expired_time = datetime.utcnow() - timedelta(minutes=1)
    reservation = MockReservation(id=1, state="pending", expires_at=expired_time)
    mock_repo.get_reservation.return_value = reservation

    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(1)
    assert exc_info.value.status_code == 400
    assert "expired" in exc_info.value.detail


def test_confirm_reservation_not_pending(service, mock_repo):
    reservation = MockReservation(id=1, state="cancelled")
    mock_repo.get_reservation.return_value = reservation

    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(1)
    assert exc_info.value.status_code == 400
    assert "not in pending state" in exc_info.value.detail


def test_confirm_reservation_not_found(service, mock_repo):
    mock_repo.get_reservation.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        service.confirm_reservation(999)
    assert exc_info.value.status_code == 404


def test_cancel_reservation_success(service, mock_repo):
    reservation = MockReservation(id=1, state="pending")
    mock_repo.get_reservation.return_value = reservation
    mock_repo.update_reservation_state.return_value = reservation

    result = service.cancel_reservation(1)

    assert result.id == 1
    mock_repo.update_reservation_state.assert_called_once_with(1, "cancelled")


def test_cancel_reservation_already_cancelled(service, mock_repo):
    reservation = MockReservation(id=1, state="cancelled")
    mock_repo.get_reservation.return_value = reservation

    result = service.cancel_reservation(1)

    assert result.state == "cancelled"
    mock_repo.update_reservation_state.assert_not_called()


def test_cancel_reservation_not_found(service, mock_repo):
    mock_repo.get_reservation.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        service.cancel_reservation(999)
    assert exc_info.value.status_code == 404


def test_get_order_success(service, mock_repo):
    order = MockOrder(id=1)
    mock_repo.get_order.return_value = order

    result = service.get_order(1)

    assert result.id == 1
    mock_repo.get_order.assert_called_once_with(1)


def test_get_order_not_found(service, mock_repo):
    mock_repo.get_order.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        service.get_order(999)
    assert exc_info.value.status_code == 404


def test_list_orders_success(service, mock_repo):
    orders = [MockOrder(id=1), MockOrder(id=2)]
    mock_repo.list_orders.return_value = (orders, 2)

    results, total = service.list_orders(1, 10)

    assert len(results) == 2
    assert total == 2
    mock_repo.list_orders.assert_called_once_with(1, 10)


def test_list_orders_pagination(service, mock_repo):
    orders = [MockOrder(id=11), MockOrder(id=12)]
    mock_repo.list_orders.return_value = (orders, 100)

    results, total = service.list_orders(2, 10)

    assert len(results) == 2
    assert total == 100
    mock_repo.list_orders.assert_called_once_with(2, 10)


def test_list_orders_invalid_page(service, mock_repo):
    with pytest.raises(HTTPException) as exc_info:
        service.list_orders(0, 10)
    assert exc_info.value.status_code == 400


def test_list_orders_invalid_page_size(service, mock_repo):
    with pytest.raises(HTTPException) as exc_info:
        service.list_orders(1, 0)
    assert exc_info.value.status_code == 400
