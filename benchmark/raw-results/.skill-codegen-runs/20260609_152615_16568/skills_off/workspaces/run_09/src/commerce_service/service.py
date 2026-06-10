"""Service layer with business logic for inventory and orders."""

from datetime import datetime, timedelta
from typing import Optional

from .models import Order, Reservation, ReservationStatus
from .repository import Repository


class InsufficientStockError(Exception):
    """Raised when inventory is insufficient for a reservation."""

    pass


class ReservationNotFoundError(Exception):
    """Raised when a reservation does not exist."""

    pass


class InvalidReservationStateError(Exception):
    """Raised when attempting an invalid state transition."""

    pass


class ReservationExpiredError(Exception):
    """Raised when attempting to confirm an expired reservation."""

    pass


class SKUNotFoundError(Exception):
    """Raised when a SKU does not exist."""

    pass


class IdempotencyError(Exception):
    """Raised when idempotency key is reused with different parameters."""

    pass


class CommerceService:
    """Business logic for inventory reservations and order orchestration."""

    RESERVATION_TTL_MINUTES = 15

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, product_name: str, initial_stock: int):
        """Create a new SKU with initial stock."""
        return self.repo.create_sku(product_name, initial_stock)

    def adjust_stock(self, sku_id: int, quantity_change: int):
        """Adjust available stock for a SKU."""
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        # Ensure stock doesn't go negative
        new_available = sku.available_stock + quantity_change
        if new_available < 0:
            raise ValueError(f"Stock adjustment would result in negative inventory")

        self.repo.update_sku_stock(sku_id, quantity_change, 0)
        return self.repo.get_sku(sku_id)

    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        idempotency_key: str,
    ) -> Reservation:
        """Create a reservation for inventory. Respects idempotency keys."""
        # Check for idempotency: if key exists, return existing reservation
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        # Verify SKU exists
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        # Check stock availability
        if quantity > sku.available_stock:
            raise InsufficientStockError(
                f"Insufficient stock: {quantity} requested, {sku.available_stock} available"
            )

        # Reserve the inventory
        expires_at = datetime.utcnow() + timedelta(minutes=self.RESERVATION_TTL_MINUTES)
        reservation = self.repo.create_reservation(sku_id, quantity, idempotency_key, expires_at)

        # Update SKU stock: move from available to reserved
        self.repo.update_sku_stock(sku_id, -quantity, quantity)

        return reservation

    def confirm_reservation(self, reservation_id: int) -> Order:
        """Confirm a pending reservation and create an order."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        # Check expiration
        if datetime.utcnow() > reservation.expires_at:
            self.repo.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        # Only allow transition from PENDING
        if reservation.status != ReservationStatus.PENDING:
            raise InvalidReservationStateError(
                f"Cannot confirm reservation in {reservation.status.value} state"
            )

        # Transition to confirmed and create order
        self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)
        order = self.repo.create_order(reservation.sku_id, reservation.quantity, reservation_id)

        return order

    def cancel_reservation(self, reservation_id: int) -> Reservation:
        """Cancel a reservation and release reserved inventory."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        # Only allow cancellation of pending reservations
        if reservation.status != ReservationStatus.PENDING:
            raise InvalidReservationStateError(
                f"Cannot cancel reservation in {reservation.status.value} state"
            )

        # Release reserved inventory back to available
        self.repo.update_sku_stock(reservation.sku_id, reservation.quantity, -reservation.quantity)

        # Update status
        self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)

        return self.repo.get_reservation(reservation_id)

    def get_orders(self, limit: int = 10, cursor: Optional[int] = None) -> tuple[list[Order], Optional[int]]:
        """Get paginated list of orders."""
        return self.repo.get_orders(limit, cursor)
