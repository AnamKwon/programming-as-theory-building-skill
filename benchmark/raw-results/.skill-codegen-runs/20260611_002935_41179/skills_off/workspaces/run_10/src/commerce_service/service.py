from datetime import datetime, timezone
from .repository import Repository


class ReservationNotFoundError(Exception):
    pass


class ReservationStatusError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class SKUNotFoundError(Exception):
    pass


class InsufficientStockError(Exception):
    pass


class Service:
    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, sku: str, initial_stock: int):
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int):
        sku_row = self.repo.get_sku_by_name(sku)
        if not sku_row:
            raise SKUNotFoundError(f"SKU {sku} not found")

        new_stock = self.repo.update_stock(sku_row["id"], amount)
        return {"sku": sku, "available_stock": new_stock}

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ):
        # Check idempotency first
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return {
                "id": existing["id"],
                "sku": existing["sku"],
                "quantity": existing["quantity"],
                "status": existing["status"],
                "created_at": existing["created_at"],
            }

        # Get SKU
        sku_row = self.repo.get_sku_by_name(sku)
        if not sku_row:
            raise SKUNotFoundError(f"SKU {sku} not found")

        # Check stock
        if sku_row["available_stock"] < quantity:
            raise InsufficientStockError("Insufficient stock")

        # Deduct stock and create reservation
        self.repo.update_stock(sku_row["id"], -quantity)
        res_id = self.repo.create_reservation(sku_row["id"], quantity, idempotency_key)

        # Fetch created reservation
        res = self.repo.get_reservation(res_id)
        return {
            "id": res["id"],
            "sku": res["sku"],
            "quantity": res["quantity"],
            "status": res["status"],
            "created_at": res["created_at"],
        }

    def confirm_reservation(self, res_id: int):
        res = self.repo.get_reservation(res_id)
        if not res:
            raise ReservationNotFoundError(f"Reservation {res_id} not found")

        if res["status"] != "PENDING":
            raise ReservationStatusError(
                f"Reservation is not in PENDING status, current status: {res['status']}"
            )

        # Check if expired
        created_at = datetime.fromisoformat(res["created_at"])
        now = datetime.now(timezone.utc)
        age_seconds = (now - created_at).total_seconds()

        if age_seconds > 300:
            # Mark as expired and restore stock
            self.repo.update_reservation_status(res_id, "EXPIRED")
            self.repo.update_stock(res["sku_id"], res["quantity"])
            raise ReservationExpiredError("Reservation expired")

        # Confirm and create order
        self.repo.update_reservation_status(res_id, "CONFIRMED")
        order_id = self.repo.create_order(res_id, res["sku_id"], res["quantity"])

        return {"id": order_id, "status": "confirmed"}

    def cancel_reservation(self, res_id: int):
        res = self.repo.get_reservation(res_id)
        if not res:
            raise ReservationNotFoundError(f"Reservation {res_id} not found")

        if res["status"] != "PENDING":
            raise ReservationStatusError(
                f"Reservation is not in PENDING status, current status: {res['status']}"
            )

        # Cancel and restore stock
        self.repo.update_reservation_status(res_id, "CANCELLED")
        self.repo.update_stock(res["sku_id"], res["quantity"])

        return {"status": "cancelled"}

    def get_orders(self, page: int = 1, size: int = 10):
        rows, total = self.repo.get_orders(page, size)
        orders = [
            {
                "id": row["id"],
                "sku": row["sku"],
                "quantity": row["quantity"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
        return {
            "orders": orders,
            "page": page,
            "size": size,
            "total": total,
        }
