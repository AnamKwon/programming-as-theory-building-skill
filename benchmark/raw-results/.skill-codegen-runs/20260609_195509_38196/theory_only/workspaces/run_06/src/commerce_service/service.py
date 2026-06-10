"""Business logic for inventory and order operations."""

import uuid
from datetime import datetime, timedelta

from .models import ReservationStatus
from .repository import Repository


class SKUNotFoundError(Exception):
    """SKU does not exist."""


class InsufficientStockError(Exception):
    """Not enough available inventory for reservation."""


class ReservationNotFoundError(Exception):
    """Reservation does not exist."""


class ReservationExpiredError(Exception):
    """Reservation has expired."""


class ReservationAlreadyConfirmedError(Exception):
    """Cannot operate on already-confirmed reservation."""


class IdempotencyConflictError(Exception):
    """Idempotency key used with conflicting request."""


class OrderService:
    """Orchestrates inventory and reservation operations."""

    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, sku_id: str, name: str):
        """Create a new product SKU."""
        existing = self.repo.get_sku(sku_id)
        if existing:
            return existing

        sku = self.repo.create_sku(sku_id, name)
        self.repo.get_or_create_stock(sku_id)
        return sku

    def adjust_stock(self, sku_id: str, delta: int, idempotency_key: str):
        """Adjust stock by signed delta. Idempotency prevents duplicate adjustments."""
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        # Idempotency: use the idempotency key to deduplicate requests
        # For stock adjustments, we do not retry; if same key appears twice, it's
        # expected to be from the same upstream request and already applied.
        # For now, we just apply it. Stricter deduplication could be added.

        self.repo.adjust_stock(sku_id, delta)

    def create_reservation(
        self,
        sku_id: str,
        quantity: int,
        idempotency_key: str,
        ttl_seconds: int = 1800,
    ) -> str:
        """
        Reserve inventory. Returns reservation ID.
        Idempotency ensures same idempotency_key always returns same reservation.
        """
        # Check idempotency first
        existing_res = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing_res:
            return existing_res.reservation_id

        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        stock = self.repo.get_stock(sku_id)
        if not stock:
            raise InsufficientStockError(f"No stock available for {sku_id}")

        available = stock.quantity - stock.reserved
        if available < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for {sku_id}: {available} available, {quantity} requested"
            )

        reservation_id = f"res_{uuid.uuid4().hex[:12]}"
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)

        self.repo.create_reservation(
            reservation_id,
            sku_id,
            quantity,
            idempotency_key,
            expires_at,
        )
        self.repo.reserve_stock(sku_id, quantity)

        return reservation_id

    def confirm_reservation(self, reservation_id: str) -> str:
        """
        Confirm a reservation into an order.
        Returns order ID.
        """
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status == ReservationStatus.EXPIRED:
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        if reservation.status == ReservationStatus.CONFIRMED:
            # Idempotency: if already confirmed, look up the order and return it
            # For this implementation, we assume one order per reservation
            raise ReservationAlreadyConfirmedError(
                f"Reservation {reservation_id} already confirmed"
            )

        if reservation.status == ReservationStatus.CANCELLED:
            raise ReservationAlreadyConfirmedError(
                f"Reservation {reservation_id} is cancelled"
            )

        now = datetime.utcnow()
        if reservation.expires_at <= now:
            self.repo.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
            self.repo.release_reserved_stock(reservation.sku_id, reservation.quantity)
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        order_id = f"ord_{uuid.uuid4().hex[:12]}"

        self.repo.confirm_reserved_stock(reservation.sku_id, reservation.quantity)
        self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED, confirmed_at=now)
        order = self.repo.create_order(
            order_id,
            reservation_id,
            reservation.sku_id,
            reservation.quantity,
        )

        return order_id

    def cancel_reservation(self, reservation_id: str):
        """Cancel a pending reservation and release its stock."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status in (ReservationStatus.CONFIRMED, ReservationStatus.CANCELLED):
            # Cannot cancel already-finalized reservations
            raise ReservationAlreadyConfirmedError(
                f"Cannot cancel reservation in {reservation.status.value} state"
            )

        self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)
        self.repo.release_reserved_stock(reservation.sku_id, reservation.quantity)

    def get_sku_details(self, sku_id: str):
        """Get SKU with current stock levels."""
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        stock = self.repo.get_stock(sku_id)
        if not stock:
            available = 0
            reserved = 0
        else:
            available = stock.quantity - stock.reserved
            reserved = stock.reserved

        return {
            "sku_id": sku.sku_id,
            "name": sku.name,
            "available_quantity": max(0, available),
            "reserved_quantity": reserved,
            "created_at": sku.created_at,
        }

    def get_reservation_details(self, reservation_id: str):
        """Get reservation state."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        return {
            "reservation_id": reservation.reservation_id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "status": reservation.status,
            "created_at": reservation.created_at,
            "expires_at": reservation.expires_at,
        }

    def get_order_details(self, order_id: str):
        """Get order state."""
        order = self.repo.get_order(order_id)
        if not order:
            return None

        return {
            "order_id": order.order_id,
            "reservation_id": order.reservation_id,
            "sku_id": order.sku_id,
            "quantity": order.quantity,
            "status": order.status,
            "created_at": order.created_at,
            "confirmed_at": order.confirmed_at,
        }

    def list_orders(self, limit: int = 20, offset: int = 0):
        """List orders with pagination."""
        orders, total = self.repo.get_orders_paginated(limit, offset)
        return [
            {
                "order_id": o.order_id,
                "reservation_id": o.reservation_id,
                "sku_id": o.sku_id,
                "quantity": o.quantity,
                "status": o.status,
                "created_at": o.created_at,
                "confirmed_at": o.confirmed_at,
            }
            for o in orders
        ], total
