"""Business logic service layer."""

from datetime import datetime, timezone
from fastapi import HTTPException, status
from src.commerce_service.repository import Repository


class Service:
    RESERVATION_TTL_SECONDS = 300

    def __init__(self, repository: Repository):
        self.repository = repository

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        try:
            return self.repository.create_sku(sku, initial_stock)
        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"SKU {sku} already exists"
                )
            raise

    def adjust_stock(self, sku: str, amount: int) -> dict:
        sku_data = self.repository.get_sku_by_name(sku)
        if not sku_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku} not found"
            )
        return self.repository.adjust_stock(sku, amount)

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> dict:
        existing = self.repository.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        sku_data = self.repository.get_sku_by_name(sku)
        if not sku_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku} not found"
            )

        if sku_data["stock"] < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient stock"
            )

        self.repository.adjust_stock(sku, -quantity)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return self.repository.create_reservation(
            sku_data["id"], sku, quantity, idempotency_key, now
        )

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.repository.get_reservation_by_id(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found"
            )

        if reservation["status"] != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation is not PENDING"
            )

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        created_at = reservation["created_at"]
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        elapsed = (now - created_at).total_seconds()
        if elapsed > self.RESERVATION_TTL_SECONDS:
            self.repository.update_reservation_status(reservation_id, "EXPIRED")
            self.repository.adjust_stock(reservation["sku"], reservation["quantity"])
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation expired"
            )

        self.repository.update_reservation_status(reservation_id, "CONFIRMED")
        order = self.repository.create_order(reservation_id, now)
        return order

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.repository.get_reservation_by_id(reservation_id)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found"
            )

        if reservation["status"] != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation is not PENDING"
            )

        self.repository.update_reservation_status(reservation_id, "CANCELLED")
        self.repository.adjust_stock(reservation["sku"], reservation["quantity"])
        return {"status": "CANCELLED"}

    def list_orders(self, page: int = 1, size: int = 10) -> dict:
        if page < 1:
            page = 1
        if size < 1:
            size = 10
        orders, total = self.repository.list_orders(page, size)
        return {
            "items": orders,
            "page": page,
            "size": size,
            "total": total
        }
