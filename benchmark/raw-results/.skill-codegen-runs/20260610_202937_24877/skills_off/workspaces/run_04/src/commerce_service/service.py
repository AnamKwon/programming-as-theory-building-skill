from datetime import datetime, timezone, timedelta
from commerce_service.repository import Database
from commerce_service.models import ReservationStatus


class InventoryService:
    def __init__(self, db: Database):
        self.db = db

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        return self.db.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> dict:
        sku_data = self.db.get_sku_by_name(sku)
        if not sku_data:
            raise ValueError(f"SKU {sku} not found")
        return self.db.adjust_stock(sku, amount)

    def reserve_stock(self, sku: str, quantity: int, idempotency_key: str) -> tuple[dict, int]:
        existing_reservation = self.db.get_reservation_by_idempotency_key(idempotency_key)
        if existing_reservation:
            return existing_reservation, 200

        sku_data = self.db.get_sku_by_name(sku)
        if not sku_data:
            raise ValueError(f"SKU {sku} not found")

        if sku_data['available_stock'] < quantity:
            raise ValueError("Insufficient stock")

        self.db.adjust_stock(sku, -quantity)
        reservation = self.db.create_reservation(sku, quantity, idempotency_key)
        return reservation, 201

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.db.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation['status'] != ReservationStatus.PENDING.value:
            raise ValueError(f"Reservation is not in PENDING status")

        created_at = datetime.fromisoformat(reservation['created_at'])
        now = datetime.now(timezone.utc)
        if (now - created_at) > timedelta(seconds=300):
            self.db.update_reservation_status(reservation_id, ReservationStatus.EXPIRED.value)
            self.db.adjust_stock(reservation['sku'], reservation['quantity'])
            raise ValueError("Reservation expired")

        self.db.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED.value)
        order = self.db.create_order(reservation_id, reservation['sku'], reservation['quantity'])
        return order

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.db.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation['status'] != ReservationStatus.PENDING.value:
            raise ValueError(f"Reservation is not in PENDING status")

        self.db.update_reservation_status(reservation_id, ReservationStatus.CANCELLED.value)
        self.db.adjust_stock(reservation['sku'], reservation['quantity'])

        return {"id": reservation_id, "status": ReservationStatus.CANCELLED.value}

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[dict], int]:
        return self.db.get_orders(page, size)
