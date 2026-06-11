"""Business logic service layer."""

from datetime import datetime
from typing import Optional

from .repository import Repository


class InsufficientStockError(Exception):
    """Raised when stock is insufficient."""

    pass


class ReservationExpiredError(Exception):
    """Raised when reservation has expired."""

    pass


class InvalidReservationStatusError(Exception):
    """Raised when attempting operation on reservation with invalid status."""

    pass


class CommerceService:
    """Service for commerce operations."""

    RESERVATION_EXPIRY_SECONDS = 300

    def __init__(self, repo: Repository):
        """Initialize service with repository."""
        self.repo = repo

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        """Create a new SKU."""
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> dict:
        """Adjust stock level."""
        return self.repo.adjust_stock(sku, amount)

    def reserve_stock(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> dict:
        """Reserve stock for an order."""
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        sku_data = self.repo.get_sku(sku)
        if not sku_data or sku_data["stock"] < quantity:
            raise InsufficientStockError()

        return self.repo.create_reservation(sku, quantity, idempotency_key)

    def confirm_reservation(self, reservation_id: int) -> dict:
        """Confirm a reservation and create an order."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation["status"] != "PENDING":
            raise InvalidReservationStatusError(
                f"Reservation is {reservation['status']}, not PENDING"
            )

        created_at = datetime.fromisoformat(reservation["created_at"])
        now = datetime.utcnow()
        elapsed = (now - created_at).total_seconds()

        if elapsed > self.RESERVATION_EXPIRY_SECONDS:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.restore_stock(reservation["sku"], reservation["quantity"])
            raise ReservationExpiredError()

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        order = self.repo.create_order(reservation_id)
        return {
            "reservation_id": reservation_id,
            "order_id": order["id"],
            "status": "CONFIRMED",
        }

    def cancel_reservation(self, reservation_id: int) -> dict:
        """Cancel a reservation and restore stock."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation["status"] != "PENDING":
            raise InvalidReservationStatusError(
                f"Reservation is {reservation['status']}, not PENDING"
            )

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        self.repo.restore_stock(reservation["sku"], reservation["quantity"])
        return {
            "reservation_id": reservation_id,
            "status": "CANCELLED",
            "stock_restored": reservation["quantity"],
        }

    def get_orders(self, page: int = 1, size: int = 10) -> dict:
        """Get paginated orders."""
        orders, total = self.repo.get_orders(page, size)
        return {
            "orders": orders,
            "page": page,
            "size": size,
            "total": total,
        }
