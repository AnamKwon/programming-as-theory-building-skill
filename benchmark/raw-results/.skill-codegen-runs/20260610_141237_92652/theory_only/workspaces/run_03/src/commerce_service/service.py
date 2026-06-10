from datetime import datetime, timezone
from typing import Optional, Tuple, List
from commerce_service.repository import Repository


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> bool:
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> Optional[int]:
        return self.repo.adjust_stock(sku, amount)

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> Tuple[Optional[dict], str]:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing, "idempotent"

        sku_record = self.repo.get_sku(sku)
        if not sku_record:
            return None, "sku_not_found"

        available = sku_record.get('available_stock', 0)
        if available < quantity:
            return None, "insufficient_stock"

        reservation = self.repo.create_reservation(sku, quantity, idempotency_key)
        if not reservation:
            return None, "creation_failed"

        self.repo.deduct_stock(sku, quantity)

        return reservation, "created"

    def confirm_reservation(self, reservation_id: int) -> Tuple[Optional[dict], str]:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            return None, "not_found"

        if reservation['status'] != "PENDING":
            return None, "invalid_state"

        created_at_str = reservation['created_at']
        created_at = datetime.fromisoformat(created_at_str)
        now_utc = datetime.now(timezone.utc)

        age_seconds = (now_utc - created_at).total_seconds()
        if age_seconds > 300:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.restore_stock(reservation['sku'], reservation['quantity'])
            return None, "expired"

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")

        order = self.repo.create_order(reservation_id)
        if not order:
            return None, "order_creation_failed"

        return order, "confirmed"

    def cancel_reservation(self, reservation_id: int) -> Tuple[Optional[dict], str]:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            return None, "not_found"

        if reservation['status'] != "PENDING":
            return None, "invalid_state"

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        self.repo.restore_stock(reservation['sku'], reservation['quantity'])

        return reservation, "cancelled"

    def get_orders(self, page: int = 1, size: int = 10) -> Tuple[List[dict], int]:
        return self.repo.get_orders(page, size)
