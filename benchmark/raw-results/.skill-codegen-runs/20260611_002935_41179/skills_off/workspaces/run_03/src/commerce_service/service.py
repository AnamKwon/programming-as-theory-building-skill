from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status

from .repository import Repository, SKU, Reservation, Order


RESERVATION_EXPIRY_SECONDS = 300


class CommerceService:
    def __init__(self, repository: Repository):
        self.repository = repository

    def create_sku(self, sku: str, initial_stock: int) -> SKU:
        """Create a new SKU with initial stock."""
        existing = self.repository.get_sku_by_name(sku)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"SKU '{sku}' already exists",
            )
        return self.repository.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> SKU:
        """Adjust stock for a SKU."""
        db_sku = self.repository.get_sku_by_name(sku)
        if not db_sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU '{sku}' not found",
            )
        return self.repository.adjust_stock(sku, amount)

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> Reservation:
        """Create a reservation with idempotency guarantee."""
        # Rule 2: Check idempotency key
        existing_reservation = self.repository.get_reservation_by_idempotency_key(
            idempotency_key
        )
        if existing_reservation:
            return existing_reservation

        # Get SKU
        db_sku = self.repository.get_sku_by_name(sku)
        if not db_sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU '{sku}' not found",
            )

        # Rule 1: Check stock availability
        if db_sku.available_stock < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock",
            )

        # Rule 3: Deduct stock and create reservation
        self.repository.adjust_stock(sku, -quantity)
        reservation = self.repository.create_reservation(
            db_sku.id, sku, quantity, idempotency_key
        )
        return reservation

    def confirm_reservation(self, reservation_id: int) -> tuple[Reservation, Order]:
        """Confirm a pending reservation and create an order."""
        reservation = self.repository.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
            )

        # State validation: must be PENDING
        if reservation.status != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot confirm reservation with status '{reservation.status}'",
            )

        # Expiration check: must be within 300 seconds
        now = datetime.utcnow()
        age_seconds = (now - reservation.created_at).total_seconds()
        if age_seconds > RESERVATION_EXPIRY_SECONDS:
            # Mark as expired
            self.repository.update_reservation_status(reservation_id, "EXPIRED")
            # Restore stock
            self.repository.adjust_stock(reservation.sku, reservation.quantity)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation expired",
            )

        # Confirm reservation and create order
        updated_reservation = self.repository.update_reservation_status(
            reservation_id, "CONFIRMED"
        )
        order = self.repository.create_order(reservation_id)
        return updated_reservation, order

    def cancel_reservation(self, reservation_id: int) -> Reservation:
        """Cancel a reservation and restore stock."""
        reservation = self.repository.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
            )

        # State validation: must be PENDING
        if reservation.status != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel reservation with status '{reservation.status}'",
            )

        # Restore stock
        self.repository.adjust_stock(reservation.sku, reservation.quantity)
        # Mark as cancelled
        updated_reservation = self.repository.update_reservation_status(
            reservation_id, "CANCELLED"
        )
        return updated_reservation

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[Order], int]:
        """Get paginated orders."""
        if page < 1:
            page = 1
        if size < 1:
            size = 10
        return self.repository.get_orders(page, size)
