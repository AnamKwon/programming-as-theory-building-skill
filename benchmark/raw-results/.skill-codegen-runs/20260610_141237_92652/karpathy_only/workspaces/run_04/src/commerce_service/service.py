import time
from typing import Optional, Tuple, List, Dict
from .repository import Repository


RESERVATION_EXPIRY_SECONDS = 300


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> int:
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> Optional[int]:
        return self.repo.adjust_stock(sku, amount)

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> Tuple[Dict, int]:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing, 201

        if not self.repo.sku_exists(sku):
            return {"detail": "SKU not found"}, 400

        current_stock = self.repo.get_sku_stock(sku)
        if current_stock is None or current_stock < quantity:
            return {"detail": "Insufficient stock"}, 400

        current_time = time.time()
        reservation_id = self.repo.create_reservation(sku, quantity, idempotency_key, current_time)
        self.repo.adjust_stock(sku, -quantity)

        return {
            "id": reservation_id,
            "sku": sku,
            "quantity": quantity,
            "status": "PENDING",
            "created_at": current_time,
            "idempotency_key": idempotency_key
        }, 201

    def confirm_reservation(self, reservation_id: int) -> Tuple[Dict, int]:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            return {"detail": "Reservation not found"}, 400

        if reservation["status"] != "PENDING":
            return {"detail": f"Reservation is {reservation['status']}, must be PENDING"}, 400

        current_time = time.time()
        age_seconds = current_time - reservation["created_at"]
        if age_seconds > RESERVATION_EXPIRY_SECONDS:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.adjust_stock(reservation["sku"], reservation["quantity"])
            return {"detail": "Reservation expired"}, 400

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        order_id = self.repo.create_order(
            reservation_id,
            reservation["sku"],
            reservation["quantity"],
            current_time
        )

        return {
            "id": reservation_id,
            "sku": reservation["sku"],
            "quantity": reservation["quantity"],
            "status": "CONFIRMED",
            "order_id": order_id
        }, 200

    def cancel_reservation(self, reservation_id: int) -> Tuple[Dict, int]:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            return {"detail": "Reservation not found"}, 400

        if reservation["status"] != "PENDING":
            return {"detail": f"Reservation is {reservation['status']}, must be PENDING"}, 400

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        self.repo.adjust_stock(reservation["sku"], reservation["quantity"])

        return {
            "id": reservation_id,
            "status": "CANCELLED",
            "stock_restored": reservation["quantity"]
        }, 200

    def get_orders(self, page: int = 1, size: int = 10) -> Dict:
        orders, total = self.repo.get_orders(page, size)
        return {
            "orders": orders,
            "page": page,
            "size": size,
            "total": total
        }
