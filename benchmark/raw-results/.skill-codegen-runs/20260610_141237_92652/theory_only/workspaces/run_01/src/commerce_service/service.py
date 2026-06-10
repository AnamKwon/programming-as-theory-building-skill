from datetime import datetime
from fastapi import HTTPException
from src.commerce_service.repository import Repository


class CommerceService:
    def __init__(self, repository: Repository):
        self.repository = repository

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        return self.repository.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> dict:
        result = self.repository.adjust_stock(sku, amount)
        if result is None:
            raise HTTPException(status_code=404, detail="SKU not found")
        return result

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> dict:
        existing = self.repository.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return {
                "id": existing["id"],
                "sku": existing["sku"],
                "quantity": existing["quantity"],
                "status": existing["status"],
                "idempotency_key": existing["idempotency_key"],
                "created_at": existing["created_at"]
            }

        sku_record = self.repository.get_sku(sku)
        if sku_record is None:
            raise HTTPException(status_code=404, detail="SKU not found")

        if sku_record["available_stock"] < quantity:
            raise HTTPException(status_code=400, detail="Insufficient stock")

        self.repository.adjust_stock(sku, -quantity)

        reservation = self.repository.create_reservation(sku, quantity, idempotency_key)
        return reservation

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.repository.get_reservation(reservation_id)
        if reservation is None:
            raise HTTPException(status_code=404, detail="Reservation not found")

        if reservation["status"] != "PENDING":
            raise HTTPException(status_code=400, detail="Reservation is not in PENDING status")

        created_at = datetime.fromisoformat(reservation["created_at"])
        now = datetime.utcnow()
        elapsed = (now - created_at).total_seconds()

        if elapsed > 300:
            self.repository.update_reservation_status(reservation_id, "EXPIRED")
            self.repository.adjust_stock(reservation["sku"], reservation["quantity"])
            raise HTTPException(status_code=400, detail="Reservation expired")

        self.repository.update_reservation_status(reservation_id, "CONFIRMED")

        order = self.repository.create_order(
            reservation_id,
            reservation["sku"],
            reservation["quantity"]
        )

        return {
            "reservation_id": reservation_id,
            "order_id": order["id"],
            "status": "CONFIRMED",
            "sku": reservation["sku"],
            "quantity": reservation["quantity"]
        }

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.repository.get_reservation(reservation_id)
        if reservation is None:
            raise HTTPException(status_code=404, detail="Reservation not found")

        if reservation["status"] != "PENDING":
            raise HTTPException(status_code=400, detail="Reservation is not in PENDING status")

        self.repository.update_reservation_status(reservation_id, "CANCELLED")
        self.repository.adjust_stock(reservation["sku"], reservation["quantity"])

        return {
            "reservation_id": reservation_id,
            "status": "CANCELLED",
            "sku": reservation["sku"],
            "quantity": reservation["quantity"]
        }

    def get_orders_paginated(self, page: int = 1, size: int = 10) -> dict:
        orders, total = self.repository.get_orders_paginated(page, size)
        return {
            "total": total,
            "page": page,
            "size": size,
            "orders": orders
        }
