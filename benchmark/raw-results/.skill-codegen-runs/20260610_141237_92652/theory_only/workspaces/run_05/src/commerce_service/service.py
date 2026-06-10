from datetime import datetime
from commerce_service.repository import Repository


RESERVATION_EXPIRATION_SECONDS = 300


class Service:
    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, sku: str, initial_stock: int) -> dict | None:
        success = self.repo.create_sku(sku, initial_stock)
        if success:
            return self.repo.get_sku(sku)
        return None

    def adjust_stock(self, sku: str, amount: int) -> dict | None:
        return self.repo.adjust_stock(sku, amount)

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> tuple[dict | None, str | None]:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing, "idempotent"

        sku_record = self.repo.get_sku(sku)
        if not sku_record:
            return None, "sku_not_found"

        available_stock = sku_record["available_stock"]
        if available_stock < quantity:
            return None, "insufficient_stock"

        self.repo.adjust_stock(sku, -quantity)
        reservation = self.repo.create_reservation(sku, quantity, idempotency_key)
        return reservation, "created"

    def confirm_reservation(self, reservation_id: int) -> tuple[dict | None, str | None]:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            return None, "not_found"

        if reservation["status"] != "PENDING":
            return None, "invalid_state"

        created_at = datetime.fromisoformat(reservation["created_at"])
        elapsed = (datetime.utcnow() - created_at).total_seconds()
        if elapsed > RESERVATION_EXPIRATION_SECONDS:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            sku = reservation["sku"]
            quantity = reservation["quantity"]
            self.repo.adjust_stock(sku, quantity)
            return None, "expired"

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        order = self.repo.create_order(reservation_id)
        if order:
            updated_reservation = self.repo.get_reservation(reservation_id)
            return (updated_reservation, order), "confirmed"
        return None, "order_creation_failed"

    def cancel_reservation(self, reservation_id: int) -> tuple[dict | None, str | None]:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            return None, "not_found"

        if reservation["status"] != "PENDING":
            return None, "invalid_state"

        sku = reservation["sku"]
        quantity = reservation["quantity"]
        self.repo.adjust_stock(sku, quantity)
        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        updated_reservation = self.repo.get_reservation(reservation_id)
        return updated_reservation, "cancelled"
