from datetime import datetime, timedelta
from typing import Optional

from .models import OrderSchema, ReservationSchema, ReservationState
from .repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class InvalidStateTransitionError(Exception):
    pass


class OrderAlreadyExistsError(Exception):
    pass


class Service:
    RESERVATION_TTL_MINUTES = 10

    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, sku_code: str, name: str, quantity: int):
        return self.repo.create_sku(sku_code, name, quantity)

    def adjust_stock(self, sku_id: int, quantity_delta: int):
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        new_quantity = sku.quantity + quantity_delta
        if new_quantity < 0:
            raise ValueError(f"Insufficient stock: cannot reduce below 0")

        return self.repo.update_sku_quantity(sku_id, quantity_delta)

    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        idempotency_key: Optional[str] = None,
    ) -> ReservationSchema:
        if idempotency_key:
            existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
            if existing:
                return existing

        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        if sku.quantity < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for SKU {sku_id}: available={sku.quantity}, requested={quantity}"
            )

        expires_at = datetime.utcnow() + timedelta(minutes=self.RESERVATION_TTL_MINUTES)
        reservation = self.repo.create_reservation(
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )

        self.repo.update_sku_quantity(sku_id, -quantity)

        return reservation

    def confirm_reservation(self, reservation_id: int) -> OrderSchema:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if datetime.fromisoformat(str(reservation.expires_at)) < datetime.utcnow():
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        if reservation.state == ReservationState.CONFIRMED:
            existing_order = self.repo.get_order_by_reservation_id(reservation_id)
            if existing_order:
                return existing_order
            raise OrderAlreadyExistsError(f"Order already exists for reservation {reservation_id}")

        if reservation.state == ReservationState.CANCELLED:
            raise InvalidStateTransitionError(
                f"Cannot confirm cancelled reservation {reservation_id}"
            )

        self.repo.update_reservation_state(reservation_id, ReservationState.CONFIRMED)
        order = self.repo.create_order(reservation_id)
        return order

    def cancel_reservation(self, reservation_id: int) -> ReservationSchema:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.state == ReservationState.CANCELLED:
            return reservation

        if reservation.state == ReservationState.CONFIRMED:
            raise InvalidStateTransitionError(
                f"Cannot cancel confirmed reservation {reservation_id}"
            )

        self.repo.update_reservation_state(reservation_id, ReservationState.CANCELLED)
        self.repo.update_sku_quantity(reservation.sku_id, reservation.quantity)

        return self.repo.get_reservation(reservation_id)

    def get_orders(self, limit: int = 10, offset: int = 0) -> tuple[list[OrderSchema], int]:
        return self.repo.list_orders(limit=limit, offset=offset)
