"""Business logic service layer."""
from datetime import datetime
from typing import Optional
from .repository import Database


class CommerceService:
    """Business logic for commerce operations."""

    def __init__(self, db: Database):
        self.db = db

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        """Create a SKU with initial stock."""
        sku_id = self.db.create_sku(sku, initial_stock)
        return {"id": sku_id, "sku": sku, "initial_stock": initial_stock}

    def adjust_stock(self, sku: str, amount: int) -> dict:
        """Adjust stock for a SKU."""
        new_stock = self.db.adjust_stock(sku, amount)
        return {"sku": sku, "new_stock": new_stock}

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> tuple[dict, int]:
        """
        Create a reservation.
        Returns (reservation_dict, status_code)
        Status code 201 for new, 200 for idempotent, 400 for insufficient stock.
        """
        # Check idempotency key first
        existing = self.db.check_idempotency_key(idempotency_key)
        if existing:
            existing["created_at"] = datetime.fromisoformat(existing["created_at"])
            return existing, 200

        # Check stock availability
        available_stock = self.db.get_sku_stock(sku)
        if available_stock is None:
            return {"detail": "SKU not found"}, 404
        if available_stock < quantity:
            return {"detail": "Insufficient stock"}, 400

        # Deduct stock and create reservation
        self.db.adjust_stock(sku, -quantity)
        reservation_id = self.db.create_reservation(sku, quantity, idempotency_key)

        reservation = self.db.get_reservation(reservation_id)
        reservation["created_at"] = datetime.fromisoformat(reservation["created_at"])
        return reservation, 201

    def confirm_reservation(self, reservation_id: int) -> tuple[Optional[dict], int]:
        """
        Confirm a reservation.
        Returns (response_dict, status_code)
        Checks for PENDING status, expiration (300s), then creates order.
        """
        reservation = self.db.get_reservation(reservation_id)
        if not reservation:
            return {"detail": "Reservation not found"}, 404

        if reservation["status"] != "PENDING":
            return {"detail": "Reservation is not in PENDING status"}, 400

        # Check expiration (300 seconds)
        created_at = datetime.fromisoformat(reservation["created_at"])
        now = datetime.utcnow()
        elapsed = (now - created_at).total_seconds()

        if elapsed > 300:
            # Mark as expired and restore stock
            self.db.update_reservation_status(reservation_id, "EXPIRED")
            self.db.adjust_stock(reservation["sku"], reservation["quantity"])
            return {"detail": "Reservation expired"}, 400

        # Confirm and create order
        self.db.update_reservation_status(reservation_id, "CONFIRMED")
        order_id = self.db.create_order(
            reservation_id, reservation["sku"], reservation["quantity"]
        )

        return {
            "id": order_id,
            "reservation_id": reservation_id,
            "sku": reservation["sku"],
            "quantity": reservation["quantity"],
        }, 200

    def cancel_reservation(self, reservation_id: int) -> tuple[Optional[dict], int]:
        """
        Cancel a reservation.
        Restores stock to the SKU.
        """
        reservation = self.db.get_reservation(reservation_id)
        if not reservation:
            return {"detail": "Reservation not found"}, 404

        if reservation["status"] != "PENDING":
            return {"detail": "Reservation is not in PENDING status"}, 400

        # Restore stock and mark as cancelled
        self.db.adjust_stock(reservation["sku"], reservation["quantity"])
        self.db.update_reservation_status(reservation_id, "CANCELLED")

        return {"status": "CANCELLED", "reservation_id": reservation_id}, 200

    def get_orders(self, page: int = 1, size: int = 10) -> dict:
        """Get paginated list of orders."""
        orders, total = self.db.get_orders(page, size)
        converted_orders = [
            {
                "id": order["id"],
                "reservation_id": order["reservation_id"],
                "sku": order["sku"],
                "quantity": order["quantity"],
                "created_at": datetime.fromisoformat(order["created_at"]),
            }
            for order in orders
        ]
        return {
            "orders": converted_orders,
            "page": page,
            "size": size,
            "total": total,
        }
