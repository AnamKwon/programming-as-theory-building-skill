from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .models import ReservationStatus, OrderStatus
from .repository import Repository


class InsufficientStockError(Exception):
    """Raised when attempting to reserve more stock than available."""
    pass


class ReservationNotFoundError(Exception):
    """Raised when a reservation is not found."""
    pass


class ReservationExpiredError(Exception):
    """Raised when a reservation has expired."""
    pass


class InvalidReservationStatusError(Exception):
    """Raised when attempting an operation on a reservation in the wrong state."""
    pass


class SKUNotFoundError(Exception):
    """Raised when a SKU is not found."""
    pass


class CommerceService:
    """Business logic for inventory and order orchestration.

    Enforces domain rules around stock availability, reservation expiration,
    idempotency, and order state transitions.
    """

    def __init__(self, repo: Repository, reservation_ttl_minutes: int = 15):
        self.repo = repo
        self.reservation_ttl = timedelta(minutes=reservation_ttl_minutes)

    # ─── SKU Management ──────────────────────────────────────────────────────

    def create_sku(self, name: str, initial_stock: int) -> dict:
        sku = self.repo.create_sku(name, initial_stock)
        return {"id": sku.id, "name": sku.name, "stock_level": sku.stock_level}

    def adjust_stock(self, sku_id: int, adjustment: int) -> dict:
        sku = self.repo.adjust_stock(sku_id, adjustment)
        return {"id": sku.id, "name": sku.name, "stock_level": sku.stock_level}

    # ─── Reservation Logic ───────────────────────────────────────────────────

    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """Create a reservation for a SKU quantity.

        Enforces: stock availability check, idempotency via idempotency_key.
        Idempotency: if key exists, return the existing reservation (pending or confirmed).
        """
        # Idempotency: if key exists, return it regardless of status
        if idempotency_key:
            existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
            if existing:
                return {
                    "id": existing.id,
                    "sku_id": existing.sku_id,
                    "quantity": existing.quantity,
                    "status": existing.status.value,
                    "created_at": existing.created_at,
                    "expires_at": existing.expires_at,
                }

        # Check SKU exists and has sufficient stock
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        if sku.stock_level < quantity:
            raise InsufficientStockError(
                f"SKU {sku_id} has {sku.stock_level} in stock, requested {quantity}"
            )

        # Create reservation with expiration
        expires_at = datetime.utcnow() + self.reservation_ttl
        reservation = self.repo.create_reservation(
            sku_id, quantity, expires_at, idempotency_key
        )

        return {
            "id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "status": reservation.status.value,
            "created_at": reservation.created_at,
            "expires_at": reservation.expires_at,
        }

    def confirm_reservation(self, reservation_id: int) -> dict:
        """Confirm a pending reservation and create an order.

        Enforces: reservation exists, is pending, and hasn't expired.
        Transitions reservation to confirmed and creates an order.
        """
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        # Check expiration
        if datetime.utcnow() > reservation.expires_at:
            self.repo.mark_reservation_expired(reservation_id)
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        # Check status
        if reservation.status != ReservationStatus.PENDING:
            raise InvalidReservationStatusError(
                f"Cannot confirm reservation in {reservation.status.value} state"
            )

        # Mark confirmed and create order
        self.repo.mark_reservation_confirmed(reservation_id)
        order = self.repo.create_order(
            reservation_id, reservation.sku_id, reservation.quantity
        )

        return {
            "id": order.id,
            "reservation_id": order.reservation_id,
            "sku_id": order.sku_id,
            "quantity": order.quantity,
            "status": order.status.value,
            "created_at": order.created_at,
        }

    def cancel_reservation(self, reservation_id: int) -> dict:
        """Cancel a reservation and release the stock hold.

        Enforces: reservation exists and is in a cancellable state (pending or confirmed).
        """
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status in (ReservationStatus.CANCELLED, ReservationStatus.EXPIRED):
            raise InvalidReservationStatusError(
                f"Cannot cancel reservation in {reservation.status.value} state"
            )

        self.repo.mark_reservation_cancelled(reservation_id)

        return {
            "id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "status": ReservationStatus.CANCELLED.value,
            "created_at": reservation.created_at,
            "expires_at": reservation.expires_at,
        }

    # ─── Order Lookup ───────────────────────────────────────────────────────

    def list_orders(self, skip: int = 0, limit: int = 20) -> dict:
        orders, total = self.repo.list_orders(skip, limit)
        return {
            "items": [
                {
                    "id": o.id,
                    "reservation_id": o.reservation_id,
                    "sku_id": o.sku_id,
                    "quantity": o.quantity,
                    "status": o.status.value,
                    "created_at": o.created_at,
                }
                for o in orders
            ],
            "total": total,
            "skip": skip,
            "limit": limit,
        }
