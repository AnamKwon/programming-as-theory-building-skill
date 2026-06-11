from datetime import datetime
from .repository import Repository


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> dict:
        return self.repo.adjust_stock(sku, amount)

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> dict:
        # Check for existing reservation with same idempotency key
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        # Create new reservation
        return self.repo.create_reservation(sku, quantity, idempotency_key)

    def confirm_reservation(self, reservation_id: int) -> dict:
        # Get reservation
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ValueError("Reservation not found")

        # Check status
        if reservation["status"] != "PENDING":
            raise ValueError(f"Reservation is not PENDING")

        # Check expiration (300 seconds = 5 minutes)
        created_at = reservation["created_at"]
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        now = datetime.utcnow()
        elapsed = (now - created_at).total_seconds()

        if elapsed > 300:
            # Mark as expired and restore stock
            self.repo.mark_reservation_expired(reservation_id)
            raise ValueError("Reservation expired")

        # Confirm reservation and create order
        return self.repo.confirm_reservation(reservation_id)

    def cancel_reservation(self, reservation_id: int) -> dict:
        return self.repo.cancel_reservation(reservation_id)

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[dict], int]:
        return self.repo.get_orders(page, size)
