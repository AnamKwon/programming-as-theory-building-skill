import uuid
from datetime import datetime, timedelta

from .models import (
    DBOrder,
    DBOrderItem,
    DBReservation,
    OrderStatus,
    ReservationStatus,
)
from .repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class InvalidReservationStateError(Exception):
    pass


class OrderNotFoundError(Exception):
    pass


class DuplicateIdempotencyKeyError(Exception):
    pass


class Service:
    RESERVATION_TTL_MINUTES = 15

    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, sku: str, quantity: int):
        return self.repo.create_sku(sku, quantity)

    def adjust_stock(self, sku: str, delta: int):
        existing = self.repo.get_sku(sku)
        if not existing:
            raise ValueError(f"SKU {sku} not found")

        new_quantity = existing.quantity + delta
        if new_quantity < 0:
            raise ValueError("Stock cannot be negative")

        return self.repo.update_sku_quantity(sku, new_quantity)

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> DBReservation:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing.status == ReservationStatus.CANCELLED:
                raise DuplicateIdempotencyKeyError(
                    "Idempotency key already used for a cancelled reservation"
                )
            return existing

        sku_record = self.repo.get_sku(sku)
        if not sku_record:
            raise ValueError(f"SKU {sku} not found")

        if sku_record.quantity < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for {sku}: have {sku_record.quantity}, need {quantity}"
            )

        reservation_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(
            minutes=self.RESERVATION_TTL_MINUTES
        )

        reservation = self.repo.create_reservation(
            reservation_id=reservation_id,
            sku=sku,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )

        self.repo.update_sku_quantity(sku, sku_record.quantity - quantity)

        return reservation

    def get_reservation(self, reservation_id: str) -> DBReservation:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status == ReservationStatus.PENDING:
            if datetime.utcnow() > reservation.expires_at:
                self.repo.update_reservation_status(
                    reservation_id, ReservationStatus.EXPIRED
                )
                sku = self.repo.get_sku(reservation.sku)
                if sku:
                    self.repo.update_sku_quantity(
                        reservation.sku, sku.quantity + reservation.quantity
                    )
                return self.repo.get_reservation(reservation_id)

        return reservation

    def confirm_reservation(self, reservation_id: str) -> DBOrder:
        reservation = self.get_reservation(reservation_id)

        if reservation.status == ReservationStatus.CONFIRMED:
            order = self._find_order_by_reservation(reservation_id)
            if order:
                return order

        if reservation.status != ReservationStatus.PENDING:
            raise InvalidReservationStateError(
                f"Cannot confirm reservation in {reservation.status} state"
            )

        if datetime.utcnow() > reservation.expires_at:
            self.repo.update_reservation_status(
                reservation_id, ReservationStatus.EXPIRED
            )
            raise InvalidReservationStateError("Reservation has expired")

        self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CONFIRMED
        )

        order_id = str(uuid.uuid4())
        items = [DBOrderItem(sku=reservation.sku, quantity=reservation.quantity)]

        order = self.repo.create_order(order_id, items)
        self.repo.update_order_status(order_id, OrderStatus.CONFIRMED)

        return self.repo.get_order(order_id)

    def cancel_reservation(self, reservation_id: str) -> DBReservation:
        reservation = self.get_reservation(reservation_id)

        if reservation.status == ReservationStatus.CANCELLED:
            return reservation

        if reservation.status not in [
            ReservationStatus.PENDING,
            ReservationStatus.EXPIRED,
        ]:
            raise InvalidReservationStateError(
                f"Cannot cancel reservation in {reservation.status} state"
            )

        self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CANCELLED
        )

        if reservation.status == ReservationStatus.PENDING:
            sku = self.repo.get_sku(reservation.sku)
            if sku:
                self.repo.update_sku_quantity(
                    reservation.sku, sku.quantity + reservation.quantity
                )

        return self.repo.get_reservation(reservation_id)

    def get_order(self, order_id: str) -> DBOrder:
        order = self.repo.get_order(order_id)
        if not order:
            raise OrderNotFoundError(f"Order {order_id} not found")
        return order

    def list_orders(self, cursor: str = None, limit: int = 20):
        return self.repo.list_orders(cursor=cursor, limit=limit)

    def _find_order_by_reservation(self, reservation_id: str) -> DBOrder:
        orders, _ = self.repo.list_orders(limit=1000)
        for order in orders:
            if order.order_id.startswith(reservation_id[:8]):
                return order
        return None
