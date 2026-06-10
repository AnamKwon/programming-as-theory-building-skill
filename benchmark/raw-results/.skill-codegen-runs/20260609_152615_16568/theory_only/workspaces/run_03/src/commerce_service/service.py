"""Business logic layer for commerce operations."""

import uuid
from datetime import datetime
from typing import Optional

from commerce_service.models import ReservationStatus
from commerce_service.repository import Repository


class InsufficientStockError(Exception):
    """Raised when not enough stock is available for a reservation."""

    pass


class ReservationNotFoundError(Exception):
    """Raised when a reservation cannot be found."""

    pass


class ReservationAlreadyExpiredError(Exception):
    """Raised when attempting to operate on an expired reservation."""

    pass


class SKUNotFoundError(Exception):
    """Raised when a SKU does not exist."""

    pass


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku_id: str, name: str) -> dict:
        """Create a new SKU."""
        self.repo.create_sku(sku_id, name)
        return {"sku_id": sku_id, "name": name}

    def adjust_stock(self, sku_id: str, adjustment: int) -> dict:
        """Adjust stock level for a SKU."""
        if not self.repo.get_sku(sku_id):
            raise SKUNotFoundError(f"SKU {sku_id} not found")
        new_level = self.repo.adjust_stock(sku_id, adjustment)
        return {"sku_id": sku_id, "new_available": new_level}

    def create_reservation(
        self, order_id: str, sku_id: str, quantity: int, idempotency_key: str
    ) -> dict:
        """Create a reservation with idempotency.

        Returns existing reservation if idempotency key is reused.
        """
        # Check for existing reservation with same idempotency key
        existing = self.repo.check_idempotency(idempotency_key)
        if existing:
            if existing["status"] == ReservationStatus.EXPIRED.value:
                raise ReservationAlreadyExpiredError(
                    f"Reservation {existing['id']} has expired"
                )
            return {"id": existing["id"], "status": existing["status"]}

        # Verify SKU exists
        if not self.repo.get_sku(sku_id):
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        # Check stock availability
        stock = self.repo.get_stock_level(sku_id)
        if not stock or (stock["available"] - stock["reserved"]) < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for {sku_id}. Available: {stock['available'] - stock['reserved'] if stock else 0}"
            )

        # Create reservation
        reservation_id = str(uuid.uuid4())
        self.repo.create_reservation(
            reservation_id, order_id, sku_id, quantity, idempotency_key
        )

        return {
            "id": reservation_id,
            "order_id": order_id,
            "sku_id": sku_id,
            "quantity": quantity,
            "status": ReservationStatus.PENDING.value,
        }

    def confirm_reservation(self, reservation_id: str) -> dict:
        """Confirm a pending reservation."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation["status"] == ReservationStatus.EXPIRED.value:
            raise ReservationAlreadyExpiredError(f"Reservation {reservation_id} has expired")

        self.repo.confirm_reservation(reservation_id)
        return {
            "id": reservation_id,
            "status": ReservationStatus.CONFIRMED.value,
        }

    def cancel_reservation(self, reservation_id: str) -> dict:
        """Cancel a reservation and release reserved stock."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        self.repo.cancel_reservation(reservation_id)
        return {
            "id": reservation_id,
            "status": ReservationStatus.CANCELLED.value,
        }

    def get_order(self, order_id: str) -> Optional[dict]:
        """Get order details with all reservations."""
        order = self.repo.get_order(order_id)
        if not order:
            return None

        reservations = self.repo.get_order_reservations(order_id)
        return {
            "order": {
                "id": order["id"],
                "status": order["status"],
                "created_at": datetime.fromisoformat(order["created_at"]),
            },
            "reservations": [
                {
                    "id": r["id"],
                    "order_id": r["order_id"],
                    "sku_id": r["sku_id"],
                    "quantity": r["quantity"],
                    "status": r["status"],
                    "created_at": datetime.fromisoformat(r["created_at"]),
                    "expires_at": datetime.fromisoformat(r["expires_at"])
                    if r["expires_at"]
                    else None,
                }
                for r in reservations
            ],
        }

    def list_orders(self, offset: int = 0, limit: int = 10) -> dict:
        """List orders with pagination."""
        orders, total = self.repo.list_orders(offset, limit)
        return {
            "orders": [
                {
                    "id": o["id"],
                    "status": o["status"],
                    "created_at": datetime.fromisoformat(o["created_at"]),
                }
                for o in orders
            ],
            "total": total,
            "offset": offset,
            "limit": limit,
        }
