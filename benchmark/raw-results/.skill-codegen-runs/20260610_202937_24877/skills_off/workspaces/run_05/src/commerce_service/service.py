from datetime import datetime
from typing import Optional, Tuple
from .repository import Repository


class CommerceService:
    def __init__(self, repository: Optional[Repository] = None):
        self.repo = repository or Repository()

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> Optional[dict]:
        return self.repo.adjust_stock(sku, amount)

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> dict:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        sku_data = self.repo.get_sku(sku)
        if not sku_data or sku_data["available_stock"] < quantity:
            raise ValueError("Insufficient stock")

        return self.repo.create_reservation(sku, quantity, idempotency_key)

    def confirm_reservation(self, reservation_id: str) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError("Reservation not found")

        if reservation["status"] != "PENDING":
            raise ValueError(f"Reservation is not PENDING, status: {reservation['status']}")

        created_at = datetime.fromisoformat(reservation["created_at"])
        now = datetime.utcnow()
        elapsed = (now - created_at).total_seconds()

        if elapsed > 300:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.restore_stock(reservation["sku"], reservation["quantity"])
            raise ValueError("Reservation expired")

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        order = self.repo.create_order(
            reservation_id, reservation["sku"], reservation["quantity"]
        )

        return order

    def cancel_reservation(self, reservation_id: str) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError("Reservation not found")

        if reservation["status"] != "PENDING":
            raise ValueError(f"Reservation is not PENDING, status: {reservation['status']}")

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        self.repo.restore_stock(reservation["sku"], reservation["quantity"])

        return {"id": reservation_id, "status": "CANCELLED"}

    def get_orders(self, page: int = 1, size: int = 10) -> Tuple[list, int]:
        return self.repo.get_orders(page, size)
