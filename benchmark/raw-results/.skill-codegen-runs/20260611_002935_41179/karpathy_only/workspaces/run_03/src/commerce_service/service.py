from datetime import datetime
from commerce_service.repository import Database


RESERVATION_EXPIRY_SECONDS = 300


class CommerceService:
    def __init__(self, db: Database):
        self.db = db

    def create_sku(self, sku: str, initial_stock: int):
        self.db.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> dict:
        stock = self.db.adjust_stock(sku, amount)
        if stock is None:
            raise ValueError(f"SKU not found: {sku}")
        return {"sku": sku, "stock": stock}

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> dict:
        existing = self.db.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        current_stock = self.db.get_sku_stock(sku)
        if current_stock is None:
            raise ValueError(f"SKU not found: {sku}")

        if current_stock < quantity:
            raise ValueError("Insufficient stock")

        self.db.adjust_stock(sku, -quantity)
        reservation_id, created_at = self.db.create_reservation(
            sku, quantity, idempotency_key
        )

        return {
            "id": reservation_id,
            "sku": sku,
            "quantity": quantity,
            "status": "PENDING",
            "idempotency_key": idempotency_key,
            "created_at": created_at,
        }

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.db.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation not found: {reservation_id}")

        if reservation["status"] != "PENDING":
            raise ValueError(
                f"Cannot confirm reservation with status: {reservation['status']}"
            )

        created_at = datetime.fromisoformat(reservation["created_at"])
        now = datetime.utcnow()
        age_seconds = (now - created_at).total_seconds()

        if age_seconds > RESERVATION_EXPIRY_SECONDS:
            self.db.update_reservation_status(reservation_id, "EXPIRED")
            self.db.adjust_stock(reservation["sku"], reservation["quantity"])
            raise ValueError("Reservation expired")

        self.db.update_reservation_status(reservation_id, "CONFIRMED")
        order_id = self.db.create_order(reservation_id)

        return {
            "id": order_id,
            "reservation_id": reservation_id,
            "created_at": datetime.utcnow().isoformat(),
        }

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.db.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation not found: {reservation_id}")

        if reservation["status"] != "PENDING":
            raise ValueError(
                f"Cannot cancel reservation with status: {reservation['status']}"
            )

        self.db.update_reservation_status(reservation_id, "CANCELLED")
        self.db.adjust_stock(reservation["sku"], reservation["quantity"])

        updated = self.db.get_reservation(reservation_id)
        return updated

    def get_orders(self, page: int = 1, size: int = 10) -> dict:
        orders, total = self.db.get_orders(page, size)
        return {
            "items": orders,
            "page": page,
            "size": size,
            "total": total,
        }
