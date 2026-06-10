"""Business logic layer."""

import uuid
from datetime import datetime, timedelta
from typing import Optional

from .models import OrderStatus, ReservationStatus
from .repository import Repository


class ConflictError(Exception):
    """Raised when operation conflicts with existing state."""

    pass


class ValidationError(Exception):
    """Raised when validation fails."""

    pass


class NotFoundError(Exception):
    """Raised when resource not found."""

    pass


class CommercService:
    """Business logic for commerce operations."""

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku_id: str, name: str):
        """Create a new SKU."""
        existing = self.repo.get_sku(sku_id)
        if existing:
            raise ConflictError(f"SKU {sku_id} already exists")
        return self.repo.create_sku(sku_id, name)

    def get_sku(self, sku_id: str):
        """Get SKU details."""
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise NotFoundError(f"SKU {sku_id} not found")
        return sku

    def adjust_stock(self, sku_id: str, quantity_change: float):
        """Adjust stock quantity for a SKU."""
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise NotFoundError(f"SKU {sku_id} not found")

        inventory = self.repo.adjust_inventory(sku_id, quantity_change)
        if inventory.available_quantity < 0:
            raise ValidationError("Insufficient available inventory")
        return inventory

    def get_inventory(self, sku_id: str):
        """Get current inventory state."""
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise NotFoundError(f"SKU {sku_id} not found")

        inventory = self.repo.get_inventory(sku_id)
        if not inventory:
            raise NotFoundError(f"Inventory not found for SKU {sku_id}")
        return inventory

    def create_reservation(
        self,
        sku_id: str,
        order_id: str,
        quantity: float,
        ttl_seconds: int = 3600,
        idempotency_key: Optional[str] = None,
    ):
        """Create a reservation for inventory."""
        # Check idempotency: if key exists, return existing reservation
        if idempotency_key:
            existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
            if existing:
                return existing

        # Validate SKU exists
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise NotFoundError(f"SKU {sku_id} not found")

        # Check inventory availability
        inventory = self.repo.get_inventory(sku_id)
        if not inventory or inventory.available_quantity < quantity:
            raise ValidationError(f"Insufficient stock for SKU {sku_id}. Available: {inventory.available_quantity if inventory else 0}")

        # Ensure order exists
        order = self.repo.get_order(order_id)
        if not order:
            order = self.repo.create_order(order_id)

        # Create reservation
        reservation_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)

        reservation = self.repo.create_reservation(
            reservation_id=reservation_id,
            sku_id=sku_id,
            order_id=order_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )

        # Move inventory from available to reserved
        self.repo.reserve_inventory(sku_id, quantity)

        return reservation

    def get_reservation(self, reservation_id: str):
        """Get reservation details."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise NotFoundError(f"Reservation {reservation_id} not found")
        return reservation

    def confirm_reservation(self, reservation_id: str):
        """Confirm a pending reservation."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise NotFoundError(f"Reservation {reservation_id} not found")

        # Check expiration
        if datetime.utcnow() > reservation.expires_at:
            self.repo.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
            raise ValidationError(f"Reservation {reservation_id} has expired")

        if reservation.status != ReservationStatus.PENDING:
            raise ValidationError(f"Cannot confirm reservation in {reservation.status} status")

        reservation = self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)

        # Update order status if all reservations are confirmed
        order = self.repo.get_order(reservation.order_id)
        if order:
            reservations = self.repo.get_reservations_by_order(reservation.order_id)
            if all(r.status == ReservationStatus.CONFIRMED for r in reservations):
                self.repo.update_order_status(reservation.order_id, OrderStatus.CONFIRMED)

        return reservation

    def cancel_reservation(self, reservation_id: str):
        """Cancel a reservation."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise NotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status == ReservationStatus.CANCELLED:
            raise ValidationError(f"Reservation {reservation_id} is already cancelled")

        if reservation.status == ReservationStatus.CONFIRMED:
            raise ValidationError(f"Cannot cancel confirmed reservation {reservation_id}")

        # Release reserved inventory
        self.repo.release_reserved_inventory(reservation.sku_id, reservation.quantity)

        reservation = self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)

        # Check if order should be cancelled (all reservations cancelled/expired)
        order = self.repo.get_order(reservation.order_id)
        if order:
            reservations = self.repo.get_reservations_by_order(reservation.order_id)
            if all(r.status in (ReservationStatus.CANCELLED, ReservationStatus.EXPIRED) for r in reservations):
                self.repo.update_order_status(reservation.order_id, OrderStatus.CANCELLED)

        return reservation

    def get_order(self, order_id: str):
        """Get order details."""
        order = self.repo.get_order(order_id)
        if not order:
            raise NotFoundError(f"Order {order_id} not found")
        return order

    def list_orders(self, page: int = 1, page_size: int = 10):
        """List orders with pagination."""
        if page < 1 or page_size < 1:
            raise ValidationError("Page and page_size must be >= 1")
        skip = (page - 1) * page_size
        orders, total = self.repo.list_orders(skip=skip, limit=page_size)
        has_more = skip + page_size < total
        return {
            "orders": orders,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": has_more,
        }
