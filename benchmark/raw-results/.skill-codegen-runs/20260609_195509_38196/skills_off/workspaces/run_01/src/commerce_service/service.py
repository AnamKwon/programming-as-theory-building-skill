import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .models import (
    OrderResponse,
    OrderStatus,
    OrderTable,
    ReservationResponse,
    ReservationStatus,
    ReservationTable,
    SKUResponse,
    SKUTable,
)
from .repository import Repository


class ServiceError(Exception):
    """Base service exception."""

    pass


class InsufficientStockError(ServiceError):
    """Raised when stock is insufficient for reservation."""

    pass


class ReservationNotFoundError(ServiceError):
    """Raised when reservation does not exist."""

    pass


class ReservationExpiredError(ServiceError):
    """Raised when reservation has expired."""

    pass


class ReservationAlreadyConfirmedError(ServiceError):
    """Raised when trying to confirm an already confirmed reservation."""

    pass


class SKUNotFoundError(ServiceError):
    """Raised when SKU does not exist."""

    pass


class IdempotencyError(ServiceError):
    """Raised when idempotency key already used with different parameters."""

    pass


class CommerceService:
    def __init__(self, db: Session):
        self.repo = Repository(db)

    def create_sku(self, sku_id: str, name: str, available_stock: int) -> SKUResponse:
        sku = self.repo.create_sku(sku_id, name, available_stock)
        return self._sku_to_response(sku)

    def adjust_stock(self, sku_id: str, delta: int) -> SKUResponse:
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        if sku.available_stock + delta < 0:
            raise InsufficientStockError(
                f"Cannot adjust stock below 0 for SKU {sku_id}"
            )

        sku = self.repo.update_sku_stock(sku_id, delta, 0)
        return self._sku_to_response(sku)

    def create_reservation(
        self, sku_id: str, quantity: int, duration_minutes: int
    ) -> ReservationResponse:
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        available = sku.available_stock
        if available < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for SKU {sku_id}: available={available}, requested={quantity}"
            )

        reservation_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=duration_minutes)

        self.repo.update_sku_stock(sku_id, -quantity, quantity)
        reservation = self.repo.create_reservation(
            reservation_id, sku_id, quantity, expires_at
        )

        return self._reservation_to_response(reservation)

    def confirm_reservation(
        self, reservation_id: str, idempotency_key: str
    ) -> tuple[ReservationResponse, str]:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if datetime.utcnow() > reservation.expires_at:
            self.repo.cancel_reservation(reservation_id)
            self.repo.update_sku_stock(
                reservation.sku_id, reservation.quantity, -reservation.quantity
            )
            raise ReservationExpiredError(
                f"Reservation {reservation_id} expired at {reservation.expires_at}"
            )

        if reservation.status != ReservationStatus.PENDING:
            raise ReservationAlreadyConfirmedError(
                f"Reservation {reservation_id} is already {reservation.status}"
            )

        existing_order = self.repo.get_order_by_idempotency_key(idempotency_key)
        if existing_order:
            return self._reservation_to_response(reservation), existing_order.id

        order_id = str(uuid.uuid4())
        self.repo.confirm_reservation(reservation_id)
        order = self.repo.create_order(
            order_id,
            reservation_id,
            reservation.sku_id,
            reservation.quantity,
            idempotency_key,
        )
        self.repo.confirm_order(order_id)

        return self._reservation_to_response(reservation), order.id

    def cancel_reservation(self, reservation_id: str) -> ReservationResponse:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status == ReservationStatus.CANCELLED:
            return self._reservation_to_response(reservation)

        self.repo.cancel_reservation(reservation_id)
        self.repo.update_sku_stock(
            reservation.sku_id, reservation.quantity, -reservation.quantity
        )

        return self._reservation_to_response(reservation)

    def get_order(self, order_id: str) -> OrderResponse:
        order = self.repo.get_order(order_id)
        if not order:
            raise Exception(f"Order {order_id} not found")
        return self._order_to_response(order)

    def list_orders(self, skip: int = 0, limit: int = 20) -> dict:
        orders, total = self.repo.list_orders(skip, limit)
        return {
            "orders": [self._order_to_response(o) for o in orders],
            "total": total,
            "skip": skip,
            "limit": limit,
        }

    def cleanup_expired_reservations(self) -> int:
        """Auto-expire pending reservations past their expiration time."""
        now = datetime.utcnow()
        expired = self.repo.get_expired_pending_reservations(now)

        for reservation in expired:
            self.repo.cancel_reservation(reservation.id)
            self.repo.update_sku_stock(
                reservation.sku_id, reservation.quantity, -reservation.quantity
            )

        return len(expired)

    @staticmethod
    def _sku_to_response(sku: SKUTable) -> SKUResponse:
        return SKUResponse(
            id=sku.id,
            name=sku.name,
            available_stock=sku.available_stock,
            reserved_stock=sku.reserved_stock,
            created_at=sku.created_at,
        )

    @staticmethod
    def _reservation_to_response(reservation: ReservationTable) -> ReservationResponse:
        return ReservationResponse(
            id=reservation.id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            status=ReservationStatus(reservation.status),
            expires_at=reservation.expires_at,
            created_at=reservation.created_at,
            confirmed_at=reservation.confirmed_at,
        )

    @staticmethod
    def _order_to_response(order: OrderTable) -> OrderResponse:
        return OrderResponse(
            id=order.id,
            reservation_id=order.reservation_id,
            sku_id=order.sku_id,
            quantity=order.quantity,
            status=OrderStatus(order.status),
            created_at=order.created_at,
            confirmed_at=order.confirmed_at,
        )
