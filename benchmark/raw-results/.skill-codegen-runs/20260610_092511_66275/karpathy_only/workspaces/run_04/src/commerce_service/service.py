"""Business logic for the commerce service."""

from datetime import datetime, timezone

from commerce_service.repository import Repository


class InsufficientStockError(Exception):
    """Raised when stock is insufficient for a reservation."""

    pass


class ReservationExpiredError(Exception):
    """Raised when attempting to confirm an expired reservation."""

    pass


class InvalidStatusTransitionError(Exception):
    """Raised when an invalid status transition is attempted."""

    pass


class CommerceService:
    """Service layer for commerce operations."""

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku_id: str, initial_stock: int) -> dict:
        """Create a new SKU with initial stock."""
        return self.repo.create_sku(sku_id, initial_stock)

    def adjust_stock(self, sku_id: str, delta: int) -> dict:
        """Adjust stock for a SKU."""
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        result = self.repo.adjust_stock(sku_id, delta)
        if result is None:
            raise ValueError(f"Failed to adjust stock for SKU {sku_id}")

        return result

    def create_reservation(
        self, sku_id: str, quantity: int, idempotency_key: str
    ) -> dict:
        """Create a reservation for a SKU.

        If a reservation with the same idempotency key and SKU exists,
        return the existing reservation (idempotency).
        """
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        # Check idempotency: return existing reservation if it exists
        existing = self.repo.get_reservation_by_idempotency(
            idempotency_key, sku_id
        )
        if existing:
            return existing

        # Check stock availability
        if sku["stock"] < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for SKU {sku_id}: "
                f"requested {quantity}, available {sku['stock']}"
            )

        # Reserve stock by reducing available stock
        self.repo.adjust_stock(sku_id, -quantity)

        # Create reservation
        reservation = self.repo.create_reservation(
            sku_id, quantity, idempotency_key
        )
        return reservation

    def confirm_reservation(self, reservation_id: str) -> dict:
        """Confirm a reservation into an order.

        Validates that:
        - Reservation exists
        - Reservation is pending (not already confirmed/cancelled)
        - Reservation has not expired
        """
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation["status"] != "pending":
            raise InvalidStatusTransitionError(
                f"Cannot confirm reservation with status '{reservation['status']}'"
            )

        # Check expiration
        expires_at = datetime.fromisoformat(reservation["expires_at"])
        now = datetime.now(timezone.utc)
        if now > expires_at:
            raise ReservationExpiredError(
                f"Reservation {reservation_id} expired at {expires_at}"
            )

        # Update reservation status
        updated_reservation = self.repo.update_reservation_status(
            reservation_id, "confirmed"
        )

        # Create order with completed status
        order = self.repo.create_order(
            reservation["sku_id"],
            reservation["quantity"],
            initial_status="completed",
        )

        # Mark order as completed
        completed_order = self.repo.update_order_status(
            order["order_id"], "completed"
        )

        return {
            "reservation": updated_reservation,
            "order": completed_order,
        }

    def cancel_reservation(self, reservation_id: str) -> dict:
        """Cancel a reservation and return reserved stock."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation["status"] == "cancelled":
            raise InvalidStatusTransitionError(
                "Reservation is already cancelled"
            )

        if reservation["status"] == "confirmed":
            raise InvalidStatusTransitionError(
                "Cannot cancel a confirmed reservation"
            )

        # Return stock
        self.repo.adjust_stock(reservation["sku_id"], reservation["quantity"])

        # Update reservation status
        updated_reservation = self.repo.update_reservation_status(
            reservation_id, "cancelled"
        )

        return updated_reservation

    def get_order(self, order_id: str) -> dict:
        """Get an order by ID."""
        order = self.repo.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        return order

    def list_orders(self, limit: int = 10, offset: int = 0) -> tuple[list[dict], int]:
        """List orders with pagination."""
        if limit < 1 or limit > 100:
            limit = 10
        if offset < 0:
            offset = 0
        return self.repo.list_orders(limit, offset)
