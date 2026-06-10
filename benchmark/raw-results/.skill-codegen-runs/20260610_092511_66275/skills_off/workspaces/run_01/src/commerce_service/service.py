"""Business logic layer for commerce operations."""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func

from .models import SKUModel, ReservationModel, OrderModel
from .repository import Repository


class CommerceService:
    """Service for inventory and order management."""

    def __init__(self, repo: Repository):
        self.repo = repo

    # SKU operations
    def create_sku(self, sku_code: str, qty: int) -> SKUModel:
        """Create a new SKU."""
        existing = self.repo.get_sku_by_code(sku_code)
        if existing:
            raise ValueError(f"SKU code '{sku_code}' already exists")
        if qty < 0:
            raise ValueError("Quantity cannot be negative")
        return self.repo.create_sku(sku_code, qty)

    def adjust_stock(self, sku_id: int, delta: int) -> SKUModel:
        """Adjust stock by delta."""
        if delta == 0:
            sku = self.repo.get_sku_by_id(sku_id)
            if not sku:
                raise ValueError(f"SKU {sku_id} not found")
            return sku
        return self.repo.adjust_stock(sku_id, delta)

    # Reservation operations
    def create_reservation(
        self, sku_id: int, qty: int, idempotency_key: str, ttl_seconds: int = 3600
    ) -> ReservationModel:
        """Create a reservation if one doesn't already exist."""
        # Check for idempotent retry
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        # Validate inputs
        if qty <= 0:
            raise ValueError("Reservation quantity must be positive")
        if ttl_seconds < 60 or ttl_seconds > 86400:
            raise ValueError("TTL must be between 60 and 86400 seconds")

        # Check SKU exists and has sufficient stock
        sku = self.repo.get_sku_by_id(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        # Calculate available quantity (on-hand minus pending reservations)
        available = self._calculate_available_stock(sku_id)
        if available < qty:
            raise ValueError(f"Insufficient stock: {available} available, {qty} requested")

        # Create reservation
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        return self.repo.create_reservation(sku_id, qty, idempotency_key, expires_at)

    def confirm_reservation(self, reservation_id: int) -> tuple[ReservationModel, OrderModel]:
        """Confirm a reservation and create an order."""
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        # Check status
        if reservation.status == "confirmed":
            # Find the associated order
            with self.repo.get_session() as session:
                stmt = select(OrderModel).where(OrderModel.reservation_id == reservation_id)
                order = session.execute(stmt).scalar_one()
                session.expunge(order)
            return reservation, order

        if reservation.status != "pending":
            raise ValueError(f"Cannot confirm reservation with status '{reservation.status}'")

        # Check expiration
        if datetime.utcnow() > reservation.expires_at:
            # Mark as cancelled implicitly by expiration
            self.repo.cancel_reservation(reservation_id)
            raise ValueError("Reservation has expired")

        # Confirm and deduct from stock
        self.repo.adjust_stock(reservation.sku_id, -reservation.qty)
        confirmed_res = self.repo.confirm_reservation(reservation_id)
        order = self.repo.create_order(reservation_id, reservation.sku_id, reservation.qty)

        return confirmed_res, order

    def cancel_reservation(self, reservation_id: int) -> ReservationModel:
        """Cancel a reservation."""
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status == "cancelled":
            return reservation

        if reservation.status != "pending":
            raise ValueError(f"Cannot cancel reservation with status '{reservation.status}'")

        return self.repo.cancel_reservation(reservation_id)

    # Order operations
    def get_order(self, order_id: int) -> Optional[OrderModel]:
        """Get order by ID."""
        return self.repo.get_order_by_id(order_id)

    def list_orders(self, offset: int = 0, limit: int = 50) -> tuple[list[OrderModel], int]:
        """List orders with pagination."""
        if offset < 0 or limit <= 0 or limit > 1000:
            raise ValueError("Invalid pagination parameters")
        return self.repo.list_orders(offset, limit)

    # Helper methods
    def _calculate_available_stock(self, sku_id: int) -> int:
        """Calculate available stock (on-hand minus pending/confirmed reservations)."""
        sku = self.repo.get_sku_by_id(sku_id)
        if not sku:
            return 0

        # Count pending reservations
        with self.repo.get_session() as session:
            stmt = select(
                func.coalesce(func.sum(ReservationModel.qty), 0)
            ).where(
                (ReservationModel.sku_id == sku_id) & (ReservationModel.status == "pending")
            )
            reserved = session.execute(stmt).scalar()

        return max(0, sku.qty_on_hand - reserved)
