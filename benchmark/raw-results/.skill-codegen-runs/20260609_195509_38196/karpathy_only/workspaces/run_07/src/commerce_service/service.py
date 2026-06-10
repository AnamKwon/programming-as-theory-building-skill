from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy.orm import Session

from .models import (
    OrderStatus,
    Reservation,
    ReservationStatus,
    SKU,
)
from .repository import OrderRepository, ReservationRepository, SKURepository


class InsufficientStockError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class SKUNotFoundError(Exception):
    pass


class CommerceService:
    def __init__(self, session: Session):
        self.session = session
        self.sku_repo = SKURepository(session)
        self.reservation_repo = ReservationRepository(session)
        self.order_repo = OrderRepository(session)

    def create_sku(self, name: str, initial_stock: int = 0) -> SKU:
        sku_id = str(uuid4())
        return self.sku_repo.create(sku_id, name, initial_stock)

    def adjust_stock(self, sku_id: str, quantity_delta: int) -> SKU:
        sku = self.sku_repo.get(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")
        result = self.sku_repo.update_stock(sku_id, quantity_delta)
        if result.current_stock < 0:
            raise InsufficientStockError("Stock cannot be negative")
        return result

    def create_reservation(
        self, sku_id: str, quantity: int, idempotency_key: str | None = None
    ) -> Reservation:
        # Check for idempotency: if same key exists, return it
        if idempotency_key:
            existing = self.reservation_repo.get_by_idempotency_key(idempotency_key)
            if existing:
                return existing

        # Check stock availability
        sku = self.sku_repo.get(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")
        if sku.current_stock < quantity:
            raise InsufficientStockError(
                f"Insufficient stock: need {quantity}, have {sku.current_stock}"
            )

        # Reserve stock and create reservation
        self.sku_repo.update_stock(sku_id, -quantity)

        reservation_id = str(uuid4())
        now = datetime.now()
        expires_at = now + timedelta(minutes=30)

        reservation = self.reservation_repo.create(
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )

        return reservation

    def confirm_reservation(self, reservation_id: str):
        reservation = self.reservation_repo.get(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        # Check if expired
        now = datetime.now()
        if reservation.expires_at <= now:
            self.reservation_repo.update_status(reservation_id, ReservationStatus.EXPIRED)
            raise ReservationExpiredError("Reservation has expired")

        # Check status
        if reservation.status != ReservationStatus.PENDING:
            raise ValueError(f"Cannot confirm reservation in {reservation.status} state")

        # Create order and mark reservation confirmed
        order_id = str(uuid4())
        order = self.order_repo.create(
            order_id=order_id,
            reservation_id=reservation_id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
        )
        self.reservation_repo.update_status(reservation_id, ReservationStatus.CONFIRMED)

        return order

    def cancel_reservation(self, reservation_id: str):
        reservation = self.reservation_repo.get(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        # Only cancel if still pending
        if reservation.status != ReservationStatus.PENDING:
            raise ValueError(f"Cannot cancel reservation in {reservation.status} state")

        # Release stock back
        self.sku_repo.update_stock(reservation.sku_id, reservation.quantity)
        self.reservation_repo.update_status(reservation_id, ReservationStatus.CANCELLED)

        return reservation

    def expire_old_reservations(self):
        now = datetime.now()
        expired = self.reservation_repo.get_expired(now)
        for res in expired:
            # Release stock back
            self.sku_repo.update_stock(res.sku_id, res.quantity)
            self.reservation_repo.update_status(res.id, ReservationStatus.EXPIRED)
        return len(expired)

    def get_order(self, order_id: str):
        order = self.order_repo.get(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        return order

    def list_orders(self, limit: int = 10, offset: int = 0):
        orders, total = self.order_repo.list_paginated(limit, offset)
        return orders, total
