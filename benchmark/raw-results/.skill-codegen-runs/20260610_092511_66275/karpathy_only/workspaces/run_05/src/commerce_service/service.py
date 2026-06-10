from datetime import datetime

from .models import OrderStatus, ReservationStatus
from .repository import Database


class ValidationError(Exception):
    pass


class ServiceLayer:
    def __init__(self, db: Database):
        self.db = db

    def create_sku(self, sku_code: str, stock_qty: int) -> dict:
        existing = self.db.get_sku_by_code(sku_code)
        if existing:
            raise ValidationError(f"SKU {sku_code} already exists")
        return self.db.create_sku(sku_code, stock_qty)

    def adjust_stock(self, sku_id: int, adjustment: int) -> dict:
        sku = self.db.get_sku_by_id(sku_id)
        if not sku:
            raise ValidationError(f"SKU {sku_id} not found")
        new_qty = sku["stock_qty"] + adjustment
        if new_qty < 0:
            raise ValidationError("Stock adjustment would result in negative inventory")
        return self.db.adjust_stock(sku_id, adjustment)

    def create_reservation(self, sku_code: str, qty: int, idempotency_key: str) -> dict:
        existing_res = self.db.get_reservation_by_idempotency_key(idempotency_key)
        if existing_res:
            return existing_res

        sku = self.db.get_sku_by_code(sku_code)
        if not sku:
            raise ValidationError(f"SKU {sku_code} not found")

        if sku["stock_qty"] < qty:
            raise ValidationError(
                f"Insufficient stock: {sku['stock_qty']} available, {qty} requested"
            )

        return self.db.create_reservation(sku["id"], qty, idempotency_key)

    def confirm_reservation(
        self, reservation_id: int, idempotency_key: str
    ) -> tuple[dict, dict]:
        reservation = self.db.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ValidationError(f"Reservation {reservation_id} not found")

        if reservation["idempotency_key"] != idempotency_key:
            raise ValidationError("Idempotency key mismatch")

        if reservation["status"] == ReservationStatus.CONFIRMED.value:
            order = self._get_order_by_reservation(reservation_id)
            if order:
                return reservation, order

        if reservation["status"] == ReservationStatus.CANCELLED.value:
            raise ValidationError("Cannot confirm a cancelled reservation")

        expires_at = datetime.fromisoformat(reservation["expires_at"])
        if datetime.utcnow() > expires_at:
            self.db.cancel_reservation(reservation_id)
            raise ValidationError("Reservation has expired")

        confirmed_res = self.db.confirm_reservation(reservation_id)
        order = self.db.create_order(
            reservation_id, reservation["sku_id"], reservation["qty"]
        )
        return confirmed_res, order

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.db.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ValidationError(f"Reservation {reservation_id} not found")

        if reservation["status"] in (
            ReservationStatus.CONFIRMED.value,
            ReservationStatus.CANCELLED.value,
        ):
            raise ValidationError(
                f"Cannot cancel a {reservation['status']} reservation"
            )

        return self.db.cancel_reservation(reservation_id)

    def get_order(self, order_id: int) -> dict:
        order = self.db.get_order_by_id(order_id)
        if not order:
            raise ValidationError(f"Order {order_id} not found")
        return order

    def list_orders(self, limit: int = 20, offset: int = 0) -> tuple[list[dict], int]:
        limit = min(limit, 100)
        return self.db.list_orders(limit, offset)

    def _get_order_by_reservation(self, reservation_id: int) -> dict | None:
        with self.db.get_connection() as conn:
            row = conn.execute(
                """
                SELECT o.id, s.sku_code, o.qty, o.status, o.created_at
                FROM orders o
                JOIN skus s ON o.sku_id = s.id
                WHERE o.reservation_id = ?
                """,
                (reservation_id,),
            ).fetchone()
            return dict(row) if row else None
