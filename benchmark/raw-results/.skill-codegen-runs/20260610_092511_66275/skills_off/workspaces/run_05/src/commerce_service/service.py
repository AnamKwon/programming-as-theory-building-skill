from datetime import datetime, timedelta
from typing import Optional

from .models import ReservationStatus, OrderStatus
from .repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class ReservationAlreadyExistsError(Exception):
    pass


class InvalidReservationStateError(Exception):
    pass


class CommerceService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, name: str, quantity: int) -> int:
        return self.repo.create_sku(name, quantity)

    def get_sku(self, sku_id: int) -> Optional[dict]:
        return self.repo.get_sku(sku_id)

    def adjust_stock(self, sku_id: int, adjustment: int) -> None:
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        if sku["quantity"] + adjustment < 0:
            raise InsufficientStockError(f"Insufficient stock for SKU {sku_id}")
        self.repo.adjust_stock(sku_id, adjustment)

    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        expires_in_seconds: int,
        idempotency_key: str
    ) -> int:
        # Check for existing reservation with same idempotency key
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            raise ReservationAlreadyExistsError(
                f"Reservation with idempotency key {idempotency_key} already exists"
            )

        # Check SKU exists
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        # Check stock availability
        if sku["quantity"] < quantity:
            raise InsufficientStockError(
                f"Insufficient stock: need {quantity}, available {sku['quantity']}"
            )

        # Create reservation and deduct stock
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in_seconds)
        reservation_id = self.repo.create_reservation(
            sku_id, quantity, expires_at, idempotency_key
        )
        self.repo.adjust_stock(sku_id, -quantity)

        return reservation_id

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        return self.repo.get_reservation(reservation_id)

    def confirm_reservation(self, reservation_id: int) -> None:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        # Check expiration
        expires_at = datetime.fromisoformat(reservation["expires_at"])
        if datetime.utcnow() > expires_at:
            self.repo.update_reservation_status(
                reservation_id, ReservationStatus.EXPIRED
            )
            raise InvalidReservationStateError(
                f"Reservation {reservation_id} has expired"
            )

        # Check state
        if reservation["status"] != ReservationStatus.PENDING:
            raise InvalidReservationStateError(
                f"Cannot confirm reservation in {reservation['status']} status"
            )

        # Create order and add item
        order_id = self.repo.create_order()
        self.repo.add_order_item(
            order_id,
            reservation_id,
            reservation["sku_id"],
            reservation["quantity"]
        )
        self.repo.update_order_status(order_id, OrderStatus.COMPLETED)

        # Update reservation to confirmed
        self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CONFIRMED
        )

    def cancel_reservation(self, reservation_id: int) -> None:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        # Check state
        if reservation["status"] in (ReservationStatus.CONFIRMED, ReservationStatus.CANCELLED):
            raise InvalidReservationStateError(
                f"Cannot cancel reservation in {reservation['status']} status"
            )

        # Release reserved stock
        self.repo.adjust_stock(reservation["sku_id"], reservation["quantity"])

        # Update reservation status
        self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CANCELLED
        )

    def get_order(self, order_id: int) -> Optional[dict]:
        return self.repo.get_order(order_id)

    def list_orders(self, skip: int = 0, limit: int = 20) -> tuple[list[dict], int]:
        return self.repo.list_orders(skip, limit)
