from datetime import datetime, timedelta
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from commerce_service.repository import Repository
from commerce_service.models import Reservation, SKU, Order


class CommercService:
    def __init__(self, session: Session):
        self.repo = Repository(session)

    def create_sku(self, sku: str, initial_stock: int) -> SKU:
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> SKU:
        sku_record = self.repo.get_sku_by_name(sku)
        if not sku_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKU not found",
            )
        return self.repo.adjust_stock(sku_record.id, amount)

    def create_reservation(
        self,
        sku: str,
        quantity: int,
        idempotency_key: str,
    ) -> Reservation:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        sku_record = self.repo.get_sku_by_name(sku)
        if not sku_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKU not found",
            )

        if sku_record.available_stock < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock",
            )

        self.repo.reserve_stock(sku_record.id, quantity)
        reservation = self.repo.create_reservation(
            sku_record.id,
            sku,
            quantity,
            idempotency_key,
        )
        return reservation

    def confirm_reservation(self, reservation_id: int) -> Reservation:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )

        if reservation.status != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation is not in PENDING status",
            )

        now = datetime.utcnow()
        created_time = reservation.created_at
        if (now - created_time) > timedelta(seconds=300):
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            sku_record = self.repo.get_sku_by_name(reservation.sku)
            if sku_record:
                self.repo.restore_stock(sku_record.id, reservation.quantity)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation expired",
            )

        reservation = self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        self.repo.create_order(reservation_id)
        return reservation

    def cancel_reservation(self, reservation_id: int) -> Reservation:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )

        if reservation.status != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation is not in PENDING status",
            )

        sku_record = self.repo.get_sku_by_name(reservation.sku)
        if sku_record:
            self.repo.restore_stock(sku_record.id, reservation.quantity)

        reservation = self.repo.update_reservation_status(reservation_id, "CANCELLED")
        return reservation

    def get_orders(self, page: int = 1, size: int = 10):
        orders, total = self.repo.get_orders(page, size)
        return orders, total
