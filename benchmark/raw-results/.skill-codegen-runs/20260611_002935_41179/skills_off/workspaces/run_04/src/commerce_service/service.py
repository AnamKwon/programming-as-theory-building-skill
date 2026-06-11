from datetime import datetime
from typing import Optional
from commerce_service.repository import Repository


RESERVATION_EXPIRY_SECONDS = 300


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> dict:
        sku_data = self.repo.get_sku_by_name(sku)
        if not sku_data:
            raise ValueError(f"SKU {sku} not found")

        return self.repo.adjust_stock(sku, amount)

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> dict:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return {
                "id": existing["id"],
                "sku": existing["sku"],
                "quantity": existing["quantity"],
                "status": existing["status"],
                "created_at": existing["created_at"],
                "idempotency_key": existing["idempotency_key"],
            }

        sku_data = self.repo.get_sku_by_name(sku)
        if not sku_data:
            raise ValueError(f"SKU {sku} not found")

        if sku_data["available_stock"] < quantity:
            raise ValueError("Insufficient stock")

        self.repo.deduct_stock(sku, quantity)

        reservation = self.repo.create_reservation(sku, quantity, idempotency_key)
        return reservation

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation["status"] != "PENDING":
            raise ValueError(
                f"Reservation is not in PENDING status, current status: {reservation['status']}"
            )

        created_at = datetime.fromisoformat(reservation["created_at"])
        now = datetime.utcnow()
        elapsed = (now - created_at).total_seconds()

        if elapsed > RESERVATION_EXPIRY_SECONDS:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.restore_stock(reservation["sku"], reservation["quantity"])
            raise ValueError("Reservation expired")

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        order = self.repo.create_order(reservation_id)
        return {"reservation_id": reservation_id, "order": order}

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation["status"] != "PENDING":
            raise ValueError(
                f"Reservation is not in PENDING status, current status: {reservation['status']}"
            )

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        self.repo.restore_stock(reservation["sku"], reservation["quantity"])
        return {"reservation_id": reservation_id, "status": "CANCELLED"}

    def list_orders(self, page: int, size: int) -> dict:
        orders, total = self.repo.list_orders(page, size)
        return {
            "orders": orders,
            "page": page,
            "size": size,
            "total": total,
        }
