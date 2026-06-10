"""Business logic layer."""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException, status

from .models import Reservation, Order, SKU
from .repository import Repository


class CommerceService:
    """Service for commerce operations."""

    RESERVATION_EXPIRATION_SECONDS = 300

    def __init__(self, repository: Repository):
        """Initialize service with a repository."""
        self.repository = repository

    def create_sku(self, sku: str, initial_stock: int) -> SKU:
        """Create a new SKU."""
        return self.repository.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> dict:
        """Adjust stock for a SKU."""
        sku_obj = self.repository.get_sku_by_name(sku)
        if not sku_obj:
            raise HTTPException(status_code=404, detail="SKU not found")

        updated_sku = self.repository.update_sku_stock(sku_obj.id, amount)
        return {"sku": updated_sku.sku, "stock": updated_sku.stock}

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> Reservation:
        """Create a reservation with idempotency guarantee."""
        existing = self.repository.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        sku_obj = self.repository.get_sku_by_name(sku)
        if not sku_obj:
            raise HTTPException(status_code=404, detail="SKU not found")

        if sku_obj.stock < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock",
            )

        self.repository.update_sku_stock(sku_obj.id, -quantity)
        reservation = self.repository.create_reservation(
            sku_obj.id, sku, quantity, idempotency_key
        )
        return reservation

    def confirm_reservation(self, reservation_id: int) -> Order:
        """Confirm a reservation and create an order."""
        reservation = self.repository.get_reservation_by_id(reservation_id)
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")

        if reservation.status != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot confirm reservation with status {reservation.status}",
            )

        age_seconds = (datetime.utcnow() - reservation.created_at).total_seconds()
        if age_seconds > self.RESERVATION_EXPIRATION_SECONDS:
            self.repository.update_reservation_status(reservation_id, "EXPIRED")
            sku_obj = self.repository.get_sku_by_name(reservation.sku)
            if sku_obj:
                self.repository.update_sku_stock(sku_obj.id, reservation.quantity)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation expired",
            )

        self.repository.update_reservation_status(reservation_id, "CONFIRMED")
        order = self.repository.create_order(reservation_id)
        return order

    def cancel_reservation(self, reservation_id: int) -> Reservation:
        """Cancel a reservation and restore stock."""
        reservation = self.repository.get_reservation_by_id(reservation_id)
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")

        if reservation.status != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel reservation with status {reservation.status}",
            )

        self.repository.update_reservation_status(reservation_id, "CANCELLED")
        sku_obj = self.repository.get_sku_by_name(reservation.sku)
        if sku_obj:
            self.repository.update_sku_stock(sku_obj.id, reservation.quantity)
        return reservation

    def list_orders(self, page: int = 1, size: int = 10) -> dict:
        """List orders with pagination."""
        orders, total = self.repository.list_orders(page, size)
        return {
            "items": orders,
            "page": page,
            "size": size,
            "total": total,
        }
