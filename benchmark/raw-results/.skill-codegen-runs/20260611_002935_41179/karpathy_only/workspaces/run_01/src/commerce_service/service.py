"""Business logic layer for commerce service."""
from datetime import datetime
from typing import Optional, Tuple

from .repository import Database, SKURepository, ReservationRepository, OrderRepository


class CommerceService:
    """Main business logic service."""

    def __init__(self, db: Database):
        """Initialize service."""
        self.db = db
        self.sku_repo = SKURepository(db)
        self.reservation_repo = ReservationRepository(db)
        self.order_repo = OrderRepository(db)

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        """Create a new SKU."""
        return self.sku_repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> Optional[dict]:
        """Adjust stock level."""
        return self.sku_repo.adjust_stock(sku, amount)

    def create_reservation(
        self,
        sku: str,
        quantity: int,
        idempotency_key: str,
    ) -> Tuple[dict, str]:
        """
        Create a reservation with idempotency check.

        Returns:
            Tuple of (response_dict, status_code)
        """
        # Check for existing reservation with same idempotency key
        existing = self.reservation_repo.get_reservation_by_idempotency_key(
            idempotency_key
        )
        if existing:
            return (existing, "200")

        # Check stock availability
        sku_data = self.sku_repo.get_sku(sku)
        if not sku_data or sku_data["available_stock"] < quantity:
            return (None, "400")

        # Deduct stock
        self.sku_repo.adjust_stock(sku, -quantity)

        # Create reservation
        reservation = self.reservation_repo.create_reservation(
            sku, quantity, idempotency_key
        )

        return (reservation, "201")

    def confirm_reservation(self, reservation_id: int) -> Tuple[Optional[dict], str]:
        """
        Confirm a reservation and create an order.

        Returns:
            Tuple of (response_dict, status_code)
        """
        reservation = self.reservation_repo.get_reservation(reservation_id)

        if not reservation:
            return (None, "404")

        # Check if status is PENDING
        if reservation["status"] != "PENDING":
            return (None, "400")

        # Check expiration (300 seconds)
        created_at = datetime.fromisoformat(reservation["created_at"])
        now = datetime.utcnow()
        elapsed = (now - created_at).total_seconds()

        if elapsed > 300:
            # Mark as expired and restore stock
            self.reservation_repo.update_reservation_status(
                reservation_id, "EXPIRED"
            )
            self.sku_repo.adjust_stock(reservation["sku"], reservation["quantity"])
            return (None, "400_EXPIRED")

        # Create order and confirm reservation
        order = self.order_repo.create_order(reservation_id)
        self.reservation_repo.update_reservation_status(reservation_id, "CONFIRMED")

        return (order, "200")

    def cancel_reservation(self, reservation_id: int) -> Tuple[Optional[dict], str]:
        """
        Cancel a reservation and restore stock.

        Returns:
            Tuple of (response_dict, status_code)
        """
        reservation = self.reservation_repo.get_reservation(reservation_id)

        if not reservation:
            return (None, "404")

        # Check if status is PENDING
        if reservation["status"] != "PENDING":
            return (None, "400")

        # Restore stock
        self.sku_repo.adjust_stock(reservation["sku"], reservation["quantity"])

        # Mark as cancelled
        self.reservation_repo.update_reservation_status(reservation_id, "CANCELLED")

        return (reservation, "200")

    def get_orders(self, page: int = 1, size: int = 10) -> Tuple[list, int]:
        """Get paginated orders."""
        offset = (page - 1) * size
        return self.order_repo.get_orders(offset, size)
