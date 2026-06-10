"""Business logic service layer."""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException, status

from .models import OrderResponse, ReservationResponse, SKUResponse
from .repository import Repository


class CommerceService:
    """Service for commerce operations."""

    RESERVATION_EXPIRY_SECONDS = 300

    def __init__(self, repository: Repository):
        """Initialize service with repository."""
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> SKUResponse:
        """Create a new SKU."""
        sku_model = self.repo.create_sku(sku, initial_stock)
        return SKUResponse(sku=sku_model.sku, stock=sku_model.stock)

    def adjust_stock(self, sku: str, amount: int) -> SKUResponse:
        """Adjust stock for a SKU."""
        sku_model = self.repo.get_sku(sku)
        if not sku_model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku} not found",
            )

        new_stock = sku_model.stock + amount
        if new_stock < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Stock cannot be negative",
            )

        updated_sku = self.repo.update_sku_stock(sku, new_stock)
        return SKUResponse(sku=updated_sku.sku, stock=updated_sku.stock)

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> ReservationResponse:
        """Create a reservation for inventory."""
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return ReservationResponse(
                id=existing.id,
                sku=existing.sku,
                quantity=existing.quantity,
                status=existing.status,
                created_at=existing.created_at,
                idempotency_key=existing.idempotency_key,
            )

        sku_model = self.repo.get_sku(sku)
        if not sku_model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku} not found",
            )

        if sku_model.stock < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock",
            )

        sku_model.stock -= quantity
        self.repo.update_sku_stock(sku, sku_model.stock)

        reservation = self.repo.create_reservation(sku, quantity, idempotency_key)
        return ReservationResponse(
            id=reservation.id,
            sku=reservation.sku,
            quantity=reservation.quantity,
            status=reservation.status,
            created_at=reservation.created_at,
            idempotency_key=reservation.idempotency_key,
        )

    def confirm_reservation(self, reservation_id: int) -> ReservationResponse:
        """Confirm a pending reservation."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
            )

        if reservation.status != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot confirm reservation with status {reservation.status}",
            )

        now = datetime.utcnow()
        age_seconds = (now - reservation.created_at).total_seconds()

        if age_seconds > self.RESERVATION_EXPIRY_SECONDS:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            sku_model = self.repo.get_sku(reservation.sku)
            if sku_model:
                sku_model.stock += reservation.quantity
                self.repo.update_sku_stock(reservation.sku, sku_model.stock)

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation expired",
            )

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        self.repo.create_order(reservation_id)

        updated_reservation = self.repo.get_reservation(reservation_id)
        return ReservationResponse(
            id=updated_reservation.id,
            sku=updated_reservation.sku,
            quantity=updated_reservation.quantity,
            status=updated_reservation.status,
            created_at=updated_reservation.created_at,
            idempotency_key=updated_reservation.idempotency_key,
        )

    def cancel_reservation(self, reservation_id: int) -> ReservationResponse:
        """Cancel a pending reservation."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
            )

        if reservation.status != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel reservation with status {reservation.status}",
            )

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        sku_model = self.repo.get_sku(reservation.sku)
        if sku_model:
            sku_model.stock += reservation.quantity
            self.repo.update_sku_stock(reservation.sku, sku_model.stock)

        updated_reservation = self.repo.get_reservation(reservation_id)
        return ReservationResponse(
            id=updated_reservation.id,
            sku=updated_reservation.sku,
            quantity=updated_reservation.quantity,
            status=updated_reservation.status,
            created_at=updated_reservation.created_at,
            idempotency_key=updated_reservation.idempotency_key,
        )

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[OrderResponse], int]:
        """Get paginated orders."""
        if page < 1:
            page = 1
        if size < 1:
            size = 10

        orders, total = self.repo.get_orders(page, size)
        return (
            [
                OrderResponse(
                    id=order.id,
                    reservation_id=order.reservation_id,
                    created_at=order.created_at,
                )
                for order in orders
            ],
            total,
        )
