"""Business logic layer."""
from datetime import datetime, timedelta
from typing import Optional

from .repository import Repository
from .models import (
    ReservationResponse,
    ConfirmReservationResponse,
    CancelReservationResponse,
    OrderResponse,
)


RESERVATION_EXPIRATION_SECONDS = 300


class CommerceService:
    """Service layer for commerce operations."""

    def __init__(self, repository: Repository):
        self.repository = repository

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        """Create a new SKU with initial stock."""
        sku_record = self.repository.create_sku(sku, initial_stock)
        return {
            "id": sku_record.id,
            "sku": sku_record.sku,
            "available_stock": sku_record.available_stock,
        }

    def adjust_stock(self, sku: str, amount: int) -> dict:
        """Adjust stock levels for a SKU."""
        sku_record = self.repository.adjust_stock(sku, amount)
        if not sku_record:
            raise ValueError(f"SKU not found: {sku}")
        return {
            "sku": sku_record.sku,
            "available_stock": sku_record.available_stock,
        }

    def create_reservation(
        self,
        sku: str,
        quantity: int,
        idempotency_key: str,
    ) -> ReservationResponse:
        """Create a reservation (idempotent).

        Raises ValueError if stock is insufficient or idempotency_key already exists.
        """
        existing = self.repository.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return ReservationResponse(
                id=existing.id,
                sku=existing.sku,
                quantity=existing.quantity,
                status=existing.status,
                idempotency_key=existing.idempotency_key,
                created_at=existing.created_at,
            )

        sku_record = self.repository.get_sku_by_name(sku)
        if not sku_record:
            raise ValueError(f"SKU not found: {sku}")

        if sku_record.available_stock < quantity:
            raise ValueError("Insufficient stock")

        self.repository.adjust_stock(sku, -quantity)

        reservation = self.repository.create_reservation(sku, quantity, idempotency_key)
        return ReservationResponse(
            id=reservation.id,
            sku=reservation.sku,
            quantity=reservation.quantity,
            status=reservation.status,
            idempotency_key=reservation.idempotency_key,
            created_at=reservation.created_at,
        )

    def confirm_reservation(
        self,
        reservation_id: int,
    ) -> ConfirmReservationResponse:
        """Confirm a reservation and create an order.

        Raises ValueError if reservation not found, not in PENDING status, or expired.
        """
        reservation = self.repository.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation not found: {reservation_id}")

        if reservation.status != "PENDING":
            raise ValueError(f"Reservation is not in PENDING status: {reservation.status}")

        elapsed = datetime.utcnow() - reservation.created_at
        if elapsed.total_seconds() > RESERVATION_EXPIRATION_SECONDS:
            self.repository.update_reservation_status(reservation_id, "EXPIRED")
            self.repository.adjust_stock(reservation.sku, reservation.quantity)
            raise ValueError("Reservation expired")

        self.repository.update_reservation_status(reservation_id, "CONFIRMED")
        order = self.repository.create_order(reservation_id)

        return ConfirmReservationResponse(
            id=reservation_id,
            status="CONFIRMED",
            order_id=order.id,
        )

    def cancel_reservation(
        self,
        reservation_id: int,
    ) -> CancelReservationResponse:
        """Cancel a reservation and restore stock.

        Raises ValueError if reservation not found or not in PENDING status.
        """
        reservation = self.repository.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation not found: {reservation_id}")

        if reservation.status != "PENDING":
            raise ValueError(f"Reservation is not in PENDING status: {reservation.status}")

        self.repository.update_reservation_status(reservation_id, "CANCELLED")
        self.repository.adjust_stock(reservation.sku, reservation.quantity)

        return CancelReservationResponse(
            id=reservation_id,
            status="CANCELLED",
            stock_restored=reservation.quantity,
        )

    def get_orders_paginated(
        self,
        page: int = 1,
        size: int = 10,
    ) -> dict:
        """Get paginated list of orders."""
        orders, total = self.repository.get_orders_paginated(page, size)
        return {
            "orders": [
                {
                    "id": order.id,
                    "reservation_id": order.reservation_id,
                    "created_at": order.created_at,
                }
                for order in orders
            ],
            "page": page,
            "size": size,
            "total": total,
        }
