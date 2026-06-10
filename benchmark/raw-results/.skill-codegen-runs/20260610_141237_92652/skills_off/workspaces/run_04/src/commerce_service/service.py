from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .models import ReservationResponse, OrderResponse
from .repository import Repository


class CommerceService:
    EXPIRATION_SECONDS = 300

    def __init__(self, db: Session):
        self.db = db
        self.repo = Repository(db)

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        existing = self.repo.get_sku_by_code(sku)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="SKU already exists",
            )
        sku_obj = self.repo.create_sku(sku, initial_stock)
        return {"id": sku_obj.id, "sku": sku_obj.sku, "stock": sku_obj.stock_level}

    def adjust_stock(self, sku: str, amount: int) -> dict:
        sku_obj = self.repo.get_sku_by_code(sku)
        if not sku_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKU not found",
            )
        new_stock = sku_obj.stock_level + amount
        if new_stock < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock for adjustment",
            )
        updated_sku = self.repo.update_sku_stock(sku_obj.id, new_stock)
        return {"sku": updated_sku.sku, "stock": updated_sku.stock_level}

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> ReservationResponse:
        existing_reservation = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing_reservation:
            return ReservationResponse(
                id=existing_reservation.id,
                sku=existing_reservation.sku_code,
                quantity=existing_reservation.quantity,
                status=existing_reservation.status,
                created_at=existing_reservation.created_at,
            )

        sku_obj = self.repo.get_sku_by_code(sku)
        if not sku_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKU not found",
            )

        if sku_obj.stock_level < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock",
            )

        new_stock = sku_obj.stock_level - quantity
        self.repo.update_sku_stock(sku_obj.id, new_stock)

        now = datetime.now(timezone.utc)
        reservation = self.repo.create_reservation(
            sku_id=sku_obj.id,
            sku_code=sku,
            quantity=quantity,
            status="PENDING",
            created_at=now,
            idempotency_key=idempotency_key,
        )

        return ReservationResponse(
            id=reservation.id,
            sku=reservation.sku_code,
            quantity=reservation.quantity,
            status=reservation.status,
            created_at=reservation.created_at,
        )

    def confirm_reservation(self, reservation_id: int) -> ReservationResponse:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )

        if reservation.status != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot confirm non-PENDING reservation (status: {reservation.status})",
            )

        now = datetime.now(timezone.utc)
        elapsed = (now - reservation.created_at).total_seconds()

        if elapsed > self.EXPIRATION_SECONDS:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")

            sku_obj = self.repo.get_sku_by_id(reservation.sku_id)
            if sku_obj:
                restored_stock = sku_obj.stock_level + reservation.quantity
                self.repo.update_sku_stock(sku_obj.id, restored_stock)

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation expired",
            )

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        self.repo.create_order(reservation_id, now)

        updated_reservation = self.repo.get_reservation_by_id(reservation_id)
        return ReservationResponse(
            id=updated_reservation.id,
            sku=updated_reservation.sku_code,
            quantity=updated_reservation.quantity,
            status=updated_reservation.status,
            created_at=updated_reservation.created_at,
        )

    def cancel_reservation(self, reservation_id: int) -> ReservationResponse:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )

        if reservation.status != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel non-PENDING reservation (status: {reservation.status})",
            )

        self.repo.update_reservation_status(reservation_id, "CANCELLED")

        sku_obj = self.repo.get_sku_by_id(reservation.sku_id)
        if sku_obj:
            restored_stock = sku_obj.stock_level + reservation.quantity
            self.repo.update_sku_stock(sku_obj.id, restored_stock)

        updated_reservation = self.repo.get_reservation_by_id(reservation_id)
        return ReservationResponse(
            id=updated_reservation.id,
            sku=updated_reservation.sku_code,
            quantity=updated_reservation.quantity,
            status=updated_reservation.status,
            created_at=updated_reservation.created_at,
        )

    def get_orders(self, page: int = 1, size: int = 10) -> dict:
        if page < 1:
            page = 1
        if size < 1:
            size = 10

        offset = (page - 1) * size
        orders, total = self.repo.get_orders(offset=offset, limit=size)

        return {
            "page": page,
            "size": size,
            "total": total,
            "orders": [
                OrderResponse(
                    id=order.id,
                    reservation_id=order.reservation_id,
                    created_at=order.created_at,
                )
                for order in orders
            ],
        }
