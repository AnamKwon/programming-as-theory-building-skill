from datetime import datetime
from fastapi import HTTPException
from commerce_service.repository import Repository
from typing import Dict, Any


RESERVATION_EXPIRY_SECONDS = 300


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> Dict[str, Any]:
        try:
            return self.repo.create_sku(sku, initial_stock)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    def adjust_stock(self, sku: str, amount: int) -> Dict[str, Any]:
        sku_obj = self.repo.get_sku_by_name(sku)
        if sku_obj is None:
            raise HTTPException(status_code=404, detail=f"SKU {sku} not found")
        return self.repo.adjust_stock(sku, amount)

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> Dict[str, Any]:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        sku_obj = self.repo.get_sku_by_name(sku)
        if sku_obj is None:
            raise HTTPException(status_code=404, detail=f"SKU {sku} not found")

        if sku_obj["available_stock"] < quantity:
            raise HTTPException(status_code=400, detail="Insufficient stock")

        self.repo.deduct_stock(sku, quantity)

        reservation = self.repo.create_reservation(
            sku_obj["id"], sku, quantity, idempotency_key
        )
        return reservation

    def confirm_reservation(self, reservation_id: int) -> Dict[str, Any]:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if reservation is None:
            raise HTTPException(status_code=404, detail="Reservation not found")

        if reservation["status"] != "PENDING":
            raise HTTPException(
                status_code=400,
                detail=f"Reservation is {reservation['status']}, not PENDING",
            )

        created_at = datetime.fromisoformat(reservation["created_at"])
        now = datetime.utcnow()
        age_seconds = (now - created_at).total_seconds()

        if age_seconds > RESERVATION_EXPIRY_SECONDS:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.restore_stock(reservation["sku"], reservation["quantity"])
            raise HTTPException(status_code=400, detail="Reservation expired")

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        order = self.repo.create_order(reservation_id)

        return order

    def cancel_reservation(self, reservation_id: int) -> Dict[str, Any]:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if reservation is None:
            raise HTTPException(status_code=404, detail="Reservation not found")

        if reservation["status"] != "PENDING":
            raise HTTPException(
                status_code=400,
                detail=f"Reservation is {reservation['status']}, not PENDING",
            )

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        self.repo.restore_stock(reservation["sku"], reservation["quantity"])

        return {
            "id": reservation_id,
            "status": "CANCELLED",
            "restored_quantity": reservation["quantity"],
        }

    def get_orders(self, page: int = 1, size: int = 10) -> Dict[str, Any]:
        if page < 1:
            page = 1
        if size < 1:
            size = 10
        return self.repo.get_orders(page, size)
