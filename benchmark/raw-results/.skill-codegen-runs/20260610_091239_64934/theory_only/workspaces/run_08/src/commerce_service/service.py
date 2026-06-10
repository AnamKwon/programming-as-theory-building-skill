from datetime import datetime
from sqlalchemy.orm import Session
from commerce_service.repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class SKUNotFoundError(Exception):
    pass


class DuplicateIdempotencyKeyError(Exception):
    pass


class CommerceService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, session: Session, sku_id: str, name: str):
        self.repo.create_sku(session, sku_id, name)
        return {"sku_id": sku_id, "name": name}

    def get_sku(self, session: Session, sku_id: str):
        sku = self.repo.get_sku(session, sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")
        return {"sku_id": sku.sku_id, "name": sku.name}

    def adjust_stock(self, session: Session, sku_id: str, quantity: int):
        sku = self.repo.get_sku(session, sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        stock = self.repo.adjust_stock(session, sku_id, quantity)

        if stock.available < 0:
            raise InsufficientStockError(f"Cannot adjust stock below 0 for {sku_id}")

        return {
            "sku_id": stock.sku_id,
            "available": stock.available,
            "reserved": stock.reserved,
        }

    def get_stock(self, session: Session, sku_id: str):
        stock = self.repo.get_stock(session, sku_id)
        if not stock:
            raise SKUNotFoundError(f"Stock for {sku_id} not found")

        return {
            "sku_id": stock.sku_id,
            "available": stock.available,
            "reserved": stock.reserved,
        }

    def create_reservation(self, session: Session, sku_id: str, quantity: int, idempotency_key: str):
        existing = self.repo.get_reservation_by_idempotency_key(session, idempotency_key)
        if existing:
            if existing.status == "expired":
                raise ReservationExpiredError(f"Reservation {existing.reservation_id} has expired")
            return {
                "reservation_id": existing.reservation_id,
                "sku_id": existing.sku_id,
                "quantity": existing.quantity,
                "status": existing.status,
                "created_at": existing.created_at,
                "expires_at": existing.expires_at,
            }

        sku = self.repo.get_sku(session, sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        stock = self.repo.get_or_create_stock(session, sku_id)

        if stock.available < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for {sku_id}: requested {quantity}, available {stock.available}"
            )

        reservation = self.repo.create_reservation(session, sku_id, quantity, idempotency_key)
        self.repo.update_stock_reserved(session, sku_id, quantity)

        return {
            "reservation_id": reservation.reservation_id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "status": reservation.status,
            "created_at": reservation.created_at,
            "expires_at": reservation.expires_at,
        }

    def confirm_reservation(self, session: Session, reservation_id: str, idempotency_key: str):
        reservation = self.repo.get_reservation(session, reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.idempotency_key != idempotency_key:
            raise ValueError("Idempotency key mismatch")

        if datetime.utcnow() > reservation.expires_at:
            self.repo.update_reservation_status(session, reservation_id, "expired")
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        if reservation.status == "confirmed":
            order = self.repo.get_order(session, reservation_id)
            if not order:
                order = self.repo.create_order(session, reservation.sku_id, reservation.quantity)
            return {
                "order_id": order.order_id,
                "sku_id": order.sku_id,
                "quantity": order.quantity,
                "status": order.status,
                "created_at": order.created_at,
            }

        self.repo.update_reservation_status(session, reservation_id, "confirmed")
        order = self.repo.create_order(session, reservation.sku_id, reservation.quantity)

        return {
            "order_id": order.order_id,
            "sku_id": order.sku_id,
            "quantity": order.quantity,
            "status": order.status,
            "created_at": order.created_at,
        }

    def cancel_reservation(self, session: Session, reservation_id: str):
        reservation = self.repo.get_reservation(session, reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status in ["confirmed", "cancelled", "expired"]:
            return {
                "reservation_id": reservation.reservation_id,
                "sku_id": reservation.sku_id,
                "quantity": reservation.quantity,
                "status": reservation.status,
                "created_at": reservation.created_at,
                "expires_at": reservation.expires_at,
            }

        self.repo.update_reservation_status(session, reservation_id, "cancelled")
        self.repo.update_stock_reserved(session, reservation.sku_id, -reservation.quantity)

        return {
            "reservation_id": reservation.reservation_id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "status": "cancelled",
            "created_at": reservation.created_at,
            "expires_at": reservation.expires_at,
        }

    def get_order(self, session: Session, order_id: str):
        order = self.repo.get_order(session, order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        return {
            "order_id": order.order_id,
            "sku_id": order.sku_id,
            "quantity": order.quantity,
            "status": order.status,
            "created_at": order.created_at,
        }

    def list_orders(self, session: Session, limit: int = 10, cursor: str = None):
        orders, next_cursor = self.repo.list_orders(session, limit, cursor)
        return {
            "orders": [
                {
                    "order_id": o.order_id,
                    "sku_id": o.sku_id,
                    "quantity": o.quantity,
                    "status": o.status,
                    "created_at": o.created_at,
                }
                for o in orders
            ],
            "next_cursor": next_cursor,
        }
