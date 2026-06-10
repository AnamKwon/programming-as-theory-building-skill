from datetime import datetime
from typing import Optional, Tuple, List
from .repository import Repository
from fastapi import HTTPException


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        if self.repo.create_sku(sku, initial_stock):
            return {"sku": sku, "available_stock": initial_stock}
        raise HTTPException(status_code=400, detail="SKU already exists")

    def adjust_stock(self, sku: str, amount: int) -> dict:
        sku_obj = self.repo.get_sku(sku)
        if not sku_obj:
            raise HTTPException(status_code=404, detail="SKU not found")

        new_stock = self.repo.adjust_stock(sku, amount)
        if new_stock is None:
            raise HTTPException(status_code=400, detail="Cannot adjust stock")

        return {"sku": sku, "available_stock": new_stock}

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> Tuple[dict, int]:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return {
                "id": existing["id"],
                "sku": existing["sku"],
                "quantity": existing["quantity"],
                "status": existing["status"],
                "created_at": existing["created_at"],
                "idempotency_key": existing["idempotency_key"]
            }, 200

        sku_obj = self.repo.get_sku(sku)
        if not sku_obj:
            raise HTTPException(status_code=404, detail="SKU not found")

        if sku_obj["available_stock"] < quantity:
            raise HTTPException(status_code=400, detail="Insufficient stock")

        if not self.repo.deduct_stock(sku, quantity):
            raise HTTPException(status_code=400, detail="Insufficient stock")

        reservation = self.repo.create_reservation(sku, quantity, idempotency_key)
        if not reservation:
            self.repo.restore_stock(sku, quantity)
            raise HTTPException(status_code=400, detail="Failed to create reservation")

        return reservation, 201

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")

        if reservation["status"] != "PENDING":
            raise HTTPException(
                status_code=400,
                detail=f"Cannot confirm reservation with status {reservation['status']}"
            )

        created_at = datetime.fromisoformat(reservation["created_at"])
        now = datetime.utcnow()
        age_seconds = (now - created_at).total_seconds()

        if age_seconds > 300:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.restore_stock(reservation["sku"], reservation["quantity"])
            raise HTTPException(status_code=400, detail="Reservation expired")

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")

        order = self.repo.create_order(
            reservation_id, reservation["sku"], reservation["quantity"]
        )
        if not order:
            raise HTTPException(status_code=400, detail="Failed to create order")

        return reservation

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")

        if reservation["status"] != "PENDING":
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel reservation with status {reservation['status']}"
            )

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        self.repo.restore_stock(reservation["sku"], reservation["quantity"])

        return reservation

    def get_orders(self, page: int = 1, size: int = 10) -> dict:
        orders, total = self.repo.get_orders(page, size)
        return {
            "orders": orders,
            "page": page,
            "size": size,
            "total": total
        }
