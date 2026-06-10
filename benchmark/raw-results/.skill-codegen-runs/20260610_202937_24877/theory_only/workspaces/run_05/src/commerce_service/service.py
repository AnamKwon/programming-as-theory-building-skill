from datetime import datetime, timedelta
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from .repository import Repository

RESERVATION_TTL_SECONDS = 300


class CommerceService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = Repository(db)

    def create_sku(self, sku: str, initial_stock: int):
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int):
        sku_obj = self.repo.get_sku(sku)
        if not sku_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="SKU not found"
            )
        return self.repo.adjust_stock(sku, amount)

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str):
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        sku_obj = self.repo.get_sku(sku)
        if not sku_obj or sku_obj.available_stock < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock"
            )

        self.repo.adjust_stock(sku, -quantity)
        return self.repo.create_reservation(sku, quantity, idempotency_key)

    def confirm_reservation(self, reservation_id: int):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found"
            )

        if reservation.status != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation is not in PENDING status"
            )

        created_at = reservation.created_at
        now = datetime.utcnow()
        if (now - created_at).total_seconds() > RESERVATION_TTL_SECONDS:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.adjust_stock(reservation.sku, reservation.quantity)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation expired"
            )

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        self.repo.create_order(reservation_id, reservation.sku, reservation.quantity)
        updated_reservation = self.repo.get_reservation(reservation_id)
        return updated_reservation

    def cancel_reservation(self, reservation_id: int):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found"
            )

        if reservation.status != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation is not in PENDING status"
            )

        self.repo.adjust_stock(reservation.sku, reservation.quantity)
        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        updated_reservation = self.repo.get_reservation(reservation_id)
        return updated_reservation

    def get_orders(self, page: int = 1, size: int = 10):
        return self.repo.get_orders(page, size)
