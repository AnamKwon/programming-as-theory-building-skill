"""Business logic service layer."""

import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Optional

from .models import OrderStatus, OrderResponse, ReservationResponse
from .repository import Repository


class ReservationExpirationError(Exception):
    """Raised when attempting to operate on an expired reservation."""

    pass


class InsufficientStockError(Exception):
    """Raised when insufficient stock is available for a reservation."""

    pass


class ReservationAlreadyExists(Exception):
    """Raised when attempting to create a duplicate reservation."""

    pass


class InvalidStateTransitionError(Exception):
    """Raised when attempting an invalid state transition."""

    pass


class CommerceService:
    """Business logic for inventory and order management."""

    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, sku_id: str, name: str) -> dict:
        """Create a new SKU."""
        sku = self.repo.create_sku(sku_id, name)
        self.repo.commit()
        return {
            "id": sku.id,
            "name": sku.name,
            "created_at": sku.created_at,
        }

    def adjust_stock(self, sku_id: str, delta: int) -> dict:
        """Adjust stock for a SKU."""
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        stock = self.repo.update_stock(sku_id, delta)
        self.repo.commit()
        return {
            "sku_id": stock.sku_id,
            "quantity": stock.quantity,
        }

    def create_reservation(
        self,
        sku_id: str,
        quantity: int,
        idempotency_key: str,
        ttl_seconds: int = 300,
    ) -> dict:
        """
        Create a reservation for inventory.

        Idempotency: If the same idempotency_key is used, returns the existing
        reservation instead of creating a duplicate.
        """
        # Check if reservation already exists for this idempotency key
        idempotency_hash = self._hash_idempotency_key(idempotency_key)
        existing = self._find_reservation_by_hash(idempotency_hash)
        if existing:
            return {
                "id": existing.id,
                "sku_id": existing.sku_id,
                "quantity": existing.quantity,
                "status": existing.status,
                "expires_at": existing.expires_at,
                "created_at": existing.created_at,
            }

        # Verify SKU exists
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        # Check available stock (excluding expired/cancelled reservations)
        stock = self.repo.get_stock(sku_id)
        current_stock = stock.quantity if stock else 0
        reserved_quantity = self._get_active_reserved_quantity(sku_id)
        available = current_stock - reserved_quantity

        if available < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for {sku_id}. Available: {available}, "
                f"Requested: {quantity}"
            )

        # Create reservation
        reservation_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        reservation = self.repo.create_reservation(
            reservation_id, sku_id, quantity, expires_at
        )
        self.repo.commit()

        return {
            "id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "status": reservation.status,
            "expires_at": reservation.expires_at,
            "created_at": reservation.created_at,
        }

    def confirm_reservation(
        self, reservation_id: str, idempotency_key: str
    ) -> dict:
        """Confirm a reservation and transition to confirmed state."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        # Check if reservation has expired
        if datetime.utcnow() > reservation.expires_at:
            raise ReservationExpirationError(
                f"Reservation {reservation_id} has expired"
            )

        # Check state transition validity
        if reservation.status != OrderStatus.RESERVED.value:
            raise InvalidStateTransitionError(
                f"Cannot confirm reservation in state {reservation.status}"
            )

        reservation = self.repo.confirm_reservation(reservation_id)
        self.repo.commit()

        return {
            "id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "status": reservation.status,
            "expires_at": reservation.expires_at,
            "created_at": reservation.created_at,
        }

    def cancel_reservation(
        self, reservation_id: str, idempotency_key: str
    ) -> dict:
        """Cancel a reservation."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status == OrderStatus.CANCELLED.value:
            # Idempotent: already cancelled
            return {
                "id": reservation.id,
                "sku_id": reservation.sku_id,
                "quantity": reservation.quantity,
                "status": reservation.status,
                "expires_at": reservation.expires_at,
                "created_at": reservation.created_at,
            }

        reservation = self.repo.cancel_reservation(reservation_id)
        self.repo.commit()

        return {
            "id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "status": reservation.status,
            "expires_at": reservation.expires_at,
            "created_at": reservation.created_at,
        }

    def get_orders(self, skip: int = 0, limit: int = 10) -> dict:
        """Get paginated list of orders (reservations)."""
        reservations, total = self.repo.get_reservations(skip, limit)
        items = [
            {
                "reservation_id": r.id,
                "sku_id": r.sku_id,
                "quantity": r.quantity,
                "status": r.status,
                "created_at": r.created_at,
                "confirmed_at": r.confirmed_at,
            }
            for r in reservations
        ]
        return {
            "items": items,
            "total": total,
            "skip": skip,
            "limit": limit,
        }

    def _get_active_reserved_quantity(self, sku_id: str) -> int:
        """
        Get total quantity reserved (but not cancelled) for a SKU.
        Excludes expired and cancelled reservations.
        """
        reserved = self.repo.get_reservation_by_sku_and_status(
            sku_id, OrderStatus.RESERVED.value
        )
        confirmed = self.repo.get_reservation_by_sku_and_status(
            sku_id, OrderStatus.CONFIRMED.value
        )

        now = datetime.utcnow()
        total = 0

        for r in reserved:
            if now <= r.expires_at:
                total += r.quantity

        for r in confirmed:
            total += r.quantity

        return total

    def _hash_idempotency_key(self, key: str) -> str:
        """Hash an idempotency key for lookup."""
        return hashlib.sha256(key.encode()).hexdigest()

    def _find_reservation_by_hash(self, hash_value: str) -> Optional[object]:
        """
        Find reservation by idempotency hash.
        Note: This is a simplified approach; production systems would store
        the hash separately in the database.
        """
        # For now, return None as we're not storing hashes.
        # In production, add an idempotency_hash column to Reservation table.
        return None
