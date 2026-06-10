from datetime import datetime, timedelta
from uuid import uuid4
from typing import Optional

from .models import ReservationStatus, OrderStatus
from .repository import Repository


class ReservationExpiredError(Exception):
    pass


class InsufficientStockError(Exception):
    pass


class IdempotencyError(Exception):
    pass


class InvalidStateError(Exception):
    pass


class Service:
    RESERVATION_TTL_SECONDS = 300

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku_id: str, quantity: int):
        existing = self.repo.get_sku(sku_id)
        if existing:
            raise ValueError(f"SKU {sku_id} already exists")
        return self.repo.create_sku(sku_id, quantity)

    def adjust_stock(self, sku_id: str, adjustment: int):
        return self.repo.update_stock(sku_id, adjustment)

    def create_reservation(
        self, sku_id: str, quantity: int, idempotency_key: Optional[str] = None
    ):
        if idempotency_key:
            existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
            if existing:
                if existing.status == ReservationStatus.EXPIRED:
                    raise ReservationExpiredError(f"Reservation {existing.reservation_id} has expired")
                if existing.status == ReservationStatus.CANCELLED:
                    raise IdempotencyError(f"Idempotency key {idempotency_key} was cancelled")
                return existing

        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        if sku.quantity < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for {sku_id}: needed {quantity}, available {sku.quantity}"
            )

        reservation_id = str(uuid4())
        expires_at = datetime.utcnow() + timedelta(seconds=self.RESERVATION_TTL_SECONDS)

        return self.repo.create_reservation(
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )

    def confirm_reservation(self, reservation_id: str):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if datetime.utcnow() > reservation.expires_at:
            if reservation.status == ReservationStatus.PENDING:
                self.repo.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        if reservation.status != ReservationStatus.PENDING:
            raise InvalidStateError(
                f"Cannot confirm reservation in {reservation.status} state"
            )

        self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)

        order_id = str(uuid4())
        order = self.repo.create_order(
            order_id=order_id,
            reservation_id=reservation_id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
        )

        self.repo.update_stock(reservation.sku_id, -reservation.quantity)

        return order

    def cancel_reservation(self, reservation_id: str):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status == ReservationStatus.CONFIRMED:
            raise InvalidStateError("Cannot cancel a confirmed reservation")

        if reservation.status == ReservationStatus.EXPIRED:
            raise InvalidStateError("Cannot cancel an expired reservation")

        self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)
        return reservation

    def get_order(self, order_id: str):
        order = self.repo.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        return order

    def list_orders(self, limit: int = 10, cursor: Optional[str] = None):
        return self.repo.list_orders(limit=limit, cursor=cursor)
