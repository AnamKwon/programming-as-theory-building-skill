from datetime import datetime
from typing import Optional, Tuple, List
from .repository import Repository


class Service:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> Optional[dict]:
        return self.repo.adjust_stock(sku, amount)

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> dict:
        # Check for existing reservation with same idempotency key
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        # Get SKU info
        sku_info = self.repo.get_sku_by_sku(sku)
        if not sku_info:
            raise ValueError(f"SKU {sku} not found")

        # Check stock availability
        if sku_info["available_stock"] < quantity:
            raise ValueError("Insufficient stock")

        # Deduct stock
        self.repo.adjust_stock(sku, -quantity)

        # Create reservation
        return self.repo.create_reservation(sku_info["id"], sku, quantity, idempotency_key)

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ValueError("Reservation not found")

        # Check status is PENDING
        if reservation["status"] != "PENDING":
            raise ValueError(f"Reservation is not in PENDING state, current state: {reservation['status']}")

        # Check expiration (300 seconds)
        now = datetime.utcnow()
        created_at = reservation["created_at"]
        elapsed = (now - created_at).total_seconds()

        if elapsed > 300:
            # Mark as expired and restore stock
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.adjust_stock(reservation["sku"], reservation["quantity"])
            raise ValueError("Reservation expired")

        # Change status to CONFIRMED
        self.repo.update_reservation_status(reservation_id, "CONFIRMED")

        # Create order
        order = self.repo.create_order(reservation_id, reservation["sku"], reservation["quantity"])

        return order

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ValueError("Reservation not found")

        # Check status is PENDING
        if reservation["status"] != "PENDING":
            raise ValueError(f"Reservation is not in PENDING state, current state: {reservation['status']}")

        # Change status to CANCELLED
        self.repo.update_reservation_status(reservation_id, "CANCELLED")

        # Restore stock
        self.repo.adjust_stock(reservation["sku"], reservation["quantity"])

        updated = self.repo.get_reservation_by_id(reservation_id)
        return updated

    def get_orders(self, page: int, size: int) -> Tuple[List[dict], int]:
        return self.repo.get_orders(page, size)
