"""Service layer with business logic."""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .models import OrderORM, ReservationORM, SkuORM
from .repository import OrderRepository, ReservationRepository, SkuRepository


class InsufficientStockError(Exception):
    """Raised when attempting to reserve more stock than available."""

    pass


class ReservationExpiredError(Exception):
    """Raised when attempting to confirm an expired reservation."""

    pass


class InvalidReservationStatusError(Exception):
    """Raised when attempting an invalid state transition."""

    pass


class NotFoundError(Exception):
    """Raised when a requested resource is not found."""

    pass


class CommerceService:
    """Service layer for commerce operations."""

    def __init__(self, session: Session):
        self.session = session
        self.sku_repo = SkuRepository(session)
        self.reservation_repo = ReservationRepository(session)
        self.order_repo = OrderRepository(session)

    def create_sku(self, sku_code: str, initial_stock: int = 0) -> SkuORM:
        """Create a new SKU with initial stock."""
        return self.sku_repo.create(sku_code, initial_stock)

    def adjust_stock(self, sku_id: int, quantity_delta: int) -> SkuORM:
        """Adjust stock quantity for a SKU."""
        sku = self.sku_repo.get_by_id(sku_id)
        if not sku:
            raise NotFoundError(f"SKU with id {sku_id} not found")

        if sku.stock_quantity + quantity_delta < 0:
            raise ValueError("Stock quantity cannot be negative")

        return self.sku_repo.update_stock(sku_id, quantity_delta)

    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        idempotency_key: str,
        ttl_seconds: int = 3600,
    ) -> ReservationORM:
        """
        Create a reservation for a SKU.

        Idempotency: if the same idempotency_key exists and is still pending/confirmed,
        return the existing reservation. If it's expired or cancelled, raise an error.
        """
        existing = self.reservation_repo.get_by_idempotency_key(idempotency_key)
        if existing:
            if existing.status in ("PENDING", "CONFIRMED"):
                return existing
            else:
                raise ValueError(
                    f"Idempotency key already used with status {existing.status}"
                )

        sku = self.sku_repo.get_by_id(sku_id)
        if not sku:
            raise NotFoundError(f"SKU with id {sku_id} not found")

        if sku.stock_quantity < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for SKU {sku_id}. "
                f"Available: {sku.stock_quantity}, Requested: {quantity}"
            )

        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        reservation = self.reservation_repo.create(
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
        )

        sku.stock_quantity -= quantity
        self.session.commit()

        return reservation

    def confirm_reservation(self, reservation_id: int) -> tuple[ReservationORM, OrderORM]:
        """Confirm a reservation and create an order."""
        reservation = self.reservation_repo.get_by_id(reservation_id)
        if not reservation:
            raise NotFoundError(f"Reservation with id {reservation_id} not found")

        if reservation.status != "PENDING":
            raise InvalidReservationStatusError(
                f"Cannot confirm reservation with status {reservation.status}"
            )

        if datetime.utcnow() > reservation.expires_at:
            reservation.status = "EXPIRED"
            self.session.commit()
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        reservation.status = "CONFIRMED"
        self.session.commit()

        order = self.order_repo.create(
            reservation_id=reservation_id,
            status="CONFIRMED",
        )

        return reservation, order

    def cancel_reservation(self, reservation_id: int) -> ReservationORM:
        """Cancel a reservation and restore stock."""
        reservation = self.reservation_repo.get_by_id(reservation_id)
        if not reservation:
            raise NotFoundError(f"Reservation with id {reservation_id} not found")

        if reservation.status not in ("PENDING", "CONFIRMED"):
            raise InvalidReservationStatusError(
                f"Cannot cancel reservation with status {reservation.status}"
            )

        sku = self.sku_repo.get_by_id(reservation.sku_id)
        if sku:
            sku.stock_quantity += reservation.quantity
            self.session.commit()

        reservation.status = "CANCELLED"
        self.session.commit()

        order = self.order_repo.get_by_reservation_id(reservation_id)
        if order and order.status != "CANCELLED":
            order.status = "CANCELLED"
            self.session.commit()

        return reservation

    def get_order(self, order_id: int) -> OrderORM:
        """Get order by ID."""
        order = self.order_repo.get_by_id(order_id)
        if not order:
            raise NotFoundError(f"Order with id {order_id} not found")
        return order

    def list_orders(self, limit: int = 10, offset: int = 0) -> tuple[list[OrderORM], int, bool]:
        """List orders with pagination."""
        orders, total = self.order_repo.list_paginated(limit=limit, offset=offset)
        has_more = len(orders) > limit
        if has_more:
            orders = orders[:limit]
        return orders, total, has_more
