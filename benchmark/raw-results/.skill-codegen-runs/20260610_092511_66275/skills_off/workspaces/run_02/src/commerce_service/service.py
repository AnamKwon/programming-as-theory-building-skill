from datetime import datetime

from .models import ReservationState, OrderState
from .repository import Database


class CommerceService:
    def __init__(self, db: Database):
        self.db = db

    def create_sku(self, sku: str, name: str) -> dict | None:
        if self.db.create_sku(sku, name):
            return self.db.get_sku(sku)
        return None

    def adjust_stock(self, sku: str, quantity: int) -> dict | None:
        if not self.db.get_sku(sku):
            return None
        return self.db.adjust_inventory(sku, quantity)

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> tuple[dict | None, str | None]:
        # Check if SKU exists
        if not self.db.get_sku(sku):
            return None, f"SKU {sku} not found"

        # Check for idempotent retry
        existing = self.db.get_reservation_by_key(idempotency_key)
        if existing:
            return existing, None

        # Check stock availability
        available = self.db.get_inventory(sku)
        if available is None or available < quantity:
            return None, f"Insufficient stock for {sku}: requested {quantity}, available {available or 0}"

        # Reserve stock
        reservation = self.db.create_reservation(sku, quantity, idempotency_key)
        if not reservation:
            return None, "Failed to create reservation"

        # Deduct from inventory
        self.db.adjust_inventory(sku, -quantity)

        return reservation, None

    def confirm_reservation(self, reservation_id: int) -> tuple[dict | None, str | None]:
        reservation = self.db.get_reservation(reservation_id)
        if not reservation:
            return None, f"Reservation {reservation_id} not found"

        # Check expiration
        expires_at = datetime.fromisoformat(reservation["expires_at"])
        if datetime.utcnow() > expires_at:
            self.db.update_reservation_state(reservation_id, ReservationState.EXPIRED)
            # Return inventory
            self.db.adjust_inventory(reservation["sku"], reservation["quantity"])
            return None, f"Reservation {reservation_id} has expired"

        # Check state
        if reservation["state"] != ReservationState.PENDING:
            return None, f"Reservation {reservation_id} is not in pending state"

        # Confirm reservation and create order
        self.db.update_reservation_state(reservation_id, ReservationState.CONFIRMED)
        order = self.db.create_order(reservation["sku"], reservation["quantity"])
        self.db.update_order_state(order["id"], OrderState.CONFIRMED)

        reservation = self.db.get_reservation(reservation_id)
        return reservation, None

    def cancel_reservation(self, reservation_id: int) -> tuple[dict | None, str | None]:
        reservation = self.db.get_reservation(reservation_id)
        if not reservation:
            return None, f"Reservation {reservation_id} not found"

        if reservation["state"] != ReservationState.PENDING:
            return None, f"Cannot cancel reservation {reservation_id} in {reservation['state']} state"

        # Cancel and return inventory
        self.db.update_reservation_state(reservation_id, ReservationState.CANCELLED)
        self.db.adjust_inventory(reservation["sku"], reservation["quantity"])

        reservation = self.db.get_reservation(reservation_id)
        return reservation, None

    def get_orders(self, skip: int = 0, limit: int = 20) -> tuple[list[dict], int]:
        return self.db.list_orders(skip, limit)

    def expire_reservations(self):
        now = datetime.utcnow()
        for reservation in self.db.list_pending_reservations():
            expires_at = datetime.fromisoformat(reservation["expires_at"])
            if now > expires_at:
                self.db.update_reservation_state(reservation["id"], ReservationState.EXPIRED)
                self.db.adjust_inventory(reservation["sku"], reservation["quantity"])
