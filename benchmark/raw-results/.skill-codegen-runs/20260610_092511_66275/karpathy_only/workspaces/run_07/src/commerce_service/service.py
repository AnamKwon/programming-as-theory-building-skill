from datetime import datetime, timedelta
from typing import Optional

from .repository import Repository


class ReservationExpired(Exception):
    pass


class InsufficientStock(Exception):
    pass


class NotFound(Exception):
    pass


class CommerceService:
    RESERVATION_TTL_MINUTES = 15

    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, sku_code: str, quantity: int) -> dict:
        return self.repo.create_sku(sku_code, quantity)

    def adjust_stock(self, sku_id: int, delta: int) -> dict:
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise NotFound(f"SKU {sku_id} not found")
        result = self.repo.adjust_stock(sku_id, delta)
        if result is None:
            raise ValueError("Insufficient stock for adjustment")
        return result

    def create_reservation(self, sku_id: int, quantity: int, idempotency_key: str) -> dict:
        existing = self.repo.get_reservation_by_key(idempotency_key)
        if existing:
            if existing["status"] == "expired":
                raise ReservationExpired("This reservation has expired")
            return existing

        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise NotFound(f"SKU {sku_id} not found")

        if sku["quantity"] < quantity:
            raise InsufficientStock(
                f"Requested {quantity}, available {sku['quantity']}"
            )

        expires_at = (datetime.utcnow() + timedelta(minutes=self.RESERVATION_TTL_MINUTES)).isoformat()
        reservation = self.repo.create_reservation(sku_id, quantity, idempotency_key, expires_at)
        return reservation

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise NotFound(f"Reservation {reservation_id} not found")

        if reservation["status"] != "pending":
            raise ValueError(f"Cannot confirm reservation in {reservation['status']} state")

        now = datetime.utcnow().isoformat()
        if reservation["expires_at"] and reservation["expires_at"] < now:
            self.repo.update_reservation_status(reservation_id, "expired")
            raise ReservationExpired("Reservation has expired")

        order = self.repo.create_order(
            reservation["sku_id"],
            reservation["quantity"],
            state="confirmed",
            reservation_id=reservation_id,
        )
        self.repo.update_reservation_status(reservation_id, "confirmed")
        self.repo.adjust_stock(reservation["sku_id"], -reservation["quantity"])
        return order

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise NotFound(f"Reservation {reservation_id} not found")

        if reservation["status"] not in ("pending", "expired"):
            raise ValueError(f"Cannot cancel reservation in {reservation['status']} state")

        updated = self.repo.update_reservation_status(reservation_id, "cancelled")
        return updated if updated else reservation

    def list_orders(self, offset: int = 0, limit: int = 10) -> dict:
        orders, total = self.repo.list_orders(offset, limit)
        return {
            "items": orders,
            "total": total,
            "offset": offset,
            "limit": limit,
        }

    def get_order(self, order_id: int) -> dict:
        order = self.repo.get_order(order_id)
        if not order:
            raise NotFound(f"Order {order_id} not found")
        return order
