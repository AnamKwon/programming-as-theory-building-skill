from datetime import datetime, timedelta
from typing import Optional

from .models import ReservationStatus
from .repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class InvalidReservationStateError(Exception):
    pass


class SKUNotFoundError(Exception):
    pass


class Service:
    RESERVATION_TTL_SECONDS = 300

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, code: str, description: str):
        sku = self.repo.create_sku(code, description)
        self.repo.initialize_stock(sku.id)
        return sku

    def adjust_stock(self, sku_id: str, adjustment: int):
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        stock = self.repo.adjust_stock(sku_id, adjustment)
        if stock is None:
            raise SKUNotFoundError(f"Stock for SKU {sku_id} not found")

        if stock.quantity < 0:
            raise InsufficientStockError(
                f"Stock adjustment would result in negative quantity"
            )

        return stock

    def create_reservation(
        self,
        sku_id: str,
        quantity: int,
        idempotency_key: Optional[str] = None,
    ):
        if idempotency_key:
            existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
            if existing:
                return existing

        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        stock = self.repo.get_stock(sku_id)
        if not stock or stock.quantity < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for SKU {sku_id}: need {quantity}, have {stock.quantity if stock else 0}"
            )

        expires_at = datetime.utcnow() + timedelta(seconds=self.RESERVATION_TTL_SECONDS)
        reservation = self.repo.create_reservation(
            sku_id, quantity, expires_at, idempotency_key
        )

        self.repo.adjust_stock(sku_id, -quantity)

        return reservation

    def confirm_reservation(self, reservation_id: str):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if datetime.utcnow() > reservation.expires_at:
            self.repo.update_reservation_status(
                reservation_id, ReservationStatus.EXPIRED.value
            )
            raise ReservationExpiredError(
                f"Reservation {reservation_id} has expired"
            )

        if reservation.status != ReservationStatus.PENDING.value:
            raise InvalidReservationStateError(
                f"Reservation {reservation_id} is not pending (status: {reservation.status})"
            )

        order = self.repo.create_order(
            reservation.sku_id, reservation.quantity, reservation_id
        )

        self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CONFIRMED.value
        )

        return order

    def cancel_reservation(self, reservation_id: str):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status not in (
            ReservationStatus.PENDING.value,
            ReservationStatus.EXPIRED.value,
        ):
            raise InvalidReservationStateError(
                f"Cannot cancel reservation {reservation_id} with status {reservation.status}"
            )

        self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CANCELLED.value
        )

        self.repo.adjust_stock(reservation.sku_id, reservation.quantity)

        return reservation

    def get_order(self, order_id: str):
        order = self.repo.get_order(order_id)
        if not order:
            return None
        return order

    def list_orders(self, offset: int = 0, limit: int = 10):
        orders, total = self.repo.list_orders(offset, limit)
        return orders, total
