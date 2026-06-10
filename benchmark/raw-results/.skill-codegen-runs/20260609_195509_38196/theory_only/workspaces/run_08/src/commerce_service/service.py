from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from commerce_service.models import SKU, Reservation, Order, ReservationStatus, OrderStatus
from commerce_service.repository import SKURepository, ReservationRepository, OrderRepository


RESERVATION_TTL_MINUTES = 15


class CommerceService:
    def __init__(self, db: Session):
        self.db = db
        self.sku_repo = SKURepository(db)
        self.reservation_repo = ReservationRepository(db)
        self.order_repo = OrderRepository(db)

    def create_sku(self, code: str, stock: int) -> SKU:
        existing = self.sku_repo.get_by_code(code)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"SKU with code '{code}' already exists",
            )
        return self.sku_repo.create(code, stock)

    def adjust_stock(self, sku_id: int, quantity: int) -> SKU:
        sku = self.sku_repo.get_by_id(sku_id)
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku_id} not found",
            )
        result = self.sku_repo.adjust_stock(sku_id, quantity)
        return result

    def reserve(self, sku_id: int, quantity: int, idempotency_key: str) -> Reservation:
        self.reservation_repo.expire_stale()

        existing = self.reservation_repo.get_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        sku = self.sku_repo.get_by_id(sku_id)
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku_id} not found",
            )

        available = sku.stock - sku.reserved_count
        if available < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient stock. Available: {available}, Requested: {quantity}",
            )

        sku.reserved_count += quantity
        self.db.commit()

        expires_at = datetime.utcnow() + timedelta(minutes=RESERVATION_TTL_MINUTES)
        reservation = self.reservation_repo.create(sku_id, quantity, idempotency_key, expires_at)

        return reservation

    def confirm_reservation(self, reservation_id: int) -> Order:
        reservation = self.reservation_repo.get_by_id(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
            )

        self.reservation_repo.expire_stale()
        reservation = self.reservation_repo.get_by_id(reservation_id)

        if reservation.status == ReservationStatus.EXPIRED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation has expired",
            )

        if reservation.status == ReservationStatus.CANCELLED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation has been cancelled",
            )

        if reservation.status == ReservationStatus.CONFIRMED:
            existing_order = self.order_repo.get_by_reservation_id(reservation_id)
            if existing_order:
                return existing_order

        self.reservation_repo.confirm(reservation_id)
        order = self.order_repo.create(reservation_id, reservation.sku_id, reservation.quantity)

        return order

    def cancel_reservation(self, reservation_id: int) -> Reservation:
        reservation = self.reservation_repo.get_by_id(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
            )

        if reservation.status != ReservationStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel reservation with status '{reservation.status}'",
            )

        return self.reservation_repo.cancel(reservation_id)

    def list_orders(self, skip: int = 0, limit: int = 10) -> tuple[list[Order], int]:
        return self.order_repo.list_paginated(skip, limit)
