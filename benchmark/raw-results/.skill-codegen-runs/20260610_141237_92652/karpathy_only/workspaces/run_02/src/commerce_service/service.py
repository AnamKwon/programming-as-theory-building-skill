from datetime import datetime, timedelta
from .repository import Repository


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> dict:
        sku_data = self.repo.get_sku_by_name(sku)
        if not sku_data:
            raise ValueError(f"SKU not found: {sku}")

        new_stock = sku_data["available_stock"] + amount
        if new_stock < 0:
            raise ValueError("Stock cannot be negative")

        return self.repo.update_sku_stock(sku_data["id"], new_stock)

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> dict:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        sku_data = self.repo.get_sku_by_name(sku)
        if not sku_data:
            raise ValueError(f"SKU not found: {sku}")

        if sku_data["available_stock"] < quantity:
            raise ValueError("Insufficient stock")

        reservation = self.repo.create_reservation(sku_data["id"], quantity, idempotency_key)

        self.repo.update_sku_stock(
            sku_data["id"], sku_data["available_stock"] - quantity
        )

        return reservation

    def confirm_reservation(self, res_id: int) -> dict:
        reservation = self.repo.get_reservation_by_id(res_id)
        if not reservation:
            raise ValueError(f"Reservation not found: {res_id}")

        if reservation["status"] != "PENDING":
            raise ValueError(f"Reservation is not pending: {reservation['status']}")

        created_at = datetime.fromisoformat(reservation["created_at"])
        if datetime.utcnow() - created_at > timedelta(seconds=300):
            self.repo.update_reservation_status(res_id, "EXPIRED")

            sku_data = self.repo.get_sku_by_name(reservation["sku"])
            self.repo.update_sku_stock(
                sku_data["id"], sku_data["available_stock"] + reservation["quantity"]
            )

            raise ValueError("Reservation expired")

        self.repo.update_reservation_status(res_id, "CONFIRMED")

        order = self.repo.create_order(res_id)

        return {"reservation_id": res_id, "order_id": order["id"], "status": "CONFIRMED"}

    def cancel_reservation(self, res_id: int) -> dict:
        reservation = self.repo.get_reservation_by_id(res_id)
        if not reservation:
            raise ValueError(f"Reservation not found: {res_id}")

        if reservation["status"] != "PENDING":
            raise ValueError(f"Reservation is not pending: {reservation['status']}")

        self.repo.update_reservation_status(res_id, "CANCELLED")

        sku_data = self.repo.get_sku_by_name(reservation["sku"])
        self.repo.update_sku_stock(
            sku_data["id"], sku_data["available_stock"] + reservation["quantity"]
        )

        return {"reservation_id": res_id, "status": "CANCELLED"}

    def get_orders(self, page: int = 1, size: int = 10) -> dict:
        orders, total = self.repo.get_orders(page, size)
        return {"items": orders, "page": page, "size": size, "total": total}
