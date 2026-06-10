import uuid
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from commerce_service.models import OrderStatus, ReservationStatus
from commerce_service.repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class SKUNotFoundError(Exception):
    pass


class OrderNotFoundError(Exception):
    pass


class IdempotencyError(Exception):
    pass


class Service:
    RESERVATION_TTL_MINUTES = 15

    def __init__(self, session: Session):
        self.repo = Repository(session)

    def create_sku(self, sku_id: str, name: str, initial_stock: int):
        return self.repo.create_sku(sku_id, name, initial_stock)

    def adjust_stock(self, sku_id: str, adjustment: int):
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")
        if sku.stock_quantity + adjustment < 0:
            raise ValueError("Insufficient stock")
        return self.repo.update_stock(sku_id, adjustment)

    def create_reservation(self, sku_id: str, quantity: int, idempotency_key: str):
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing.sku_id != sku_id or existing.quantity != quantity:
                raise IdempotencyError(
                    f"Idempotency key {idempotency_key} used with different parameters"
                )
            return existing

        reserved_qty = self.repo.get_reserved_quantity(sku_id)
        available = sku.stock_quantity - reserved_qty

        if available < quantity:
            raise InsufficientStockError(
                f"Insufficient stock: {available} available, {quantity} requested"
            )

        reservation_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=self.RESERVATION_TTL_MINUTES)

        try:
            return self.repo.create_reservation(
                reservation_id, sku_id, quantity, idempotency_key, expires_at
            )
        except IntegrityError:
            raise IdempotencyError(f"Idempotency key {idempotency_key} already exists")

    def confirm_reservation(self, reservation_id: str):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status != ReservationStatus.PENDING:
            raise ValueError(f"Reservation is {reservation.status}, cannot confirm")

        if datetime.utcnow() > reservation.expires_at:
            self.repo.update_reservation_status(
                reservation_id, ReservationStatus.CANCELLED
            )
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)

        order_id = str(uuid.uuid4())
        order = self.repo.create_order(order_id, reservation_id, OrderStatus.CONFIRMED)

        return order

    def cancel_reservation(self, reservation_id: str):
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status != ReservationStatus.PENDING:
            raise ValueError(f"Reservation is {reservation.status}, cannot cancel")

        return self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CANCELLED
        )

    def get_order(self, order_id: str):
        order = self.repo.get_order(order_id)
        if not order:
            raise OrderNotFoundError(f"Order {order_id} not found")
        return order

    def list_orders(self, limit: int = 10, offset: int = 0):
        return self.repo.list_orders(limit=limit, offset=offset)
