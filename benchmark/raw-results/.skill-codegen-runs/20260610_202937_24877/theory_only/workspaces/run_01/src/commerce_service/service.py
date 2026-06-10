from datetime import datetime, timedelta
from commerce_service.repository import SQLiteRepository


class CommerceService:
    def __init__(self, repository: SQLiteRepository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> dict:
        sku_data = self.repo.get_sku_by_name(sku)
        if not sku_data:
            raise ValueError(f"SKU {sku} not found")
        return self.repo.adjust_stock(sku_data["id"], amount)

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> dict:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return {
                "id": existing["id"],
                "sku": existing["sku"],
                "quantity": existing["quantity"],
                "status": existing["status"],
                "idempotency_key": existing["idempotency_key"],
                "created_at": existing["created_at"],
                "updated_at": existing["updated_at"],
            }

        sku_data = self.repo.get_sku_by_name(sku)
        if not sku_data:
            raise ValueError(f"SKU {sku} not found")

        if sku_data["available_stock"] < quantity:
            raise ValueError("Insufficient stock")

        self.repo.adjust_stock(sku_data["id"], -quantity)
        reservation = self.repo.create_reservation(sku_data["id"], quantity, idempotency_key)

        return {
            "id": reservation["id"],
            "sku": sku,
            "quantity": reservation["quantity"],
            "status": reservation["status"],
            "idempotency_key": reservation["idempotency_key"],
            "created_at": reservation["created_at"],
            "updated_at": reservation["updated_at"],
        }

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation["status"] != "PENDING":
            raise ValueError(f"Reservation is not in PENDING state")

        created_at = reservation["created_at"]
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elapsed = datetime.utcnow() - created_at

        if elapsed > timedelta(seconds=300):
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.adjust_stock(reservation["sku_id"], reservation["quantity"])
            raise ValueError("Reservation expired")

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        self.repo.create_order(reservation_id)

        updated = self.repo.get_reservation_by_id(reservation_id)
        return {
            "id": updated["id"],
            "sku": updated["sku"],
            "quantity": updated["quantity"],
            "status": updated["status"],
            "idempotency_key": updated["idempotency_key"],
            "created_at": updated["created_at"],
            "updated_at": updated["updated_at"],
        }

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation["status"] != "PENDING":
            raise ValueError(f"Reservation is not in PENDING state")

        self.repo.adjust_stock(reservation["sku_id"], reservation["quantity"])
        self.repo.update_reservation_status(reservation_id, "CANCELLED")

        updated = self.repo.get_reservation_by_id(reservation_id)
        return {
            "id": updated["id"],
            "sku": updated["sku"],
            "quantity": updated["quantity"],
            "status": updated["status"],
            "idempotency_key": updated["idempotency_key"],
            "created_at": updated["created_at"],
            "updated_at": updated["updated_at"],
        }

    def get_orders(self, page: int = 1, size: int = 10) -> dict:
        orders, total = self.repo.get_orders(page, size)
        return {
            "items": orders,
            "page": page,
            "size": size,
            "total": total,
        }
