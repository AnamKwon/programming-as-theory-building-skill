"""Business logic for inventory and order operations."""

import uuid
from datetime import datetime, timedelta
from typing import Optional

from .models import OrderResponse, OrderStatus, ReservationResponse, ReservationStatus
from .repository import Repository


class InsufficientStockError(Exception):
    """Raised when requested quantity exceeds available stock."""

    pass


class ReservationExpiredError(Exception):
    """Raised when attempting to confirm an expired reservation."""

    pass


class ReservationNotFoundError(Exception):
    """Raised when reservation cannot be found."""

    pass


class ReservationAlreadyProcessedError(Exception):
    """Raised when trying to confirm/cancel a reservation that's not pending."""

    pass


class SKUNotFoundError(Exception):
    """Raised when SKU cannot be found."""

    pass


class Service:
    """Business logic layer."""

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku_id: str, name: str, initial_stock: int) -> dict:
        """Create a new SKU."""
        sku = self.repo.create_sku(sku_id, name, initial_stock)
        return {"id": sku.id, "name": sku.name, "current_stock": sku.current_stock}

    def list_skus(self) -> list[dict]:
        """List all SKUs."""
        skus = self.repo.list_skus()
        return [
            {"id": sku.id, "name": sku.name, "current_stock": sku.current_stock} for sku in skus
        ]

    def adjust_stock(self, sku_id: str, adjustment: int) -> dict:
        """Adjust stock for a SKU.

        Raises SKUNotFoundError if SKU does not exist.
        """
        sku = self.repo.adjust_stock(sku_id, adjustment)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")
        return {"id": sku.id, "name": sku.name, "current_stock": sku.current_stock}

    def create_reservation(
        self,
        sku_id: str,
        quantity: int,
        ttl_seconds: int,
        idempotency_key: Optional[str] = None,
    ) -> ReservationResponse:
        """Create a reservation for inventory.

        Idempotency: If idempotency_key is provided and a reservation with that key
        already exists, return the existing reservation instead of creating a new one.

        Raises:
            SKUNotFoundError: If SKU does not exist.
            InsufficientStockError: If stock is insufficient.
        """
        if idempotency_key:
            existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
            if existing:
                return ReservationResponse(
                    id=existing.id,
                    sku_id=existing.sku_id,
                    quantity=existing.quantity,
                    status=ReservationStatus(existing.status),
                    expires_at=existing.expires_at,
                    created_at=existing.created_at,
                )

        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        if sku.current_stock < quantity:
            raise InsufficientStockError(
                f"SKU {sku_id} has {sku.current_stock} in stock, need {quantity}"
            )

        reservation_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)

        reservation = self.repo.create_reservation(
            reservation_id, sku_id, quantity, expires_at, idempotency_key
        )

        self.repo.adjust_stock(sku_id, -quantity)

        return ReservationResponse(
            id=reservation.id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            status=ReservationStatus(reservation.status),
            expires_at=reservation.expires_at,
            created_at=reservation.created_at,
        )

    def confirm_reservation(self, reservation_id: str) -> tuple[ReservationResponse, OrderResponse]:
        """Confirm a reservation and create an order.

        Raises:
            ReservationNotFoundError: If reservation does not exist.
            ReservationExpiredError: If reservation has expired.
            ReservationAlreadyProcessedError: If reservation is not in pending state.
        """
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status != ReservationStatus.PENDING:
            raise ReservationAlreadyProcessedError(
                f"Reservation {reservation_id} is {reservation.status}, not pending"
            )

        if datetime.utcnow() > reservation.expires_at:
            self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)

        order_id = str(uuid.uuid4())
        order = self.repo.create_order(order_id, reservation_id, OrderStatus.CONFIRMED)

        return ReservationResponse(
            id=reservation.id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            status=ReservationStatus.CONFIRMED,
            expires_at=reservation.expires_at,
            created_at=reservation.created_at,
        ), OrderResponse(
            id=order.id,
            reservation_id=order.reservation_id,
            status=OrderStatus(order.status),
            created_at=order.created_at,
        )

    def cancel_reservation(self, reservation_id: str) -> ReservationResponse:
        """Cancel a reservation and restore stock.

        Raises:
            ReservationNotFoundError: If reservation does not exist.
            ReservationAlreadyProcessedError: If reservation is not in pending state.
        """
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status != ReservationStatus.PENDING:
            raise ReservationAlreadyProcessedError(
                f"Reservation {reservation_id} is {reservation.status}, not pending"
            )

        self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)
        self.repo.adjust_stock(reservation.sku_id, reservation.quantity)

        return ReservationResponse(
            id=reservation.id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            status=ReservationStatus.CANCELLED,
            expires_at=reservation.expires_at,
            created_at=reservation.created_at,
        )

    def get_order(self, order_id: str) -> Optional[OrderResponse]:
        """Get an order by ID."""
        order = self.repo.get_order(order_id)
        if not order:
            return None
        return OrderResponse(
            id=order.id,
            reservation_id=order.reservation_id,
            status=OrderStatus(order.status),
            created_at=order.created_at,
        )

    def list_orders(
        self, limit: int = 10, offset: int = 0
    ) -> tuple[list[OrderResponse], int]:
        """List orders with pagination. Returns (orders, total_count)."""
        orders, total = self.repo.list_orders(limit, offset)
        return (
            [
                OrderResponse(
                    id=order.id,
                    reservation_id=order.reservation_id,
                    status=OrderStatus(order.status),
                    created_at=order.created_at,
                )
                for order in orders
            ],
            total,
        )
