from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .models import ReservationStatus
from .repository import OrderRepository, ReservationRepository, SKURepository


class CommerceService:
    RESERVATION_TTL_MINUTES = 30

    def __init__(self, session: Session):
        self.sku_repo = SKURepository(session)
        self.reservation_repo = ReservationRepository(session)
        self.order_repo = OrderRepository(session)

    def create_sku(self, sku_code: str, name: str, stock_quantity: int):
        existing = self.sku_repo.get_by_code(sku_code)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"SKU with code '{sku_code}' already exists",
            )
        return self.sku_repo.create(sku_code, name, stock_quantity)

    def adjust_stock(self, sku_id: int, adjustment: int):
        sku = self.sku_repo.get_by_id(sku_id)
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKU not found",
            )
        if sku.stock_quantity + adjustment < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Adjustment would result in negative stock",
            )
        return self.sku_repo.adjust_stock(sku_id, adjustment)

    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        idempotency_key: Optional[str] = None,
    ):
        self.reservation_repo.expire_stale_reservations()

        if idempotency_key:
            existing = self.reservation_repo.get_by_idempotency_key(idempotency_key)
            if existing:
                if existing.status == ReservationStatus.EXPIRED:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Reservation with this idempotency key has expired",
                    )
                return existing

        sku = self.sku_repo.get_by_id(sku_id)
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKU not found",
            )

        pending_reservations = self.reservation_repo.get_pending_for_sku(sku_id)
        reserved_quantity = sum(r.quantity for r in pending_reservations)
        available_stock = sku.stock_quantity - reserved_quantity

        if available_stock < quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Insufficient stock. Available: {available_stock}, Requested: {quantity}",
            )

        expires_at = datetime.utcnow() + timedelta(minutes=self.RESERVATION_TTL_MINUTES)
        return self.reservation_repo.create(sku_id, quantity, expires_at, idempotency_key)

    def confirm_reservation(self, reservation_id: int):
        reservation = self.reservation_repo.get_by_id(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )

        if reservation.status != ReservationStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot confirm reservation with status '{reservation.status}'",
            )

        if reservation.expires_at <= datetime.utcnow():
            self.reservation_repo.update_status(reservation_id, ReservationStatus.EXPIRED)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation has expired",
            )

        updated = self.reservation_repo.update_status(
            reservation_id, ReservationStatus.CONFIRMED
        )
        return updated

    def cancel_reservation(self, reservation_id: int):
        reservation = self.reservation_repo.get_by_id(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )

        if reservation.status != ReservationStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel reservation with status '{reservation.status}'",
            )

        updated = self.reservation_repo.update_status(
            reservation_id, ReservationStatus.CANCELLED
        )
        return updated

    def get_orders_paginated(self, page: int = 1, page_size: int = 10):
        if page < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Page must be >= 1",
            )
        if page_size < 1 or page_size > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Page size must be between 1 and 100",
            )

        orders, total = self.order_repo.list_paginated(page, page_size)
        total_pages = (total + page_size - 1) // page_size
        return orders, total, page, page_size, total_pages
