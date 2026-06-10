from datetime import datetime, timedelta
from .repository import Repository


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        success = self.repo.create_sku(sku, initial_stock)
        if not success:
            raise ValueError("SKU already exists")
        return {"sku": sku, "initial_stock": initial_stock}

    def adjust_stock(self, sku: str, amount: int) -> dict:
        updated_stock = self.repo.adjust_stock(sku, amount)
        if updated_stock is None:
            raise ValueError("SKU not found")
        return {"sku": sku, "available_stock": updated_stock}

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> dict:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        available_stock = self.repo.get_sku_stock(sku)
        if available_stock is None:
            raise ValueError("SKU not found")
        if available_stock < quantity:
            raise ValueError("Insufficient stock")

        self.repo.adjust_stock(sku, -quantity)
        reservation = self.repo.create_reservation(sku, quantity, idempotency_key)
        if not reservation:
            self.repo.adjust_stock(sku, quantity)
            raise ValueError("Failed to create reservation")

        return reservation

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError("Reservation not found")

        if reservation["status"] != "PENDING":
            raise ValueError("Reservation is not in PENDING state")

        created_at = datetime.fromisoformat(reservation["created_at"])
        now = datetime.utcnow()
        age_seconds = (now - created_at).total_seconds()

        if age_seconds > 300:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.adjust_stock(reservation["sku"], reservation["quantity"])
            raise ValueError("Reservation expired")

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        order_id = self.repo.create_order(
            reservation_id,
            reservation["sku"],
            reservation["quantity"]
        )
        if not order_id:
            raise ValueError("Failed to create order")

        return {
            "id": reservation_id,
            "sku": reservation["sku"],
            "quantity": reservation["quantity"],
            "status": "CONFIRMED",
            "created_at": reservation["created_at"],
            "idempotency_key": reservation["idempotency_key"],
        }

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError("Reservation not found")

        if reservation["status"] != "PENDING":
            raise ValueError("Reservation is not in PENDING state")

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        self.repo.adjust_stock(reservation["sku"], reservation["quantity"])

        return {
            "id": reservation_id,
            "sku": reservation["sku"],
            "quantity": reservation["quantity"],
            "status": "CANCELLED",
            "created_at": reservation["created_at"],
            "idempotency_key": reservation["idempotency_key"],
        }
