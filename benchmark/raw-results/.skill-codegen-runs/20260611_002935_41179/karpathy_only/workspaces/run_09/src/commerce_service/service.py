"""Business logic service layer."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from commerce_service.models import OrderResponse, ReservationResponse
from commerce_service.repository import Repository


class Service:
    """Business logic service."""

    RESERVATION_EXPIRATION_SECONDS = 300

    def __init__(self, repository: Repository):
        """Initialize service with repository."""
        self.repository = repository

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        """Create a new SKU."""
        sku_model = self.repository.create_sku(sku, initial_stock)
        return {"sku": sku_model.sku, "initial_stock": sku_model.initial_stock}

    def adjust_stock(self, sku: str, amount: int) -> dict:
        """Adjust stock for a SKU."""
        sku_model = self.repository.update_sku_stock(sku, amount)
        if not sku_model:
            raise ValueError(f"SKU {sku} not found")
        return {"sku": sku_model.sku, "available_stock": sku_model.available_stock}

    def create_reservation(
        self,
        sku: str,
        quantity: int,
        idempotency_key: str,
    ) -> ReservationResponse:
        """Create a reservation with idempotency and stock validation.

        Returns cached reservation if idempotency_key exists.
        Raises ValueError if insufficient stock.
        """
        existing_reservation = self.repository.get_reservation_by_idempotency_key(idempotency_key)
        if existing_reservation:
            return ReservationResponse(
                id=existing_reservation.id,
                sku=existing_reservation.sku,
                quantity=existing_reservation.quantity,
                status=existing_reservation.status,
                created_at=existing_reservation.created_at,
                idempotency_key=existing_reservation.idempotency_key,
            )

        sku_model = self.repository.get_sku(sku)
        if not sku_model:
            raise ValueError(f"SKU {sku} not found")

        if sku_model.available_stock < quantity:
            raise ValueError("Insufficient stock")

        reservation_id = str(uuid.uuid4())
        now_utc = datetime.now(timezone.utc).isoformat()

        self.repository.update_sku_stock(sku, -quantity)

        reservation = self.repository.create_reservation(
            reservation_id=reservation_id,
            sku=sku,
            quantity=quantity,
            idempotency_key=idempotency_key,
            status="PENDING",
            created_at=now_utc,
        )

        return ReservationResponse(
            id=reservation.id,
            sku=reservation.sku,
            quantity=reservation.quantity,
            status=reservation.status,
            created_at=reservation.created_at,
            idempotency_key=reservation.idempotency_key,
        )

    def confirm_reservation(self, reservation_id: str) -> ReservationResponse:
        """Confirm a reservation and create an order.

        Checks expiration, status, and creates corresponding order.
        Raises ValueError if invalid state or expired.
        """
        reservation = self.repository.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != "PENDING":
            raise ValueError(f"Reservation is {reservation.status}, not PENDING")

        created_at = datetime.fromisoformat(reservation.created_at)
        now = datetime.now(timezone.utc)
        elapsed = (now - created_at).total_seconds()

        if elapsed > self.RESERVATION_EXPIRATION_SECONDS:
            self.repository.update_reservation_status(reservation_id, "EXPIRED")
            self.repository.update_sku_stock(reservation.sku, reservation.quantity)
            raise ValueError("Reservation expired")

        self.repository.update_reservation_status(reservation_id, "CONFIRMED")

        order_id = str(uuid.uuid4())
        order_created_at = datetime.now(timezone.utc).isoformat()
        self.repository.create_order(
            order_id=order_id,
            reservation_id=reservation_id,
            sku=reservation.sku,
            quantity=reservation.quantity,
            created_at=order_created_at,
        )

        return ReservationResponse(
            id=reservation.id,
            sku=reservation.sku,
            quantity=reservation.quantity,
            status="CONFIRMED",
            created_at=reservation.created_at,
            idempotency_key=reservation.idempotency_key,
        )

    def cancel_reservation(self, reservation_id: str) -> ReservationResponse:
        """Cancel a reservation and restore stock.

        Raises ValueError if reservation not found or not PENDING.
        """
        reservation = self.repository.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != "PENDING":
            raise ValueError(f"Reservation is {reservation.status}, not PENDING")

        self.repository.update_reservation_status(reservation_id, "CANCELLED")
        self.repository.update_sku_stock(reservation.sku, reservation.quantity)

        return ReservationResponse(
            id=reservation.id,
            sku=reservation.sku,
            quantity=reservation.quantity,
            status="CANCELLED",
            created_at=reservation.created_at,
            idempotency_key=reservation.idempotency_key,
        )

    def get_orders_paginated(self, page: int = 1, size: int = 10) -> dict:
        """Get paginated orders."""
        orders, total = self.repository.get_orders_paginated(page=page, size=size)
        return {
            "page": page,
            "size": size,
            "total": total,
            "orders": [
                OrderResponse(
                    id=order.id,
                    reservation_id=order.reservation_id,
                    sku=order.sku,
                    quantity=order.quantity,
                    created_at=order.created_at,
                )
                for order in orders
            ],
        }
