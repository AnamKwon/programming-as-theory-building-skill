from datetime import datetime, timezone
from typing import List, Dict, Any
from .repository import Repository


class Service:
    def __init__(self, repository: Repository):
        self.repository = repository

    def create_sku(self, sku: str, initial_stock: int) -> Dict[str, Any]:
        return self.repository.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> Dict[str, Any]:
        sku_record = self.repository.get_sku_by_name(sku)
        if not sku_record:
            raise ValueError(f"SKU {sku} not found")

        new_stock = sku_record["available_stock"] + amount
        return self.repository.update_sku_stock(sku, new_stock)

    def create_reservation(
        self,
        sku: str,
        quantity: int,
        idempotency_key: str
    ) -> Dict[str, Any]:
        existing = self.repository.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        sku_record = self.repository.get_sku_by_name(sku)
        if not sku_record:
            raise ValueError(f"SKU {sku} not found")

        if sku_record["available_stock"] < quantity:
            raise ValueError("Insufficient stock")

        new_stock = sku_record["available_stock"] - quantity
        self.repository.update_sku_stock(sku, new_stock)

        created_at = datetime.now(timezone.utc).isoformat()
        return self.repository.create_reservation(
            sku, quantity, idempotency_key, "PENDING", created_at
        )

    def confirm_reservation(self, reservation_id: int) -> Dict[str, Any]:
        reservation = self.repository.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation["status"] != "PENDING":
            raise ValueError(f"Reservation is not in PENDING status")

        created_at_str = reservation["created_at"]
        created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        elapsed_seconds = (now - created_at).total_seconds()

        if elapsed_seconds > 300:
            self.repository.update_reservation_status(reservation_id, "EXPIRED")
            sku_record = self.repository.get_sku_by_name(reservation["sku"])
            new_stock = sku_record["available_stock"] + reservation["quantity"]
            self.repository.update_sku_stock(reservation["sku"], new_stock)
            raise ValueError("Reservation expired")

        self.repository.update_reservation_status(reservation_id, "CONFIRMED")
        now_str = datetime.now(timezone.utc).isoformat()
        self.repository.create_order(reservation_id, now_str)

        return self.repository.get_reservation(reservation_id)

    def cancel_reservation(self, reservation_id: int) -> Dict[str, Any]:
        reservation = self.repository.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation["status"] != "PENDING":
            raise ValueError(f"Reservation is not in PENDING status")

        self.repository.update_reservation_status(reservation_id, "CANCELLED")

        sku_record = self.repository.get_sku_by_name(reservation["sku"])
        new_stock = sku_record["available_stock"] + reservation["quantity"]
        self.repository.update_sku_stock(reservation["sku"], new_stock)

        return self.repository.get_reservation(reservation_id)

    def get_orders(self, page: int, size: int) -> List[Dict[str, Any]]:
        offset = (page - 1) * size
        return self.repository.get_orders(offset, size)
