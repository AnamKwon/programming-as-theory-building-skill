from datetime import datetime
from typing import Optional, Dict, Tuple, List
from .repository import Repository


class CommerceService:

    @staticmethod
    def create_sku(sku: str, initial_stock: int) -> int:
        return Repository.create_sku(sku, initial_stock)

    @staticmethod
    def adjust_stock(sku: str, amount: int) -> int:
        return Repository.adjust_stock(sku, amount)

    @staticmethod
    def create_reservation(
        sku: str,
        quantity: int,
        idempotency_key: str
    ) -> Dict:
        existing_reservation = Repository.get_reservation_by_idempotency_key(
            idempotency_key
        )
        if existing_reservation:
            return existing_reservation

        available_stock = Repository.get_sku_stock(sku)
        if available_stock is None or available_stock < quantity:
            raise ValueError("Insufficient stock")

        now = datetime.utcnow()
        reservation_id = Repository.create_reservation(
            sku, quantity, idempotency_key, now
        )

        Repository.adjust_stock(sku, -quantity)

        return {
            "id": reservation_id,
            "sku": sku,
            "quantity": quantity,
            "status": "PENDING",
            "created_at": now,
            "idempotency_key": idempotency_key
        }

    @staticmethod
    def confirm_reservation(reservation_id: int) -> Dict:
        reservation = Repository.get_reservation(reservation_id)
        if not reservation:
            raise ValueError("Reservation not found")

        if reservation["status"] != "PENDING":
            raise ValueError(f"Cannot confirm reservation with status {reservation['status']}")

        created_at_str = reservation["created_at"]
        if isinstance(created_at_str, str):
            created_at = datetime.fromisoformat(created_at_str)
        else:
            created_at = created_at_str

        now = datetime.utcnow()
        elapsed_seconds = (now - created_at).total_seconds()

        if elapsed_seconds > 300:
            Repository.update_reservation_status(reservation_id, "EXPIRED")
            Repository.adjust_stock(reservation["sku"], reservation["quantity"])
            raise ValueError("Reservation expired")

        Repository.update_reservation_status(reservation_id, "CONFIRMED")
        now = datetime.utcnow()
        order_id = Repository.create_order(reservation_id, now)

        return {
            "id": reservation_id,
            "status": "CONFIRMED"
        }

    @staticmethod
    def cancel_reservation(reservation_id: int) -> Dict:
        reservation = Repository.get_reservation(reservation_id)
        if not reservation:
            raise ValueError("Reservation not found")

        if reservation["status"] != "PENDING":
            raise ValueError(f"Cannot cancel reservation with status {reservation['status']}")

        Repository.update_reservation_status(reservation_id, "CANCELLED")
        Repository.adjust_stock(reservation["sku"], reservation["quantity"])

        return {
            "id": reservation_id,
            "status": "CANCELLED"
        }

    @staticmethod
    def get_orders(page: int = 1, size: int = 10) -> Tuple[List[Dict], int]:
        orders, total = Repository.get_orders(page, size)
        return orders, total
