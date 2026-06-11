"""Business logic for the commerce service."""

from datetime import datetime
from typing import Optional

from commerce_service.models import ReservationStatus
from commerce_service.repository import (
    SKURepository,
    ReservationRepository,
    OrderRepository,
)


class SKUService:
    """Service for SKU operations."""

    def __init__(self):
        self.sku_repo = SKURepository()

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        """Create a new SKU with initial stock."""
        return self.sku_repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> Optional[dict]:
        """Adjust stock level for a SKU."""
        return self.sku_repo.update_stock(sku, amount)

    def get_available_stock(self, sku: str) -> Optional[int]:
        """Get available stock for a SKU."""
        sku_data = self.sku_repo.get_sku(sku)
        if sku_data:
            return sku_data["available_stock"]
        return None


class ReservationService:
    """Service for reservation operations."""

    def __init__(self):
        self.sku_repo = SKURepository()
        self.reservation_repo = ReservationRepository()
        self.order_repo = OrderRepository()

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> tuple[dict, int]:
        """
        Create a reservation for a SKU.

        Returns (reservation_data, status_code).
        """
        existing = self.reservation_repo.get_reservation_by_idempotency_key(
            idempotency_key
        )
        if existing:
            return (existing, 201)

        available_stock = self.sku_repo.get_sku(sku)
        if not available_stock or available_stock["available_stock"] < quantity:
            return ({"detail": "Insufficient stock"}, 400)

        self.sku_repo.update_stock(sku, -quantity)
        reservation = self.reservation_repo.create_reservation(
            sku, quantity, idempotency_key
        )
        return (reservation, 201)

    def confirm_reservation(self, reservation_id: int) -> tuple[dict, int]:
        """
        Confirm a reservation and create an order.

        Returns (response_data, status_code).
        """
        reservation = self.reservation_repo.get_reservation(reservation_id)

        if not reservation:
            return ({"detail": "Reservation not found"}, 404)

        if reservation["status"] != ReservationStatus.PENDING:
            return ({"detail": "Reservation is not in PENDING status"}, 400)

        now = datetime.utcnow()
        created = datetime.fromisoformat(reservation["created_at"])
        elapsed = (now - created).total_seconds()

        if elapsed > 300:
            self.reservation_repo.update_reservation_status(
                reservation_id, ReservationStatus.EXPIRED
            )
            self.sku_repo.update_stock(reservation["sku"], reservation["quantity"])
            return ({"detail": "Reservation expired"}, 400)

        self.reservation_repo.update_reservation_status(
            reservation_id, ReservationStatus.CONFIRMED
        )
        order = self.order_repo.create_order(reservation_id)
        return (order, 200)

    def cancel_reservation(self, reservation_id: int) -> tuple[dict, int]:
        """
        Cancel a reservation and restore stock.

        Returns (response_data, status_code).
        """
        reservation = self.reservation_repo.get_reservation(reservation_id)

        if not reservation:
            return ({"detail": "Reservation not found"}, 404)

        if reservation["status"] != ReservationStatus.PENDING:
            return ({"detail": "Reservation is not in PENDING status"}, 400)

        self.reservation_repo.update_reservation_status(
            reservation_id, ReservationStatus.CANCELLED
        )
        self.sku_repo.update_stock(reservation["sku"], reservation["quantity"])
        return (reservation, 200)


class OrderService:
    """Service for order operations."""

    def __init__(self):
        self.order_repo = OrderRepository()

    def get_orders(self, page: int = 1, size: int = 10) -> dict:
        """Get paginated list of orders."""
        return self.order_repo.get_orders(page, size)
