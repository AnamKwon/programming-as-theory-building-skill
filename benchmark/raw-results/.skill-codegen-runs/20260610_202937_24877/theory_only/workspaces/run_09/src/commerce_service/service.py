"""Business logic for commerce service."""

from datetime import datetime
from typing import Optional

from .repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class InvalidReservationStateError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        """Create a new SKU."""
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> dict:
        """Adjust stock for a SKU."""
        result = self.repo.adjust_stock(sku, amount)
        if result is None:
            raise ValueError(f"SKU {sku} not found or invalid adjustment")
        return result

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> dict:
        """
        Create a reservation with idempotency.

        Rule 1: Check if available stock >= quantity. If not, raise InsufficientStockError.
        Rule 2: Check if idempotency_key exists. If yes, return cached reservation.
        Rule 3: Deduct stock and create reservation with PENDING status.
        """
        existing = self.repo.find_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        current_stock = self.repo.get_sku_stock(sku)
        if current_stock is None:
            raise ValueError(f"SKU {sku} not found")

        if current_stock < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for {sku}. Available: {current_stock}, Requested: {quantity}"
            )

        self.repo.adjust_stock(sku, -quantity)
        reservation = self.repo.create_reservation(sku, quantity, idempotency_key)
        return reservation

    def confirm_reservation(self, reservation_id: int) -> dict:
        """
        Confirm a reservation and create an order.

        Rule 1: Check reservation exists and is PENDING.
        Rule 2: Check expiration (creation time > 300 seconds ago).
        Rule 3: Create order and update status to CONFIRMED.
        """
        reservation = self.repo.get_reservation(reservation_id)

        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation["status"] != "PENDING":
            raise InvalidReservationStateError(
                f"Cannot confirm reservation with status {reservation['status']}"
            )

        created_at = datetime.fromisoformat(reservation["created_at"])
        now = datetime.utcnow()
        age_seconds = (now - created_at).total_seconds()

        if age_seconds > 300:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.adjust_stock(reservation["sku"], reservation["quantity"])
            raise ReservationExpiredError("Reservation has expired")

        order = self.repo.create_order(
            reservation_id,
            reservation["sku"],
            reservation["quantity"]
        )

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")

        return {
            "id": reservation_id,
            "sku": reservation["sku"],
            "quantity": reservation["quantity"],
            "status": "CONFIRMED",
            "order_id": order["id"]
        }

    def cancel_reservation(self, reservation_id: int) -> dict:
        """
        Cancel a reservation and restore stock.

        Rule: Cancel must target PENDING reservation.
        """
        reservation = self.repo.get_reservation(reservation_id)

        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation["status"] != "PENDING":
            raise InvalidReservationStateError(
                f"Cannot cancel reservation with status {reservation['status']}"
            )

        self.repo.adjust_stock(reservation["sku"], reservation["quantity"])
        self.repo.update_reservation_status(reservation_id, "CANCELLED")

        return {
            "id": reservation_id,
            "status": "CANCELLED",
            "restored_stock": reservation["quantity"]
        }

    def list_orders(self, page: int = 1, size: int = 10) -> dict:
        """List orders with pagination."""
        orders, total = self.repo.list_orders(page, size)
        return {
            "items": orders,
            "total": total,
            "page": page,
            "size": size
        }
