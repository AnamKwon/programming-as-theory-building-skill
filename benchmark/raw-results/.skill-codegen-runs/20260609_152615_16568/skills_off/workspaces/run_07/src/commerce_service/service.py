from datetime import datetime, timedelta
from typing import Optional

from .models import ReservationStatus, OrderStatus
from .repository import Database


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class OrderNotFoundError(Exception):
    pass


class CommerceService:
    def __init__(self, db: Database):
        self.db = db
        self.reservation_ttl_minutes = 15

    def create_sku(self, sku: str, name: str) -> dict:
        return self.db.create_sku(sku, name)

    def adjust_stock(self, sku: str, quantity: int) -> dict:
        sku_record = self.db.get_sku_by_code(sku)
        if not sku_record:
            raise ValueError(f"SKU not found: {sku}")
        return self.db.adjust_stock(sku_record["id"], quantity)

    def create_reservation(
        self,
        sku: str,
        quantity: int,
        customer_id: str,
        idempotency_key: str,
    ) -> dict:
        existing = self.db.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing["status"] == ReservationStatus.EXPIRED:
                raise ReservationExpiredError("Reservation has expired")
            return {
                "id": existing["id"],
                "sku": existing["sku"],
                "quantity": existing["quantity"],
                "status": existing["status"],
                "customer_id": existing["customer_id"],
                "created_at": existing["created_at"],
                "expires_at": existing["expires_at"],
                "order_id": existing["order_id"],
                "idempotent": True,
            }

        sku_record = self.db.get_sku_by_code(sku)
        if not sku_record:
            raise ValueError(f"SKU not found: {sku}")

        sku_id = sku_record["id"]
        available = self.db.get_available_stock(sku_id)
        reserved = self.db.get_reserved_quantity(sku_id)
        unreserved = available - reserved

        if unreserved < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for {sku}: available={unreserved}, requested={quantity}"
            )

        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=self.reservation_ttl_minutes)

        result = self.db.create_reservation(
            sku_id=sku_id,
            quantity=quantity,
            customer_id=customer_id,
            idempotency_key=idempotency_key,
            expires_at=expires_at.isoformat(),
        )

        return {
            "id": result["id"],
            "sku": sku,
            "quantity": quantity,
            "status": ReservationStatus.PENDING,
            "customer_id": customer_id,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "order_id": None,
            "idempotent": False,
        }

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.db.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation not found: {reservation_id}")

        if reservation["status"] == ReservationStatus.EXPIRED:
            raise ReservationExpiredError("Cannot confirm expired reservation")

        if reservation["status"] == ReservationStatus.CANCELLED:
            raise ValueError("Cannot confirm cancelled reservation")

        now = datetime.utcnow()
        expires_at = datetime.fromisoformat(reservation["expires_at"])
        if expires_at <= now:
            self.db.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
            raise ReservationExpiredError("Reservation has expired")

        if reservation["status"] == ReservationStatus.CONFIRMED:
            return reservation

        order_result = self.db.create_order(reservation["customer_id"])
        order_id = order_result["id"]

        self.db.link_reservation_to_order(reservation_id, order_id)
        self.db.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)
        self.db.confirm_order(order_id)

        return {
            "id": reservation_id,
            "sku": reservation["sku"],
            "quantity": reservation["quantity"],
            "status": ReservationStatus.CONFIRMED,
            "customer_id": reservation["customer_id"],
            "created_at": reservation["created_at"],
            "expires_at": reservation["expires_at"],
            "order_id": order_id,
        }

    def cancel_reservation(self, reservation_id: int) -> None:
        reservation = self.db.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation not found: {reservation_id}")

        if reservation["status"] == ReservationStatus.CANCELLED:
            return

        self.db.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)

    def get_order(self, order_id: int) -> dict:
        order = self.db.get_order(order_id)
        if not order:
            raise OrderNotFoundError(f"Order not found: {order_id}")

        items = self.db.get_order_items(order_id)
        return {
            "id": order["id"],
            "status": order["status"],
            "customer_id": order["customer_id"],
            "created_at": order["created_at"],
            "updated_at": order["updated_at"],
            "items": items,
        }

    def list_orders(self, customer_id: str, page: int = 1, page_size: int = 10) -> dict:
        result = self.db.list_orders(customer_id, page, page_size)
        orders_with_items = []
        for order in result["orders"]:
            items = self.db.get_order_items(order["id"])
            orders_with_items.append({
                "id": order["id"],
                "status": order["status"],
                "customer_id": order["customer_id"],
                "created_at": order["created_at"],
                "updated_at": order["updated_at"],
                "items": items,
            })
        return {
            "orders": orders_with_items,
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        }

    def cleanup_expired_reservations(self) -> int:
        now = datetime.utcnow().isoformat()
        expired_ids = self.db.get_expired_reservations(now)
        for reservation_id in expired_ids:
            self.db.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
        return len(expired_ids)
