"""Business logic layer."""

from datetime import datetime
from typing import Optional

from .models import OrderStatus, ReservationStatus
from .repository import Repository


class InsufficientStockError(Exception):
    """Raised when there is not enough stock to fulfill a request."""

    pass


class ReservationNotFoundError(Exception):
    """Raised when a reservation cannot be found."""

    pass


class ReservationExpiredError(Exception):
    """Raised when a reservation has expired."""

    pass


class InvalidStateTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    pass


class IdempotencyKeyExistsError(Exception):
    """Raised when an idempotency key is already in use."""

    pass


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, name: str, quantity: int) -> dict:
        """Create a new SKU."""
        sku_id = self.repo.create_sku(name, quantity)
        return {"id": sku_id, "name": name, "quantity": quantity}

    def get_sku(self, sku_id: int) -> Optional[dict]:
        """Get SKU by ID."""
        return self.repo.get_sku(sku_id)

    def adjust_stock(self, sku_id: int, delta: int) -> dict:
        """Adjust stock level."""
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        if not self.repo.adjust_stock(sku_id, delta):
            raise ValueError(
                f"Cannot adjust stock to {sku['quantity'] + delta} (would be negative)"
            )

        updated = self.repo.get_sku(sku_id)
        return updated

    def create_reservation(
        self, sku_id: int, quantity: int, idempotency_key: str
    ) -> dict:
        """
        Create a reservation for inventory.

        Idempotency: if the key already exists, return the existing reservation.
        """
        # Check idempotency
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return self._format_reservation(existing)

        # Check stock availability
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        if sku["quantity"] < quantity:
            raise InsufficientStockError(
                f"Insufficient stock: need {quantity}, have {sku['quantity']}"
            )

        # Reserve stock
        reservation_id = self.repo.create_reservation(
            sku_id, quantity, idempotency_key
        )
        self.repo.adjust_stock(sku_id, -quantity)

        reservation = self.repo.get_reservation(reservation_id)
        return self._format_reservation(reservation)

    def get_reservation(self, reservation_id: int) -> dict:
        """Get reservation by ID."""
        res = self.repo.get_reservation(reservation_id)
        if not res:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")
        return self._format_reservation(res)

    def confirm_reservation(self, reservation_id: int) -> dict:
        """Confirm a pending reservation, converting it to an order."""
        res = self.repo.get_reservation(reservation_id)
        if not res:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        # Check expiration
        if self._is_expired(res["expires_at"]):
            # Auto-cancel expired reservation and return stock
            self.repo.update_reservation_status(
                reservation_id, ReservationStatus.CANCELLED
            )
            self.repo.adjust_stock(res["sku_id"], res["quantity"])
            raise ReservationExpiredError(
                f"Reservation {reservation_id} has expired"
            )

        # Check status
        status = ReservationStatus(res["status"])
        if status != ReservationStatus.PENDING:
            raise InvalidStateTransitionError(
                f"Cannot confirm {status.value} reservation"
            )

        # Confirm reservation and create order
        self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)
        order_id = self.repo.create_order(
            res["sku_id"],
            res["quantity"],
            OrderStatus.CONFIRMED,
            reservation_id=reservation_id,
        )

        return {
            "reservation_id": reservation_id,
            "order_id": order_id,
            "status": ReservationStatus.CONFIRMED.value,
        }

    def cancel_reservation(self, reservation_id: int) -> dict:
        """Cancel a reservation and return stock."""
        res = self.repo.get_reservation(reservation_id)
        if not res:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        status = ReservationStatus(res["status"])
        if status == ReservationStatus.CANCELLED:
            # Idempotent: return success for already-cancelled
            return {
                "reservation_id": reservation_id,
                "status": ReservationStatus.CANCELLED.value,
            }

        if status not in (ReservationStatus.PENDING, ReservationStatus.CONFIRMED):
            raise InvalidStateTransitionError(
                f"Cannot cancel {status.value} reservation"
            )

        # Cancel and restore stock
        self.repo.update_reservation_status(
            reservation_id, ReservationStatus.CANCELLED
        )
        self.repo.adjust_stock(res["sku_id"], res["quantity"])

        return {
            "reservation_id": reservation_id,
            "status": ReservationStatus.CANCELLED.value,
        }

    def get_order(self, order_id: int) -> dict:
        """Get order by ID."""
        order = self.repo.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        return self._format_order(order)

    def list_orders(self, offset: int = 0, limit: int = 20) -> dict:
        """List orders with pagination."""
        orders, total = self.repo.list_orders(offset, limit)
        return {
            "items": [self._format_order(o) for o in orders],
            "total": total,
            "offset": offset,
            "limit": limit,
        }

    def cleanup_expired_reservations(self) -> int:
        """Find and auto-cancel expired pending reservations. Returns count."""
        expired = self.repo.get_expired_reservations()
        for res in expired:
            self.repo.update_reservation_status(
                res["id"], ReservationStatus.CANCELLED
            )
            self.repo.adjust_stock(res["sku_id"], res["quantity"])
        return len(expired)

    @staticmethod
    def _is_expired(expires_at_str: str) -> bool:
        """Check if a datetime string is in the past."""
        expires_at = datetime.fromisoformat(expires_at_str)
        return expires_at < datetime.utcnow()

    @staticmethod
    def _format_reservation(row: dict) -> dict:
        """Format a reservation row for response."""
        return {
            "id": row["id"],
            "sku_id": row["sku_id"],
            "quantity": row["quantity"],
            "status": row["status"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
        }

    @staticmethod
    def _format_order(row: dict) -> dict:
        """Format an order row for response."""
        return {
            "id": row["id"],
            "sku_id": row["sku_id"],
            "quantity": row["quantity"],
            "status": row["status"],
            "created_at": row["created_at"],
        }
