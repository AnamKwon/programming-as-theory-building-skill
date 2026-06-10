"""Business logic for inventory and order management."""

from datetime import datetime, timedelta
from typing import Optional

from commerce_service.models import (
    ReservationStatus,
    OrderStatus,
    SKUResponse,
    ReservationResponse,
    OrderResponse,
)
from commerce_service.repository import Repository


RESERVATION_EXPIRY_MINUTES = 15

def utc_now():
    return datetime.utcnow()


class ServiceError(Exception):
    """Base exception for service layer."""
    pass


class InsufficientStockError(ServiceError):
    """Raised when stock is not available for reservation."""
    pass


class ReservationNotFoundError(ServiceError):
    """Raised when reservation does not exist."""
    pass


class ReservationExpiredError(ServiceError):
    """Raised when reservation has expired."""
    pass


class InvalidStateTransitionError(ServiceError):
    """Raised when reservation status transition is invalid."""
    pass


class OrderNotFoundError(ServiceError):
    """Raised when order does not exist."""
    pass


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku_code: str, name: str, initial_stock: int) -> SKUResponse:
        sku = self.repo.create_sku(sku_code, name, initial_stock)
        return SKUResponse.from_orm(sku)

    def adjust_stock(self, sku_id: int, quantity_delta: int) -> SKUResponse:
        sku = self.repo.update_sku_stock(sku_id, quantity_delta)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        return SKUResponse.from_orm(sku)

    def reserve_stock(
        self,
        sku_id: int,
        quantity: int,
        idempotency_key: Optional[str] = None,
    ) -> ReservationResponse:
        if idempotency_key:
            existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
            if existing:
                if existing.status == ReservationStatus.EXPIRED:
                    raise ReservationExpiredError(
                        f"Idempotent request already expired: {idempotency_key}"
                    )
                return ReservationResponse.from_orm(existing)

        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        if sku.stock_count < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for SKU {sku_id}: available={sku.stock_count}, requested={quantity}"
            )

        expires_at = utc_now() + timedelta(minutes=RESERVATION_EXPIRY_MINUTES)
        reservation = self.repo.create_reservation(
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )

        self.repo.update_sku_stock(sku_id, -quantity)

        return ReservationResponse.from_orm(reservation)

    def confirm_reservation(self, reservation_id: int) -> OrderResponse:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if utc_now() > reservation.expires_at:
            self.repo.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        if reservation.status != ReservationStatus.PENDING:
            raise InvalidStateTransitionError(
                f"Cannot confirm reservation in {reservation.status} state"
            )

        order = self.repo.create_order()
        self.repo.update_reservation_order_id(reservation_id, order.id)
        self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)
        self.repo.update_order_status(order.id, OrderStatus.CONFIRMED)

        return OrderResponse.from_orm(order)

    def cancel_reservation(self, reservation_id: int) -> ReservationResponse:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status in (ReservationStatus.CONFIRMED, ReservationStatus.CANCELLED):
            raise InvalidStateTransitionError(
                f"Cannot cancel reservation in {reservation.status} state"
            )

        if reservation.status == ReservationStatus.EXPIRED:
            self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)
        else:
            self.repo.update_sku_stock(reservation.sku_id, reservation.quantity)
            self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)

        updated = self.repo.get_reservation(reservation_id)
        return ReservationResponse.from_orm(updated)

    def get_order(self, order_id: int) -> OrderResponse:
        order = self.repo.get_order(order_id)
        if not order:
            raise OrderNotFoundError(f"Order {order_id} not found")
        return OrderResponse.from_orm(order)

    def list_orders(self, offset: int, limit: int) -> tuple[list[OrderResponse], int]:
        orders, total = self.repo.list_orders(offset=offset, limit=limit)
        return [OrderResponse.from_orm(o) for o in orders], total
