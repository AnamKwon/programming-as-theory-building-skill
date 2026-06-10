import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .models import ReservationStatus
from .repository import OrderRepository, ReservationRepository, SKURepository


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class InvalidStateTransitionError(Exception):
    pass


class SKUNotFoundError(Exception):
    pass


class CommerceService:
    RESERVATION_TTL_MINUTES = 15

    def __init__(self, session: Session):
        self.session = session
        self.sku_repo = SKURepository(session)
        self.reservation_repo = ReservationRepository(session)
        self.order_repo = OrderRepository(session)

    def create_sku(self, sku_id: str, name: str, initial_stock: int) -> dict:
        """Create a new SKU with initial stock."""
        sku = self.sku_repo.create(sku_id, name, initial_stock)
        return {
            "sku_id": sku.id,
            "name": sku.name,
            "available_stock": sku.available_stock,
            "reserved_stock": sku.reserved_stock,
        }

    def adjust_stock(self, sku_id: str, quantity: int) -> dict:
        """Adjust available stock for a SKU."""
        sku = self.sku_repo.get(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        self.sku_repo.update_available_stock(sku_id, quantity)
        sku = self.sku_repo.get(sku_id)
        return {
            "sku_id": sku.id,
            "name": sku.name,
            "available_stock": sku.available_stock,
            "reserved_stock": sku.reserved_stock,
        }

    def create_reservation(
        self, sku_id: str, quantity: int, idempotency_key: Optional[str] = None
    ) -> dict:
        """Create a reservation for a SKU with optional idempotency."""
        if idempotency_key:
            existing = self.reservation_repo.get_by_idempotency_key(idempotency_key)
            if existing:
                return self._format_reservation(existing)

        sku = self.sku_repo.get(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        if sku.available_stock < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for {sku_id}: requested {quantity}, available {sku.available_stock}"
            )

        reservation_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=self.RESERVATION_TTL_MINUTES)

        reservation = self.reservation_repo.create(
            reservation_id, sku_id, quantity, expires_at, idempotency_key
        )

        self.sku_repo.update_reserved_stock(sku_id, quantity)
        self.sku_repo.update_available_stock(sku_id, -quantity)

        return self._format_reservation(reservation)

    def confirm_reservation(self, reservation_id: str) -> dict:
        """Confirm a pending reservation and create an order."""
        reservation = self.reservation_repo.get(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status != ReservationStatus.PENDING:
            raise InvalidStateTransitionError(
                f"Cannot confirm reservation in {reservation.status} state"
            )

        if datetime.utcnow() > reservation.expires_at:
            self.reservation_repo.update_status(reservation_id, ReservationStatus.EXPIRED)
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        self.reservation_repo.update_status(reservation_id, ReservationStatus.CONFIRMED)

        order_id = str(uuid.uuid4())
        order = self.order_repo.create(order_id)

        item_id = str(uuid.uuid4())
        self.order_repo.add_item(order_id, item_id, reservation.sku_id, reservation.quantity)

        return {
            "order_id": order_id,
            "status": order.status,
            "items": [{"sku_id": reservation.sku_id, "quantity": reservation.quantity}],
            "created_at": order.created_at,
            "updated_at": order.updated_at,
        }

    def cancel_reservation(self, reservation_id: str) -> dict:
        """Cancel a pending reservation and release stock."""
        reservation = self.reservation_repo.get(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status != ReservationStatus.PENDING:
            raise InvalidStateTransitionError(
                f"Cannot cancel reservation in {reservation.status} state"
            )

        self.reservation_repo.update_status(reservation_id, ReservationStatus.CANCELLED)

        self.sku_repo.update_reserved_stock(reservation.sku_id, -reservation.quantity)
        self.sku_repo.update_available_stock(reservation.sku_id, reservation.quantity)

        return self._format_reservation(reservation)

    def get_order(self, order_id: str) -> dict:
        """Get order details."""
        order = self.order_repo.get(order_id)
        if not order:
            raise Exception(f"Order {order_id} not found")

        items = [{"sku_id": item.sku_id, "quantity": item.quantity} for item in order.items]
        return {
            "order_id": order.id,
            "status": order.status,
            "items": items,
            "created_at": order.created_at,
            "updated_at": order.updated_at,
        }

    def list_orders(self, page: int = 1, page_size: int = 10) -> dict:
        """List orders with pagination."""
        orders, total = self.order_repo.list_paginated(page, page_size)
        items = [self.get_order(order.id) for order in orders]

        pages = (total + page_size - 1) // page_size
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": pages,
        }

    def _format_reservation(self, reservation) -> dict:
        return {
            "reservation_id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "status": reservation.status,
            "created_at": reservation.created_at,
            "expires_at": reservation.expires_at,
        }
