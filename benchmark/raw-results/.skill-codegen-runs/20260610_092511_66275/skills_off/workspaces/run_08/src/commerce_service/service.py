from datetime import datetime, timedelta
from typing import Optional

from .models import ReservationStatus, OrderStatus
from .repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class InvalidStateTransitionError(Exception):
    pass


class Service:
    RESERVATION_TTL_MINUTES = 30

    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, code: str, name: str, description: Optional[str], initial_stock: int):
        return self.repo.create_sku(code, name, description, initial_stock)

    def adjust_stock(self, sku_id: int, quantity_change: int):
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        return self.repo.update_sku_stock(sku_id, quantity_change)

    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        idempotency_key: Optional[str] = None,
    ):
        if idempotency_key:
            existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
            if existing:
                return existing

        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        available_stock = sku.stock_quantity
        reserved_quantity = sum(
            r.quantity for r in self.repo.list_pending_reservations_for_sku(sku_id)
        )
        available_stock -= reserved_quantity

        if available_stock < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for SKU {sku_id}. Available: {available_stock}, Requested: {quantity}"
            )

        expires_at = datetime.utcnow() + timedelta(minutes=self.RESERVATION_TTL_MINUTES)
        return self.repo.create_reservation(sku_id, quantity, expires_at, idempotency_key)

    def confirm_reservation(self, reservation_id: int):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if datetime.utcnow() > reservation.expires_at:
            self.repo.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
            raise ReservationExpiredError(f"Reservation {reservation_id} expired")

        if reservation.status != ReservationStatus.PENDING:
            raise InvalidStateTransitionError(
                f"Cannot confirm reservation in {reservation.status} status"
            )

        return self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)

    def cancel_reservation(self, reservation_id: int):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status == ReservationStatus.CANCELLED:
            return reservation

        if reservation.status not in [ReservationStatus.PENDING, ReservationStatus.CONFIRMED]:
            raise InvalidStateTransitionError(
                f"Cannot cancel reservation in {reservation.status} status"
            )

        return self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)

    def cleanup_expired_reservations(self):
        expired = self.repo.list_expired_pending_reservations(datetime.utcnow())
        for reservation in expired:
            self.repo.update_reservation_status(reservation.id, ReservationStatus.EXPIRED)
        return len(expired)

    def get_orders(self, limit: int = 10, offset: int = 0):
        orders, total = self.repo.list_orders(limit, offset)
        return orders, total
