"""Business logic layer."""

from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import OrderStatus, ReservationStatus
from .repository import Repository


class CommerceProblem(Exception):
    """Domain-level exception."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class CommerceService:
    """Service layer for commerce operations."""

    def __init__(self, session: Session):
        self.repo = Repository(session)

    def create_sku(self, sku_code: str, stock_available: int):
        """Create a new SKU."""
        try:
            return self.repo.create_sku(sku_code, stock_available)
        except IntegrityError:
            raise CommerceProblem(
                f"SKU code '{sku_code}' already exists",
                status_code=409,
            )

    def adjust_stock(self, sku_id: int, delta: int):
        """Adjust stock for a SKU."""
        sku = self.repo.get_sku_by_id(sku_id)
        if not sku:
            raise CommerceProblem("SKU not found", status_code=404)

        new_stock = sku.stock_available + delta
        if new_stock < 0:
            raise CommerceProblem(
                f"Insufficient stock: have {sku.stock_available}, requested -{delta}",
                status_code=400,
            )

        return self.repo.adjust_stock(sku_id, delta)

    def create_reservation(
        self, sku_id: int, quantity: int, idempotency_key: str, ttl_seconds: int
    ):
        """Create a reservation or return existing if idempotency key matches."""
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing.status in (ReservationStatus.CANCELLED, ReservationStatus.EXPIRED):
                raise CommerceProblem(
                    "Idempotency key was used for a cancelled/expired reservation",
                    status_code=409,
                )
            return existing

        sku = self.repo.get_sku_by_id(sku_id)
        if not sku:
            raise CommerceProblem("SKU not found", status_code=404)

        if sku.stock_available < quantity:
            raise CommerceProblem(
                f"Insufficient stock: have {sku.stock_available}, need {quantity}",
                status_code=400,
            )

        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        try:
            return self.repo.create_reservation(sku_id, quantity, idempotency_key, expires_at)
        except IntegrityError:
            raise CommerceProblem("Idempotency key already used", status_code=409)

    def confirm_reservation(self, reservation_id: int):
        """Confirm a pending reservation."""
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise CommerceProblem("Reservation not found", status_code=404)

        if reservation.status == ReservationStatus.EXPIRED:
            raise CommerceProblem("Reservation has expired", status_code=400)

        if reservation.status != ReservationStatus.PENDING:
            raise CommerceProblem(
                f"Reservation is {reservation.status}, cannot confirm",
                status_code=400,
            )

        if datetime.utcnow() > reservation.expires_at:
            self.repo.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
            raise CommerceProblem("Reservation has expired", status_code=400)

        self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)
        reservation = self.repo.get_reservation_by_id(reservation_id)

        order = self.repo.create_order(reservation_id)
        return reservation, order

    def cancel_reservation(self, reservation_id: int):
        """Cancel a reservation."""
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            raise CommerceProblem("Reservation not found", status_code=404)

        if reservation.status not in (ReservationStatus.PENDING, ReservationStatus.CONFIRMED):
            raise CommerceProblem(
                f"Cannot cancel reservation in {reservation.status} status",
                status_code=400,
            )

        self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)
        return self.repo.get_reservation_by_id(reservation_id)

    def get_order(self, order_id: int):
        """Get an order by ID."""
        order = self.repo.get_order_by_id(order_id)
        if not order:
            raise CommerceProblem("Order not found", status_code=404)
        return order

    def list_orders(self, offset: int = 0, limit: int = 20):
        """List orders with pagination."""
        if offset < 0 or limit < 1 or limit > 100:
            raise CommerceProblem("Invalid pagination parameters", status_code=400)
        return self.repo.list_orders(offset, limit)
