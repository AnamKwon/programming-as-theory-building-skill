from typing import Optional

from commerce_service.models import (
    OrderResponse,
    OrdersListResponse,
    ReservationResponse,
    SkuResponse,
)
from commerce_service.repository import Repository


class Service:
    def __init__(self, repository: Repository):
        self.repo = repository

    def health_check(self) -> dict:
        """Health check with database status."""
        db_ok = self.repo.health_check()
        return {
            "status": "healthy" if db_ok else "unhealthy",
            "database": "ok" if db_ok else "error",
        }

    def create_sku(self, name: str, price: float, stock: int = 0) -> SkuResponse:
        """Create a new SKU."""
        return self.repo.create_sku(name, price, stock)

    def adjust_stock(self, sku_id: str, quantity: int) -> SkuResponse:
        """Adjust stock for a SKU. Raises ValueError if SKU not found."""
        result = self.repo.adjust_stock(sku_id, quantity)
        if result is None:
            raise ValueError(f"SKU not found: {sku_id}")
        return result

    def reserve(self, sku_id: str, quantity: int, idempotency_key: str) -> ReservationResponse:
        """
        Reserve inventory. Raises ValueError if:
        - SKU not found
        - Insufficient stock available
        """
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU not found: {sku_id}")

        if sku.current_stock < quantity:
            raise ValueError(
                f"Insufficient stock: {quantity} requested, {sku.current_stock} available"
            )

        result = self.repo.reserve(sku_id, quantity, idempotency_key)
        if result is None:
            raise ValueError("Failed to create reservation")

        return result

    def confirm_reservation(self, reservation_id: str) -> str:
        """
        Confirm a reservation and create an order.
        Returns the order ID.
        Raises ValueError if:
        - Reservation not found
        - Reservation already confirmed or cancelled
        - Reservation has expired
        """
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation not found: {reservation_id}")

        if reservation.status != "RESERVED":
            raise ValueError(f"Reservation is {reservation.status}, cannot confirm")

        from datetime import datetime

        if datetime.utcnow() > reservation.expires_at:
            raise ValueError(f"Reservation expired at {reservation.expires_at.isoformat()}")

        order_id = self.repo.confirm_reservation(reservation_id)
        if order_id is None:
            raise ValueError("Failed to confirm reservation")

        return order_id

    def cancel_reservation(self, reservation_id: str) -> bool:
        """Cancel a reservation. Returns True if cancelled, False if not found or already cancelled."""
        return self.repo.cancel_reservation(reservation_id)

    def get_order(self, order_id: str) -> OrderResponse:
        """Get an order. Raises ValueError if not found."""
        result = self.repo.get_order(order_id)
        if result is None:
            raise ValueError(f"Order not found: {order_id}")
        return result

    def list_orders(self, skip: int = 0, limit: int = 10) -> OrdersListResponse:
        """List orders with pagination."""
        orders, total = self.repo.list_orders(skip, limit)
        return OrdersListResponse(orders=orders, total=total, skip=skip, limit=limit)
