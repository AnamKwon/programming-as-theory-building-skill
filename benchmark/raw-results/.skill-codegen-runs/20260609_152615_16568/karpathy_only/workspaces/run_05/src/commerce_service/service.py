import uuid
from datetime import datetime, timedelta

from .models import OrderStatus
from .repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class SKUNotFoundError(Exception):
    pass


class DuplicateReservationError(Exception):
    pass


class Service:
    def __init__(self, repo: Repository):
        self.repo = repo

    # === SKU Management ===

    def create_sku(self, sku_id: str, initial_stock: int):
        sku = self.repo.create_sku(sku_id, initial_stock)
        return {
            "sku_id": sku.id,
            "available_stock": sku.available_stock,
        }

    def adjust_stock(self, sku_id: str, delta: int):
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        sku = self.repo.update_stock(sku_id, delta)
        return {
            "sku_id": sku.id,
            "available_stock": sku.available_stock,
        }

    # === Reservation Management ===

    def create_reservation(
        self, sku_id: str, quantity: int, idempotency_key: str, ttl_seconds: int
    ):
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing.status == OrderStatus.PENDING_RESERVATION:
                raise DuplicateReservationError(
                    f"Reservation with idempotency key {idempotency_key} already exists"
                )
            return {
                "reservation_id": existing.id,
                "sku_id": existing.sku_id,
                "quantity": existing.quantity,
                "status": existing.status.value,
                "expires_at": existing.expires_at,
            }

        available = sku.available_stock - self.repo.sum_reserved_quantity(sku_id)
        if available < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for SKU {sku_id}: available={available}, requested={quantity}"
            )

        reservation_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)

        reservation = self.repo.create_reservation(
            reservation_id, sku_id, quantity, idempotency_key, expires_at
        )
        self.repo.update_reservation_status(reservation_id, OrderStatus.RESERVED)

        return {
            "reservation_id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "status": OrderStatus.RESERVED.value,
            "expires_at": reservation.expires_at,
        }

    def confirm_reservation(self, reservation_id: str):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status == OrderStatus.CONFIRMED:
            order = self.repo.get_order(reservation_id)
            if order:
                return {
                    "order_id": order.id,
                    "sku_id": order.sku_id,
                    "quantity": order.quantity,
                    "status": order.status.value,
                    "created_at": order.created_at,
                }

        if reservation.status != OrderStatus.RESERVED:
            raise ValueError(f"Reservation {reservation_id} is not in RESERVED state")

        if reservation.expires_at < datetime.utcnow():
            self.repo.update_reservation_status(reservation_id, OrderStatus.CANCELLED)
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        self.repo.update_reservation_status(reservation_id, OrderStatus.CONFIRMED)

        order_id = str(uuid.uuid4())
        order = self.repo.create_order(order_id, reservation.sku_id, reservation.quantity, reservation_id)

        return {
            "order_id": order.id,
            "sku_id": order.sku_id,
            "quantity": order.quantity,
            "status": order.status.value,
            "created_at": order.created_at,
        }

    def cancel_reservation(self, reservation_id: str):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status == OrderStatus.RESERVED:
            self.repo.update_reservation_status(reservation_id, OrderStatus.CANCELLED)
        self.repo.delete_reservation(reservation_id)

    # === Order Lookup ===

    def list_orders(self, limit: int, offset: int):
        orders, total = self.repo.list_orders(limit, offset)
        return {
            "items": [
                {
                    "order_id": o.id,
                    "sku_id": o.sku_id,
                    "quantity": o.quantity,
                    "status": o.status.value,
                    "created_at": o.created_at,
                }
                for o in orders
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
