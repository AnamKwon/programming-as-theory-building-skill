from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .models import Reservation, ReservationStatus, SKU, SKUStatus
from .repository import Repository


class CommercService:
    RESERVATION_TTL_SECONDS = 600  # 10 minutes

    def __init__(self, session: Session):
        self.repo = Repository(session)

    def create_sku(self, code: str, quantity: int) -> SKU:
        existing = self.repo.get_sku_by_code(code)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"SKU with code '{code}' already exists",
            )
        return self.repo.create_sku(code, quantity)

    def adjust_stock(self, sku_id: int, adjustment: int) -> SKU:
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku_id} not found",
            )
        if sku.status != SKUStatus.ACTIVE.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot adjust stock for inactive SKU",
            )
        return self.repo.update_sku_stock(sku_id, adjustment)

    def create_reservation(self, sku_id: int, quantity: int, idempotency_key: str) -> Reservation:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing.status == ReservationStatus.CANCELLED.value:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key already used for a cancelled reservation",
                )
            return existing

        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku_id} not found",
            )

        if sku.quantity_available < quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Insufficient stock. Available: {sku.quantity_available}, requested: {quantity}",
            )

        expires_at = datetime.utcnow() + timedelta(seconds=self.RESERVATION_TTL_SECONDS)
        reservation = self.repo.create_reservation(sku_id, quantity, idempotency_key, expires_at)

        sku.quantity_available -= quantity
        self.repo.session.commit()

        return reservation

    def confirm_reservation(self, reservation_id: int) -> Reservation:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
            )

        if reservation.status == ReservationStatus.EXPIRED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation has expired",
            )

        if reservation.status != ReservationStatus.PENDING.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot confirm reservation with status {reservation.status}",
            )

        if datetime.utcnow() > reservation.expires_at:
            self.repo.update_reservation_status(reservation_id, ReservationStatus.EXPIRED.value)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation has expired",
            )

        self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED.value)
        self.repo.create_order(reservation.sku_id, reservation.quantity, reservation_id)

        return self.repo.get_reservation(reservation_id)

    def cancel_reservation(self, reservation_id: int) -> Reservation:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found",
            )

        if reservation.status in [ReservationStatus.CANCELLED.value, ReservationStatus.EXPIRED.value]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel reservation with status {reservation.status}",
            )

        self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED.value)

        sku = self.repo.get_sku(reservation.sku_id)
        if sku:
            sku.quantity_available += reservation.quantity
            self.repo.session.commit()

        return self.repo.get_reservation(reservation_id)

    def get_orders(self, page: int = 1, page_size: int = 10):
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
        orders, total = self.repo.get_orders(page, page_size)
        has_more = (page * page_size) < total
        return orders, total, page, page_size, has_more
