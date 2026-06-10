"""Business logic layer."""

from datetime import datetime, timezone
from .repository import Repository


class CommerceService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> dict:
        return self.repo.adjust_stock(sku, amount)

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> tuple[dict, int]:
        # Check for existing idempotent request
        existing = self.repo.check_idempotency_key(idempotency_key)
        if existing:
            return {
                "id": existing["id"],
                "sku": existing["sku"],
                "quantity": existing["quantity"],
                "status": existing["status"],
                "created_at": existing["created_at"]
            }, 201

        # Check available stock
        available_stock = self.repo.get_available_stock(sku)
        if available_stock < quantity:
            return {"detail": "Insufficient stock"}, 400

        # Deduct stock and create reservation
        created_at = datetime.now(timezone.utc).isoformat()
        reservation = self.repo.create_reservation(sku, quantity, idempotency_key, created_at)
        self.repo.deduct_stock(sku, quantity)

        return reservation, 201

    def confirm_reservation(self, reservation_id: int) -> tuple[dict, int]:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            return {"detail": "Reservation not found"}, 404

        if reservation["status"] != "PENDING":
            return {"detail": "Reservation is not in PENDING status"}, 400

        # Check if reservation is expired (more than 300 seconds old)
        created_at = datetime.fromisoformat(reservation["created_at"])
        now = datetime.now(timezone.utc)
        if (now - created_at).total_seconds() > 300:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.restore_stock(reservation["sku"], reservation["quantity"])
            return {"detail": "Reservation expired"}, 400

        # Confirm reservation and create order
        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        order_created_at = datetime.now(timezone.utc).isoformat()
        self.repo.create_order(reservation_id, order_created_at)

        return {
            "id": reservation["id"],
            "sku": reservation["sku"],
            "quantity": reservation["quantity"],
            "status": "CONFIRMED",
            "created_at": reservation["created_at"]
        }, 200

    def cancel_reservation(self, reservation_id: int) -> tuple[dict, int]:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            return {"detail": "Reservation not found"}, 404

        if reservation["status"] != "PENDING":
            return {"detail": "Reservation is not in PENDING status"}, 400

        # Cancel reservation and restore stock
        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        self.repo.restore_stock(reservation["sku"], reservation["quantity"])

        return {
            "id": reservation["id"],
            "sku": reservation["sku"],
            "quantity": reservation["quantity"],
            "status": "CANCELLED",
            "created_at": reservation["created_at"]
        }, 200

    def get_orders(self, page: int = 1, size: int = 10) -> dict:
        orders, total = self.repo.get_orders(page, size)
        return {
            "page": page,
            "size": size,
            "total": total,
            "orders": orders
        }
