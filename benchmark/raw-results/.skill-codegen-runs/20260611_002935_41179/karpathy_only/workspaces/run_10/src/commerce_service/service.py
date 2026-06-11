"""Business logic layer."""

from datetime import datetime

from .models import ReservationStatus
from .repository import Database


class CommerceService:
    def __init__(self, db: Database):
        self.db = db

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        """Create a new SKU with initial stock."""
        return self.db.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> dict:
        """Adjust stock for a SKU."""
        return self.db.adjust_stock(sku, amount)

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> dict:
        """Create a reservation with idempotency check."""
        # Check for existing idempotent reservation
        existing = self.db.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        # Get SKU and validate stock
        sku_data = self.db.get_sku(sku)
        if not sku_data:
            raise ValueError(f"SKU {sku} not found")

        if sku_data["available_stock"] < quantity:
            raise ValueError("Insufficient stock")

        # Deduct stock and create reservation
        self.db.deduct_stock(sku, quantity)
        reservation = self.db.create_reservation(
            sku, sku_data["id"], quantity, idempotency_key
        )
        return reservation

    def confirm_reservation(self, reservation_id: int) -> dict:
        """Confirm a reservation and create an order."""
        reservation = self.db.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation["status"] != ReservationStatus.PENDING.value:
            raise ValueError(f"Reservation is not PENDING, status: {reservation['status']}")

        # Check expiration (300 seconds)
        created_at = datetime.fromisoformat(reservation["created_at"])
        now = datetime.utcnow()
        age_seconds = (now - created_at).total_seconds()

        if age_seconds > 300:
            # Mark as expired and restore stock
            self.db.update_reservation_status(reservation_id, ReservationStatus.EXPIRED.value)
            self.db.restore_stock(reservation["sku"], reservation["quantity"])
            raise ValueError("Reservation expired")

        # Update status and create order
        self.db.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED.value)
        order = self.db.create_order(reservation_id)
        return {
            "id": reservation_id,
            "sku": reservation["sku"],
            "quantity": reservation["quantity"],
            "status": ReservationStatus.CONFIRMED.value,
            "order_id": order["id"],
        }

    def cancel_reservation(self, reservation_id: int) -> dict:
        """Cancel a reservation and restore stock."""
        reservation = self.db.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation["status"] != ReservationStatus.PENDING.value:
            raise ValueError(f"Reservation is not PENDING, status: {reservation['status']}")

        # Restore stock and update status
        self.db.restore_stock(reservation["sku"], reservation["quantity"])
        self.db.update_reservation_status(reservation_id, ReservationStatus.CANCELLED.value)
        return self.db.get_reservation(reservation_id)

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[dict], int]:
        """Get paginated orders."""
        return self.db.get_orders(page, size)
