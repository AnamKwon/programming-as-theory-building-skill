"""Business logic layer."""

from datetime import datetime
from typing import Optional, Tuple

from fastapi import HTTPException, status

from .repository import OrderRepository, ReservationRepository, SKURepository


RESERVATION_EXPIRATION_SECONDS = 300


class CommerceService:
    """Main service for commerce operations."""

    @staticmethod
    def create_sku(sku: str, initial_stock: int) -> dict:
        """Create a new SKU with initial stock."""
        try:
            return SKURepository.create_sku(sku, initial_stock)
        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"SKU '{sku}' already exists",
                )
            raise

    @staticmethod
    def adjust_stock(sku: str, amount: int) -> dict:
        """Adjust stock for a SKU."""
        sku_data = SKURepository.get_sku_by_name(sku)
        if not sku_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU '{sku}' not found",
            )

        updated = SKURepository.adjust_stock(sku, amount)
        if updated["available_stock"] < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock for adjustment",
            )

        return updated

    @staticmethod
    def create_reservation(sku: str, quantity: int, idempotency_key: str) -> dict:
        """Create a reservation with idempotency."""
        existing = ReservationRepository.get_reservation_by_idempotency_key(
            idempotency_key
        )
        if existing:
            return existing

        sku_data = SKURepository.get_sku_by_name(sku)
        if not sku_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU '{sku}' not found",
            )

        if sku_data["available_stock"] < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock",
            )

        SKURepository.adjust_stock(sku, -quantity)

        created_at = datetime.utcnow()
        return ReservationRepository.create_reservation(
            sku_data["id"],
            sku,
            quantity,
            idempotency_key,
            created_at,
        )

    @staticmethod
    def confirm_reservation(reservation_id: int) -> dict:
        """Confirm a pending reservation."""
        reservation = ReservationRepository.get_reservation_by_id(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
            )

        if reservation["status"] != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Reservation is not in PENDING status",
            )

        now = datetime.utcnow()
        elapsed = (now - reservation["created_at"]).total_seconds()

        if elapsed > RESERVATION_EXPIRATION_SECONDS:
            ReservationRepository.update_reservation_status(reservation_id, "EXPIRED")
            SKURepository.adjust_stock(reservation["sku"], reservation["quantity"])
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation expired",
            )

        ReservationRepository.update_reservation_status(reservation_id, "CONFIRMED")

        OrderRepository.create_order(
            reservation_id,
            reservation["sku_id"],
            reservation["sku"],
            reservation["quantity"],
        )

        updated = ReservationRepository.get_reservation_by_id(reservation_id)
        return updated

    @staticmethod
    def cancel_reservation(reservation_id: int) -> dict:
        """Cancel a pending reservation."""
        reservation = ReservationRepository.get_reservation_by_id(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
            )

        if reservation["status"] != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation is not in PENDING status",
            )

        ReservationRepository.update_reservation_status(reservation_id, "CANCELLED")
        SKURepository.adjust_stock(reservation["sku"], reservation["quantity"])

        updated = ReservationRepository.get_reservation_by_id(reservation_id)
        return updated

    @staticmethod
    def get_orders(page: int = 1, size: int = 10) -> Tuple[list, int]:
        """Get orders with pagination."""
        if page < 1 or size < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="page and size must be >= 1",
            )
        return OrderRepository.get_orders(page, size)
