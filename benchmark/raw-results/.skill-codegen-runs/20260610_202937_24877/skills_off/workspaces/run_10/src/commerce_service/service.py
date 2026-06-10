"""Business logic layer."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from .models import OrderModel, ReservationModel, SKUModel
from .repository import OrderRepository, ReservationRepository, SKURepository


class CommerceService:
    """Main commerce service."""

    def __init__(self, session: Session):
        self.session = session
        self.sku_repo = SKURepository(session)
        self.reservation_repo = ReservationRepository(session)
        self.order_repo = OrderRepository(session)

    def create_sku(self, sku: str, initial_stock: int) -> SKUModel:
        """Create a new SKU."""
        return self.sku_repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> SKUModel:
        """Adjust stock level."""
        result = self.sku_repo.update_stock(sku, amount)
        if not result:
            raise ValueError(f"SKU {sku} not found")
        return result

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> ReservationModel:
        """Create a reservation with stock validation and idempotency."""
        # Check if idempotency key already exists
        existing = self.reservation_repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        # Check stock availability
        sku_model = self.sku_repo.get_sku(sku)
        if not sku_model:
            raise ValueError(f"SKU {sku} not found")

        if sku_model.available_stock < quantity:
            raise ValueError("Insufficient stock")

        # Deduct stock and create reservation
        self.sku_repo.update_stock(sku, -quantity)
        reservation = self.reservation_repo.create_reservation(sku, quantity, idempotency_key)
        return reservation

    def confirm_reservation(self, reservation_id: int) -> OrderModel:
        """Confirm a reservation and create an order."""
        reservation = self.reservation_repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != "PENDING":
            raise ValueError(f"Reservation is not in PENDING state, current state: {reservation.status}")

        # Check if reservation is expired (more than 300 seconds old)
        now = datetime.now(timezone.utc)
        created_at_utc = reservation.created_at.replace(tzinfo=timezone.utc)
        age_seconds = (now - created_at_utc).total_seconds()

        if age_seconds > 300:
            # Mark as expired and restore stock
            self.reservation_repo.update_reservation_status(reservation_id, "EXPIRED")
            self.sku_repo.update_stock(reservation.sku, reservation.quantity)
            raise ValueError("Reservation expired")

        # Update reservation status and create order
        self.reservation_repo.update_reservation_status(reservation_id, "CONFIRMED")
        order = self.order_repo.create_order(reservation_id, reservation.sku, reservation.quantity)
        return order

    def cancel_reservation(self, reservation_id: int) -> ReservationModel:
        """Cancel a reservation and restore stock."""
        reservation = self.reservation_repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != "PENDING":
            raise ValueError(f"Reservation is not in PENDING state, current state: {reservation.status}")

        # Restore stock and update status
        self.sku_repo.update_stock(reservation.sku, reservation.quantity)
        updated = self.reservation_repo.update_reservation_status(reservation_id, "CANCELLED")
        return updated

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[OrderModel], int]:
        """Get paginated orders."""
        return self.order_repo.get_orders_paginated(page, size)
