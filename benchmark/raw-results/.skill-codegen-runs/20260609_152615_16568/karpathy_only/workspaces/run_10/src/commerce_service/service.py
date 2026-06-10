"""Business logic for commerce service."""

import uuid
from datetime import datetime

from .models import ReservationState
from .repository import Repository


class InsufficientStockError(Exception):
    """Raised when there is not enough stock to fulfill a reservation."""

    pass


class ReservationNotFoundError(Exception):
    """Raised when a reservation is not found."""

    pass


class ReservationExpiredError(Exception):
    """Raised when a reservation has expired."""

    pass


class ReservationAlreadyConfirmedError(Exception):
    """Raised when attempting to confirm an already confirmed reservation."""

    pass


class IdempotencyError(Exception):
    """Raised when an idempotency key has already been used."""

    pass


class SKUNotFoundError(Exception):
    """Raised when a SKU is not found."""

    pass


class CommerceService:
    """Business logic for inventory and order management."""

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku_id: str, quantity: int):
        """Create a new SKU."""
        return self.repo.create_sku(sku_id, quantity)

    def adjust_stock(self, sku_id: str, delta: int):
        """Adjust stock for a SKU."""
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        return self.repo.adjust_stock(sku_id, delta)

    def create_reservation(self, sku_id: str, quantity: int, idempotency_key: str):
        """Create a new reservation with idempotency."""
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        if sku.quantity < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for {sku_id}: need {quantity}, have {sku.quantity}"
            )

        reservation_id = str(uuid.uuid4())
        reservation = self.repo.create_reservation(
            reservation_id, sku_id, quantity, idempotency_key
        )

        self.repo.adjust_stock(sku_id, -quantity)

        return reservation

    def confirm_reservation(self, reservation_id: str):
        """Confirm a pending reservation and create an order."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if datetime.utcnow() > reservation.expires_at:
            self.repo.update_reservation_state(reservation_id, ReservationState.EXPIRED)
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        if reservation.state != ReservationState.PENDING:
            raise ReservationAlreadyConfirmedError(
                f"Reservation {reservation_id} is already {reservation.state.value}"
            )

        self.repo.update_reservation_state(reservation_id, ReservationState.CONFIRMED)

        order_id = str(uuid.uuid4())
        order = self.repo.create_order(order_id, reservation.sku_id, reservation.quantity, reservation_id)

        return order

    def cancel_reservation(self, reservation_id: str):
        """Cancel a pending reservation and release stock."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.state == ReservationState.CANCELLED:
            return reservation

        if reservation.state == ReservationState.CONFIRMED:
            raise ReservationAlreadyConfirmedError(
                f"Cannot cancel confirmed reservation {reservation_id}"
            )

        self.repo.update_reservation_state(reservation_id, ReservationState.CANCELLED)
        self.repo.adjust_stock(reservation.sku_id, reservation.quantity)

        return self.repo.get_reservation(reservation_id)

    def get_order(self, order_id: str):
        """Get an order by ID."""
        return self.repo.get_order(order_id)

    def list_orders(self, limit: int = 20, offset: int = 0):
        """List orders with pagination."""
        return self.repo.list_orders(limit, offset)
