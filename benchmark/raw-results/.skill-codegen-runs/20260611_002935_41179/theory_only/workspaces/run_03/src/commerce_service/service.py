"""Business logic service layer."""

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .models import (
    AdjustStockResponse,
    CreateReservationRequest,
    CreateSKURequest,
    OrderResponse,
    ReservationResponse,
    SKUResponse,
)
from .repository import OrderRepository, ReservationRepository, SKURepository


class CommerceService:
    """Service for commerce operations."""

    def __init__(self, session: Session):
        self.session = session
        self.sku_repo = SKURepository(session)
        self.reservation_repo = ReservationRepository(session)
        self.order_repo = OrderRepository(session)

    def create_sku(self, request: CreateSKURequest) -> SKUResponse:
        """Create a new SKU."""
        sku_model = self.sku_repo.create(request.sku, request.initial_stock)
        return SKUResponse(
            id=sku_model.id,
            sku=sku_model.sku,
            total_stock=sku_model.total_stock,
            reserved_stock=sku_model.reserved_stock,
            available_stock=sku_model.available_stock,
        )

    def adjust_stock(self, sku: str, amount: int) -> AdjustStockResponse:
        """Adjust stock for a SKU."""
        sku_model = self.sku_repo.get_by_sku(sku)
        if not sku_model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku} not found",
            )

        sku_model.total_stock += amount
        sku_model = self.sku_repo.update(sku_model)

        return AdjustStockResponse(
            sku=sku_model.sku,
            total_stock=sku_model.total_stock,
            available_stock=sku_model.available_stock,
        )

    def create_reservation(self, request: CreateReservationRequest) -> ReservationResponse:
        """Create a reservation with idempotency support."""
        # Check if reservation already exists (idempotency)
        existing = self.reservation_repo.get_by_idempotency_key(request.idempotency_key)
        if existing:
            sku_model = self.sku_repo.get_by_sku(request.sku)
            return ReservationResponse(
                id=existing.id,
                sku=request.sku,
                quantity=existing.quantity,
                status=existing.status,
                created_at=existing.created_at,
                idempotency_key=existing.idempotency_key,
            )

        sku_model = self.sku_repo.get_by_sku(request.sku)
        if not sku_model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {request.sku} not found",
            )

        if sku_model.available_stock < request.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock",
            )

        # Deduct from available stock
        sku_model.reserved_stock += request.quantity
        self.sku_repo.update(sku_model)

        # Create reservation
        reservation = self.reservation_repo.create(
            sku_id=sku_model.id,
            quantity=request.quantity,
            idempotency_key=request.idempotency_key,
        )

        return ReservationResponse(
            id=reservation.id,
            sku=request.sku,
            quantity=reservation.quantity,
            status=reservation.status,
            created_at=reservation.created_at,
            idempotency_key=reservation.idempotency_key,
        )

    def confirm_reservation(self, reservation_id: int) -> ReservationResponse:
        """Confirm a reservation and create an order."""
        from .models import SKUModel

        reservation = self.reservation_repo.get_by_id(reservation_id)
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

        # Check expiration (300 seconds)
        now = datetime.utcnow()
        age_seconds = (now - reservation.created_at).total_seconds()
        if age_seconds > 300:
            # Mark as expired
            reservation.status = "EXPIRED"
            self.reservation_repo.update(reservation)

            # Restore stock
            sku_model = self.session.query(SKUModel).filter(SKUModel.id == reservation.sku_id).first()
            if sku_model:
                sku_model.reserved_stock -= reservation.quantity
                self.sku_repo.update(sku_model)

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation expired",
            )

        # Get SKU by ID
        sku_model = self.session.query(SKUModel).filter(SKUModel.id == reservation.sku_id).first()

        # Create order
        self.order_repo.create(reservation_id)

        # Mark as confirmed
        reservation.status = "CONFIRMED"
        self.reservation_repo.update(reservation)

        return ReservationResponse(
            id=reservation.id,
            sku=sku_model.sku if sku_model else "UNKNOWN",
            quantity=reservation.quantity,
            status=reservation.status,
            created_at=reservation.created_at,
            idempotency_key=reservation.idempotency_key,
        )

    def cancel_reservation(self, reservation_id: int) -> ReservationResponse:
        """Cancel a reservation and restore stock."""
        reservation = self.reservation_repo.get_by_id(reservation_id)
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

        # Restore stock
        from .models import SKUModel
        sku_model = self.session.query(SKUModel).filter(SKUModel.id == reservation.sku_id).first()
        if sku_model:
            sku_model.reserved_stock -= reservation.quantity
            self.sku_repo.update(sku_model)

        # Mark as cancelled
        reservation.status = "CANCELLED"
        self.reservation_repo.update(reservation)

        return ReservationResponse(
            id=reservation.id,
            sku=sku_model.sku if sku_model else "UNKNOWN",
            quantity=reservation.quantity,
            status=reservation.status,
            created_at=reservation.created_at,
            idempotency_key=reservation.idempotency_key,
        )

    def get_orders(self, page: int = 1, size: int = 10) -> dict:
        """Get paginated orders."""
        orders, total = self.order_repo.list_paginated(page, size)
        return {
            "orders": [
                OrderResponse(
                    id=order.id,
                    reservation_id=order.reservation_id,
                    created_at=order.created_at,
                )
                for order in orders
            ],
            "page": page,
            "size": size,
            "total": total,
        }
