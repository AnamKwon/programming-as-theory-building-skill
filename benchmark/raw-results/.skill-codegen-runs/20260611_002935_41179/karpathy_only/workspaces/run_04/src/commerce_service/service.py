from datetime import datetime
from typing import Optional
from fastapi import HTTPException, status
from commerce_service.repository import Repository, Reservation, Order


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int):
        db_sku = self.repo.create_sku(sku, initial_stock)
        return {"sku": db_sku.sku, "initial_stock": db_sku.available_stock}

    def adjust_stock(self, sku: str, amount: int) -> dict:
        db_sku = self.repo.get_sku_by_name(sku)
        if not db_sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU '{sku}' not found"
            )
        updated_sku = self.repo.adjust_stock(sku, amount)
        return {"sku": updated_sku.sku, "available_stock": updated_sku.available_stock}

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> dict:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return {
                "id": existing.id,
                "sku": existing.sku,
                "quantity": existing.quantity,
                "status": existing.status,
                "idempotency_key": existing.idempotency_key,
                "created_at": existing.created_at
            }

        db_sku = self.repo.get_sku_by_name(sku)
        if not db_sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU '{sku}' not found"
            )

        if db_sku.available_stock < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock"
            )

        self.repo.adjust_stock(sku, -quantity)
        reservation = self.repo.create_reservation(sku, quantity, idempotency_key)

        return {
            "id": reservation.id,
            "sku": reservation.sku,
            "quantity": reservation.quantity,
            "status": reservation.status,
            "idempotency_key": reservation.idempotency_key,
            "created_at": reservation.created_at
        }

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found"
            )

        if reservation.status != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot confirm reservation with status '{reservation.status}'"
            )

        now = datetime.utcnow()
        elapsed = (now - reservation.created_at).total_seconds()
        if elapsed > 300:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.adjust_stock(reservation.sku, reservation.quantity)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation expired"
            )

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        order = self.repo.create_order(reservation_id, reservation.sku, reservation.quantity)

        return {
            "id": order.id,
            "reservation_id": order.reservation_id,
            "sku": order.sku,
            "quantity": order.quantity,
            "created_at": order.created_at
        }

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found"
            )

        if reservation.status != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel reservation with status '{reservation.status}'"
            )

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        self.repo.adjust_stock(reservation.sku, reservation.quantity)

        return {
            "id": reservation.id,
            "sku": reservation.sku,
            "quantity": reservation.quantity,
            "status": "CANCELLED",
            "idempotency_key": reservation.idempotency_key,
            "created_at": reservation.created_at
        }

    def get_orders(self, page: int = 1, size: int = 10) -> dict:
        orders, total = self.repo.get_orders(page, size)
        return {
            "items": [
                {
                    "id": order.id,
                    "reservation_id": order.reservation_id,
                    "sku": order.sku,
                    "quantity": order.quantity,
                    "created_at": order.created_at
                }
                for order in orders
            ],
            "page": page,
            "size": size,
            "total": total
        }
