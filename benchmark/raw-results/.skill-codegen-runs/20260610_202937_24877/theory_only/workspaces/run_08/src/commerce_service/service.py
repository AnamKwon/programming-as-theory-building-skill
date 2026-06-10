from datetime import datetime, timedelta
from .repository import Repository


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> dict:
        return self.repo.adjust_stock(sku, amount)

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> dict:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        stock = self.repo.get_sku_stock(sku)
        if stock < quantity:
            raise ValueError("Insufficient stock")

        return self.repo.create_reservation(sku, quantity, idempotency_key)

    def confirm_reservation(self, reservation_id: str) -> dict:
        res = self.repo.get_reservation(reservation_id)

        if not res:
            raise ValueError("Reservation not found")

        if res["status"] != "PENDING":
            raise ValueError("Reservation is not PENDING")

        created_at = datetime.fromisoformat(res["created_at"])
        if datetime.utcnow() - created_at > timedelta(seconds=300):
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.adjust_stock(res["sku"], res["quantity"])
            raise ValueError("Reservation expired")

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        order = self.repo.create_order(reservation_id)

        return order

    def cancel_reservation(self, reservation_id: str) -> dict:
        res = self.repo.get_reservation(reservation_id)

        if not res:
            raise ValueError("Reservation not found")

        if res["status"] != "PENDING":
            raise ValueError("Reservation is not PENDING")

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        self.repo.adjust_stock(res["sku"], res["quantity"])

        return {"status": "CANCELLED"}

    def get_orders(self, page: int = 1, size: int = 10) -> dict:
        return self.repo.get_orders(page, size)
