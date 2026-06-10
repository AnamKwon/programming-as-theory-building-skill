from datetime import datetime
from fastapi import HTTPException

from .repository import Repository


class Service:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        self.repo.create_sku(sku, initial_stock)
        return {"sku": sku, "stock": initial_stock}

    def adjust_stock(self, sku: str, amount: int) -> dict:
        stock = self.repo.get_sku_stock(sku)
        if stock is None:
            raise HTTPException(status_code=404, detail="SKU not found")
        new_stock = self.repo.adjust_stock(sku, amount)
        return {"sku": sku, "stock": new_stock}

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> dict:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return {
                "id": existing["id"],
                "sku": existing["sku"],
                "quantity": existing["quantity"],
                "status": existing["status"],
                "idempotency_key": existing["idempotency_key"],
                "created_at": existing["created_at"],
            }

        stock = self.repo.get_sku_stock(sku)
        if stock is None:
            raise HTTPException(status_code=404, detail="SKU not found")
        if stock < quantity:
            raise HTTPException(status_code=400, detail="Insufficient stock")

        self.repo.adjust_stock(sku, -quantity)
        reservation_id = self.repo.create_reservation(sku, quantity, idempotency_key)

        reservation = self.repo.get_reservation(reservation_id)
        return {
            "id": reservation["id"],
            "sku": reservation["sku"],
            "quantity": reservation["quantity"],
            "status": reservation["status"],
            "idempotency_key": reservation["idempotency_key"],
            "created_at": reservation["created_at"],
        }

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")

        if reservation["status"] != "PENDING":
            raise HTTPException(status_code=400, detail="Reservation is not pending")

        created_at = datetime.fromisoformat(reservation["created_at"])
        now = datetime.utcnow()
        age_seconds = (now - created_at).total_seconds()

        if age_seconds > 300:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.adjust_stock(reservation["sku"], reservation["quantity"])
            raise HTTPException(status_code=400, detail="Reservation expired")

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        order_id = self.repo.create_order(
            reservation["sku"], reservation["quantity"], reservation_id
        )

        return {
            "id": reservation_id,
            "sku": reservation["sku"],
            "quantity": reservation["quantity"],
            "status": "CONFIRMED",
            "created_at": reservation["created_at"],
            "order_id": order_id,
        }

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")

        if reservation["status"] != "PENDING":
            raise HTTPException(status_code=400, detail="Reservation is not pending")

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        self.repo.adjust_stock(reservation["sku"], reservation["quantity"])

        return {
            "id": reservation_id,
            "sku": reservation["sku"],
            "quantity": reservation["quantity"],
            "status": "CANCELLED",
            "created_at": reservation["created_at"],
        }

    def get_orders(self, page: int = 1, size: int = 10) -> dict:
        orders, total = self.repo.get_orders(page, size)
        return {
            "orders": [
                {
                    "id": order["id"],
                    "sku": order["sku"],
                    "quantity": order["quantity"],
                    "created_at": order["created_at"],
                    "reservation_id": order["reservation_id"],
                }
                for order in orders
            ],
            "page": page,
            "size": size,
            "total": total,
        }
