from datetime import datetime, timedelta, timezone
from decimal import Decimal

from .models import ReservationState
from .repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class SKUNotFoundError(Exception):
    pass


class InvalidStateTransitionError(Exception):
    pass


class CommerceService:
    RESERVATION_EXPIRY_MINUTES = 15

    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, sku_code: str, name: str) -> dict:
        sku = self.repo.create_sku(sku_code, name)
        self.repo.create_stock(sku.id)
        return {"id": sku.id, "sku_code": sku.sku_code, "name": sku.name}

    def adjust_stock(self, sku_id: int, adjustment: Decimal) -> dict:
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        stock = self.repo.get_stock(sku_id)
        if not stock:
            raise SKUNotFoundError(f"Stock not found for SKU {sku_id}")

        new_available = stock.available + adjustment
        if new_available < 0:
            raise ValueError("Cannot adjust stock below zero")

        stock = self.repo.update_stock(sku_id, available=new_available)
        return {
            "sku_id": stock.sku_id,
            "available": float(stock.available),
            "reserved": float(stock.reserved),
            "committed": float(stock.committed),
        }

    def create_reservation(
        self, sku_id: int, quantity: Decimal, idempotency_key: str
    ) -> dict:
        # Check for duplicate idempotency key
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing.state == ReservationState.PENDING and self._is_expired(existing):
                raise ReservationExpiredError(f"Previous reservation has expired")
            return {
                "id": existing.id,
                "sku_id": existing.sku_id,
                "quantity": float(existing.quantity),
                "state": existing.state,
                "created_at": existing.created_at.isoformat(),
            }

        # Check SKU exists
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        # Check stock availability
        stock = self.repo.get_stock(sku_id)
        if not stock or stock.available < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for SKU {sku_id}. Available: {stock.available if stock else 0}, Required: {quantity}"
            )

        # Reserve stock
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=self.RESERVATION_EXPIRY_MINUTES
        )
        reservation = self.repo.create_reservation(
            sku_id, quantity, idempotency_key, expires_at
        )

        # Update stock: move from available to reserved
        new_available = stock.available - quantity
        new_reserved = stock.reserved + quantity
        self.repo.update_stock(sku_id, available=new_available, reserved=new_reserved)

        return {
            "id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": float(reservation.quantity),
            "state": reservation.state,
            "created_at": reservation.created_at.isoformat(),
        }

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.state != ReservationState.PENDING:
            raise InvalidStateTransitionError(
                f"Cannot confirm reservation in state {reservation.state}"
            )

        if self._is_expired(reservation):
            # Move to cancelled
            reservation = self.repo.update_reservation(
                reservation_id,
                ReservationState.CANCELLED,
                cancelled_at=datetime.now(timezone.utc),
            )
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        # Move stock from reserved to committed
        stock = self.repo.get_stock(reservation.sku_id)
        new_reserved = stock.reserved - reservation.quantity
        new_committed = stock.committed + reservation.quantity
        self.repo.update_stock(
            reservation.sku_id, reserved=new_reserved, committed=new_committed
        )

        # Create order
        reservation = self.repo.update_reservation(
            reservation_id,
            ReservationState.CONFIRMED,
            confirmed_at=datetime.now(timezone.utc),
        )
        order = self.repo.create_order(
            reservation_id, reservation.sku_id, reservation.quantity, ReservationState.CONFIRMED
        )

        return {
            "id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": float(reservation.quantity),
            "state": reservation.state,
            "created_at": reservation.created_at.isoformat(),
        }

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.state != ReservationState.PENDING:
            raise InvalidStateTransitionError(
                f"Cannot cancel reservation in state {reservation.state}"
            )

        # Release reserved stock back to available
        stock = self.repo.get_stock(reservation.sku_id)
        new_available = stock.available + reservation.quantity
        new_reserved = stock.reserved - reservation.quantity
        self.repo.update_stock(
            reservation.sku_id, available=new_available, reserved=new_reserved
        )

        reservation = self.repo.update_reservation(
            reservation_id,
            ReservationState.CANCELLED,
            cancelled_at=datetime.now(timezone.utc),
        )

        return {
            "id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": float(reservation.quantity),
            "state": reservation.state,
            "created_at": reservation.created_at.isoformat(),
        }

    def list_orders(self, limit: int = 10, offset: int = 0) -> dict:
        orders, total = self.repo.list_orders(limit=limit, offset=offset)
        return {
            "items": [
                {
                    "id": o.id,
                    "reservation_id": o.reservation_id,
                    "sku_id": o.sku_id,
                    "quantity": float(o.quantity),
                    "state": o.state,
                    "created_at": o.created_at.isoformat(),
                }
                for o in orders
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def _is_expired(self, reservation) -> bool:
        if not reservation.expires_at:
            return False
        expires = reservation.expires_at
        # Handle both naive and timezone-aware datetimes
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > expires
