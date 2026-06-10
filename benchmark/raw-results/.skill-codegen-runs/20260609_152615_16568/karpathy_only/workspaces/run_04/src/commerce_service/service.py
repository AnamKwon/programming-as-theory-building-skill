from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .models import OrderStatus, ReservationStatus
from .repository import OrderRepository, ReservationRepository, SKURepository


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class InvalidStateTransitionError(Exception):
    pass


class DuplicateReservationError(Exception):
    pass


class CommerceService:
    RESERVATION_TTL_MINUTES = 15

    def __init__(self, db: Session):
        self.db = db
        self.sku_repo = SKURepository(db)
        self.reservation_repo = ReservationRepository(db)
        self.order_repo = OrderRepository(db)

    def create_sku(self, code: str, name: str, initial_stock: int):
        return self.sku_repo.create(code, name, initial_stock)

    def adjust_stock(self, sku_id: int, amount: int):
        sku = self.sku_repo.adjust_stock(sku_id, amount)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        return sku

    def create_reservation(
        self, sku_id: int, amount: int, idempotency_key: str
    ) -> dict:
        sku = self.sku_repo.get_by_id(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        existing = self.reservation_repo.get_by_idempotency_key(idempotency_key)
        if existing:
            if existing.status == ReservationStatus.PENDING and existing.expires_at > datetime.utcnow():
                return {
                    "reservation": existing,
                    "order_id": self._get_or_create_order_for_reservation(existing).id,
                    "is_duplicate": True,
                }
            elif existing.status == ReservationStatus.EXPIRED or existing.expires_at <= datetime.utcnow():
                raise DuplicateReservationError(
                    f"Previous reservation {existing.id} has expired; use a new idempotency key"
                )

        reserved = self.reservation_repo.get_reserved_amount_for_sku(sku_id)
        available = sku.available_stock - reserved

        if available < amount:
            raise InsufficientStockError(
                f"Insufficient stock for SKU {sku_id}. "
                f"Requested: {amount}, Available: {available}"
            )

        expires_at = datetime.utcnow() + timedelta(minutes=self.RESERVATION_TTL_MINUTES)
        reservation = self.reservation_repo.create(sku_id, amount, idempotency_key, expires_at)

        order = self.order_repo.create(sku_id, amount)

        return {
            "reservation": reservation,
            "order_id": order.id,
            "is_duplicate": False,
        }

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.reservation_repo.get_by_id(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status != ReservationStatus.PENDING:
            raise InvalidStateTransitionError(
                f"Cannot confirm reservation in {reservation.status} state"
            )

        if reservation.expires_at <= datetime.utcnow():
            self.reservation_repo.update_status(reservation_id, ReservationStatus.EXPIRED)
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        reservation = self.reservation_repo.update_status(reservation_id, ReservationStatus.CONFIRMED)

        sku = self.sku_repo.get_by_id(reservation.sku_id)
        sku.available_stock -= reservation.amount
        self.db.commit()
        self.db.refresh(sku)

        order = self.order_repo.update_status(reservation_id, OrderStatus.CONFIRMED)

        return {"reservation": reservation, "order": order}

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.reservation_repo.get_by_id(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status == ReservationStatus.CANCELLED:
            return {"reservation": reservation}

        if reservation.status == ReservationStatus.CONFIRMED:
            sku = self.sku_repo.get_by_id(reservation.sku_id)
            sku.available_stock += reservation.amount
            self.db.commit()
            self.db.refresh(sku)

        reservation = self.reservation_repo.update_status(reservation_id, ReservationStatus.CANCELLED)

        self.order_repo.update_status(reservation_id, OrderStatus.COMPLETED)

        return {"reservation": reservation}

    def get_order(self, order_id: int):
        order = self.order_repo.get_by_id(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        return order

    def list_orders(self, page: int, page_size: int):
        orders, total = self.order_repo.list_paginated(page, page_size)
        total_pages = (total + page_size - 1) // page_size
        return {
            "items": orders,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    def _get_or_create_order_for_reservation(self, reservation):
        order = self.order_repo.get_by_id(reservation.id)
        if not order:
            order = self.order_repo.create(reservation.sku_id, reservation.amount)
        return order
