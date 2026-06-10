import sqlite3
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException, status
from src.commerce_service.repository import Repository


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        try:
            return self.repo.create_sku(sku, initial_stock)
        except sqlite3.IntegrityError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"SKU {sku} already exists"
            )

    def adjust_stock(self, sku: str, amount: int) -> dict:
        sku_data = self.repo.get_sku_by_name(sku)
        if not sku_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku} not found"
            )

        return self.repo.adjust_stock(sku, amount)

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> dict:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        sku_data = self.repo.get_sku_by_name(sku)
        if not sku_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku} not found"
            )

        if sku_data["available_stock"] < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock"
            )

        self.repo.adjust_stock(sku, -quantity)
        reservation = self.repo.create_reservation(sku, quantity, idempotency_key)

        return reservation

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found"
            )

        if reservation["status"] != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Reservation is not PENDING"
            )

        created_at = datetime.fromisoformat(reservation["created_at"])
        now = datetime.utcnow()
        age_seconds = (now - created_at).total_seconds()

        if age_seconds > 300:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.adjust_stock(reservation["sku"], reservation["quantity"])
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation expired"
            )

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        self.repo.create_order(reservation_id)

        return {"id": reservation_id, "status": "CONFIRMED"}

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reservation {reservation_id} not found"
            )

        if reservation["status"] != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Reservation is not PENDING"
            )

        self.repo.adjust_stock(reservation["sku"], reservation["quantity"])
        self.repo.update_reservation_status(reservation_id, "CANCELLED")

        return {"id": reservation_id, "status": "CANCELLED"}

    def list_orders(self, page: int = 1, size: int = 10) -> dict:
        if page < 1 or size < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="page and size must be >= 1"
            )

        offset = (page - 1) * size
        orders, total = self.repo.list_orders(offset, size)

        return {
            "page": page,
            "size": size,
            "total": total,
            "orders": orders
        }
