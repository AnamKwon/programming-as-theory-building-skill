"""Business logic service layer."""

from datetime import datetime, timedelta
from fastapi import HTTPException

from .repository import Repository


class CommerceService:
    EXPIRATION_SECONDS = 300

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> dict:
        try:
            return self.repo.adjust_stock(sku, amount)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> dict:
        # Check stock availability
        stock = self.repo.get_sku_stock(sku)
        if stock is None:
            raise HTTPException(status_code=400, detail=f"SKU {sku} not found")
        if stock < quantity:
            raise HTTPException(status_code=400, detail="Insufficient stock")

        # Create reservation (or return existing if idempotent)
        reservation = self.repo.create_reservation(sku, quantity, idempotency_key)

        # If this is a new reservation, deduct stock
        existing = self.repo.get_reservation(reservation["id"])
        current_created_at = existing["created_at"]
        age = (datetime.utcnow() - current_created_at).total_seconds()

        # Check if we just created it (age will be ~0)
        if age < 1:  # Freshly created
            self.repo.adjust_stock(sku, -quantity)

        return reservation

    def confirm_reservation(self, reservation_id: int) -> dict:
        # Get the reservation
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(status_code=400, detail="Reservation not found")

        # Check status
        if reservation["status"] != "PENDING":
            raise HTTPException(status_code=400, detail=f"Reservation is not PENDING")

        # Check expiration
        age = (datetime.utcnow() - reservation["created_at"]).total_seconds()
        if age > self.EXPIRATION_SECONDS:
            # Mark as expired and restore stock
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.adjust_stock(reservation["sku"], reservation["quantity"])
            raise HTTPException(status_code=400, detail="Reservation expired")

        # Update status to CONFIRMED
        self.repo.update_reservation_status(reservation_id, "CONFIRMED")

        # Create order
        order = self.repo.create_order(reservation_id)
        return order

    def cancel_reservation(self, reservation_id: int) -> dict:
        # Get the reservation
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(status_code=400, detail="Reservation not found")

        # Check status
        if reservation["status"] != "PENDING":
            raise HTTPException(status_code=400, detail=f"Reservation is not PENDING")

        # Update status to CANCELLED
        self.repo.update_reservation_status(reservation_id, "CANCELLED")

        # Restore stock
        self.repo.adjust_stock(reservation["sku"], reservation["quantity"])

        return reservation

    def get_orders(self, page: int = 1, size: int = 10) -> dict:
        orders, total = self.repo.get_orders(page, size)
        return {
            "orders": orders,
            "page": page,
            "size": size,
            "total": total,
        }
