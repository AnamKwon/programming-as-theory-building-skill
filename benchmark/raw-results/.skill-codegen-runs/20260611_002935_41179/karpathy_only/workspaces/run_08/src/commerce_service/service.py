from datetime import datetime
from typing import Optional

from .repository import Repository


class CommerceService:
    RESERVATION_EXPIRY_SECONDS = 300

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> bool:
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> Optional[int]:
        return self.repo.adjust_stock(sku, amount)

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> tuple[Optional[dict], Optional[str]]:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing, None

        available_stock = self.repo.get_sku_stock(sku)
        if available_stock is None:
            return None, "SKU not found"
        if available_stock < quantity:
            return None, "Insufficient stock"

        reservation = self.repo.create_reservation(sku, quantity, idempotency_key)
        if reservation is None:
            return None, "Failed to create reservation"

        self.repo.adjust_stock(sku, -quantity)
        return reservation, None

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        return self.repo.get_reservation(reservation_id)

    def confirm_reservation(self, reservation_id: int) -> tuple[Optional[dict], Optional[str]]:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            return None, "Reservation not found"

        if reservation["status"] != "PENDING":
            return None, f"Reservation is not pending"

        created_at = datetime.fromisoformat(reservation["created_at"])
        now = datetime.utcnow()
        elapsed = (now - created_at).total_seconds()

        if elapsed > self.RESERVATION_EXPIRY_SECONDS:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.adjust_stock(reservation["sku"], reservation["quantity"])
            return None, "Reservation expired"

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        order = self.repo.create_order(reservation_id)

        if order is None:
            return None, "Failed to create order"

        return order, None

    def cancel_reservation(self, reservation_id: int) -> tuple[Optional[dict], Optional[str]]:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            return None, "Reservation not found"

        if reservation["status"] != "PENDING":
            return None, "Reservation is not pending"

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        self.repo.adjust_stock(reservation["sku"], reservation["quantity"])

        updated_reservation = self.repo.get_reservation(reservation_id)
        return updated_reservation, None

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[dict], int]:
        return self.repo.get_orders(page, size)
