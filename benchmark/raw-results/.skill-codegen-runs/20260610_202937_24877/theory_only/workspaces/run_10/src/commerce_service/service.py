from datetime import datetime, timezone
from typing import Tuple
from commerce_service.repository import Repository


RESERVATION_EXPIRATION_SECONDS = 300


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> dict:
        result = self.repo.adjust_stock(sku, amount)
        if not result:
            raise ValueError(f"SKU '{sku}' not found")
        return result

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> Tuple[dict, int]:
        # Check for existing reservation with same idempotency key
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing, 200

        # Check available stock
        sku_record = self.repo.get_sku(sku)
        if not sku_record:
            raise ValueError(f"SKU '{sku}' not found")

        if sku_record["available_stock"] < quantity:
            raise ValueError("Insufficient stock")

        # Deduct stock and create reservation
        self.repo.adjust_stock(sku, -quantity)
        reservation = self.repo.create_reservation(sku, quantity, idempotency_key)

        return reservation, 201

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation '{reservation_id}' not found")

        if reservation["status"] != "PENDING":
            raise ValueError(f"Reservation status is '{reservation['status']}', not 'PENDING'")

        # Check expiration (created more than 300 seconds ago)
        created_at = datetime.fromisoformat(reservation["created_at"])
        now = datetime.now(timezone.utc)
        age_seconds = (now - created_at).total_seconds()

        if age_seconds > RESERVATION_EXPIRATION_SECONDS:
            # Mark as expired and restore stock
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.adjust_stock(reservation["sku"], reservation["quantity"])
            raise ValueError("Reservation expired")

        # Update status to CONFIRMED
        updated_reservation = self.repo.update_reservation_status(reservation_id, "CONFIRMED")

        # Create corresponding order
        self.repo.create_order(
            reservation_id, reservation["sku"], reservation["quantity"]
        )

        return updated_reservation

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation '{reservation_id}' not found")

        if reservation["status"] != "PENDING":
            raise ValueError(f"Reservation status is '{reservation['status']}', not 'PENDING'")

        # Restore stock
        self.repo.adjust_stock(reservation["sku"], reservation["quantity"])

        # Update status to CANCELLED
        updated_reservation = self.repo.update_reservation_status(reservation_id, "CANCELLED")

        return updated_reservation

    def get_orders(self, page: int = 1, size: int = 10) -> Tuple[list, int]:
        return self.repo.get_orders(page, size)
