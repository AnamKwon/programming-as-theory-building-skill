"""Business logic layer."""

from datetime import datetime, timedelta
from typing import Optional, Tuple

from .repository import Repository
from .models import SKU, Reservation, Order


class CommercService:
    """Business logic for inventory and orders."""

    RESERVATION_EXPIRATION_SECONDS = 300

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> SKU:
        """Create a new SKU with initial stock."""
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> int:
        """Adjust stock for a SKU."""
        return self.repo.adjust_stock(sku, amount)

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> Tuple[Reservation, bool]:
        """
        Create a reservation with idempotency.
        Returns (reservation, is_new) where is_new=False if reservation already existed.
        """
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing, False

        db_sku = self.repo.get_sku_by_name(sku)
        if not db_sku:
            raise ValueError(f"SKU {sku} not found")

        if db_sku.stock < quantity:
            raise ValueError("Insufficient stock")

        self.repo.deduct_stock(db_sku.id, quantity)

        reservation = self.repo.create_reservation(db_sku.id, sku, quantity, idempotency_key)

        return reservation, True

    def confirm_reservation(self, reservation_id: int) -> Tuple[Reservation, Order]:
        """Confirm a reservation and create an order."""
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != "PENDING":
            raise ValueError(f"Cannot confirm reservation with status {reservation.status}")

        created_at = reservation.created_at
        now = datetime.utcnow()
        age_seconds = (now - created_at).total_seconds()

        if age_seconds > self.RESERVATION_EXPIRATION_SECONDS:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            db_sku = self.repo.get_sku_by_id(reservation.sku_id)
            if db_sku:
                self.repo.restore_stock(db_sku.id, reservation.quantity)
            raise ValueError("Reservation expired")

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        order = self.repo.create_order(reservation_id)

        reservation = self.repo.get_reservation_by_id(reservation_id)

        return reservation, order

    def cancel_reservation(self, reservation_id: int) -> Reservation:
        """Cancel a reservation and restore stock."""
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != "PENDING":
            raise ValueError(f"Cannot cancel reservation with status {reservation.status}")

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        db_sku = self.repo.get_sku_by_id(reservation.sku_id)
        if db_sku:
            self.repo.restore_stock(db_sku.id, reservation.quantity)

        return self.repo.get_reservation_by_id(reservation_id)

    def get_orders_paginated(self, page: int = 1, size: int = 10) -> Tuple[list[Order], int]:
        """Get paginated orders."""
        if page < 1:
            page = 1
        if size < 1:
            size = 10

        orders, total = self.repo.get_orders_paginated(page, size)
        return orders, total
