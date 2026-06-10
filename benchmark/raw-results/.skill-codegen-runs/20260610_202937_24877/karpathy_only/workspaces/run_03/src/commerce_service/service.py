from datetime import datetime
from .repository import Repository


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> dict:
        result = self.repo.adjust_stock(sku, amount)
        if result is None:
            raise ValueError(f"SKU not found: {sku}")
        return result

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> dict:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        sku_data = self.repo.get_sku_by_name(sku)
        if sku_data is None:
            raise ValueError(f"SKU not found: {sku}")

        if sku_data["available_stock"] < quantity:
            raise ValueError("Insufficient stock")

        self.repo.adjust_stock(sku, -quantity)

        reservation = self.repo.create_reservation(sku, quantity, idempotency_key)
        return reservation

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if reservation is None:
            raise ValueError(f"Reservation not found: {reservation_id}")

        if reservation["status"] != "PENDING":
            raise ValueError(f"Reservation is not PENDING: {reservation['status']}")

        created_at = datetime.fromisoformat(reservation["created_at"])
        now = datetime.utcnow()
        age_seconds = (now - created_at).total_seconds()

        if age_seconds > 300:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.adjust_stock(reservation["sku"], reservation["quantity"])
            raise ValueError("Reservation expired")

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")

        order = self.repo.create_order(
            reservation_id, reservation["sku"], reservation["quantity"]
        )

        updated_reservation = self.repo.get_reservation_by_id(reservation_id)
        return {
            "id": updated_reservation["id"],
            "sku": updated_reservation["sku"],
            "quantity": updated_reservation["quantity"],
            "status": updated_reservation["status"],
            "created_at": updated_reservation["created_at"],
            "updated_at": updated_reservation["updated_at"],
        }

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if reservation is None:
            raise ValueError(f"Reservation not found: {reservation_id}")

        if reservation["status"] != "PENDING":
            raise ValueError(f"Reservation is not PENDING: {reservation['status']}")

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        self.repo.adjust_stock(reservation["sku"], reservation["quantity"])

        updated_reservation = self.repo.get_reservation_by_id(reservation_id)
        return {
            "id": updated_reservation["id"],
            "sku": updated_reservation["sku"],
            "quantity": updated_reservation["quantity"],
            "status": updated_reservation["status"],
            "created_at": updated_reservation["created_at"],
            "updated_at": updated_reservation["updated_at"],
        }

    def get_orders(self, page: int = 1, size: int = 10) -> dict:
        orders, total = self.repo.get_orders(page, size)
        return {
            "orders": orders,
            "page": page,
            "size": size,
            "total": total,
        }
