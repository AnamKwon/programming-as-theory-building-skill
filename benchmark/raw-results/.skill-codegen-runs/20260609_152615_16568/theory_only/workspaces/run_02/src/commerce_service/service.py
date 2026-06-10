"""Business logic service layer."""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .models import ReservationStatus, OrderStatus
from .repository import Repository, ReservationModel, OrderModel, SKUModel


class ReservationExpiredError(Exception):
    """Raised when a reservation has expired."""
    pass


class InsufficientStockError(Exception):
    """Raised when there is insufficient stock."""
    pass


class SKUNotFoundError(Exception):
    """Raised when SKU is not found."""
    pass


class ReservationNotFoundError(Exception):
    """Raised when reservation is not found."""
    pass


class OrderNotFoundError(Exception):
    """Raised when order is not found."""
    pass


class Service:
    """Business logic service."""

    def __init__(self, db: Session):
        self.repo = Repository(db)

    # SKU operations
    def create_sku(self, code: str, name: str) -> SKUModel:
        """Create a new SKU."""
        return self.repo.create_sku(code, name)

    def get_sku(self, sku_id: int) -> SKUModel:
        """Get SKU by ID, raising if not found."""
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")
        return sku

    def adjust_stock(self, sku_id: int, adjustment: int) -> SKUModel:
        """Adjust stock for a SKU."""
        sku = self.get_sku(sku_id)
        if sku.stock + adjustment < 0:
            raise ValueError("Stock cannot be negative")
        return self.repo.adjust_stock(sku_id, adjustment)

    # Reservation operations
    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        idempotency_key: str
    ) -> ReservationModel:
        """
        Create a reservation for a SKU.

        If idempotency_key already exists, return the existing reservation.
        Raises InsufficientStockError if not enough available stock.
        """
        # Check for existing reservation with same idempotency key
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        # Check SKU exists and has sufficient stock
        sku = self.get_sku(sku_id)
        available = sku.stock - sku.reserved
        if available < quantity:
            raise InsufficientStockError(
                f"Insufficient stock: need {quantity}, have {available}"
            )

        # Create reservation and update reserved count
        expires_at = datetime.utcnow() + timedelta(hours=24)
        reservation = self.repo.create_reservation(
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            expires_at=expires_at
        )
        self.repo.update_sku_reserved(sku_id, quantity)
        return reservation

    def get_reservation(self, reservation_id: int) -> ReservationModel:
        """Get reservation by ID, raising if not found."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")
        return reservation

    def confirm_reservation(self, reservation_id: int) -> OrderModel:
        """
        Confirm a reservation and create an order.

        Raises ReservationExpiredError if reservation has expired.
        Raises ValueError if reservation is not in pending state.
        """
        reservation = self.get_reservation(reservation_id)

        if reservation.status != ReservationStatus.PENDING:
            raise ValueError(
                f"Can only confirm pending reservations, got {reservation.status}"
            )

        if datetime.utcnow() > reservation.expires_at:
            # Release reserved stock and cancel reservation
            self.repo.update_sku_reserved(reservation.sku_id, -reservation.quantity)
            self.repo.update_reservation_status(
                reservation_id, ReservationStatus.CANCELLED
            )
            raise ReservationExpiredError("Reservation has expired")

        # Create order and update reservation status
        order = self.repo.create_order(reservation_id)
        self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CONFIRMED
        )
        return order

    def cancel_reservation(self, reservation_id: int) -> ReservationModel:
        """
        Cancel a reservation and release reserved stock.

        Can only cancel pending reservations.
        """
        reservation = self.get_reservation(reservation_id)

        if reservation.status != ReservationStatus.PENDING:
            raise ValueError(
                f"Can only cancel pending reservations, got {reservation.status}"
            )

        # Release reserved stock and update status
        self.repo.update_sku_reserved(reservation.sku_id, -reservation.quantity)
        return self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CANCELLED
        )

    # Order operations
    def get_order(self, order_id: int) -> OrderModel:
        """Get order by ID, raising if not found."""
        order = self.repo.get_order(order_id)
        if not order:
            raise OrderNotFoundError(f"Order {order_id} not found")
        return order

    def list_orders(self, offset: int = 0, limit: int = 20) -> tuple[list[OrderModel], int]:
        """List orders with pagination."""
        return self.repo.list_orders(offset, limit)
