import uuid
from datetime import datetime, timedelta
from typing import Optional

from .models import ReservationResponse, ReservationState, SKUResponse
from .repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class InvalidStateTransitionError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class CommerceService:
    RESERVATION_TTL_MINUTES = 15

    def __init__(self, repository: Repository):
        self.repo = repository

    # ========================================================================
    # SKU Management
    # ========================================================================

    def create_sku(self, sku_id: str, name: str, initial_stock: int) -> SKUResponse:
        sku = self.repo.create_sku(sku_id, name, initial_stock)
        return SKUResponse(
            id=sku.id,
            name=sku.name,
            available_stock=sku.available_stock,
            reserved_stock=sku.reserved_stock,
            created_at=sku.created_at,
        )

    def adjust_stock(self, sku_id: str, quantity: int) -> SKUResponse:
        sku = self.repo.update_sku_stock(sku_id, quantity)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        return SKUResponse(
            id=sku.id,
            name=sku.name,
            available_stock=sku.available_stock,
            reserved_stock=sku.reserved_stock,
            created_at=sku.created_at,
        )

    # ========================================================================
    # Reservation Management
    # ========================================================================

    def reserve(self, sku_id: str, quantity: int, idempotency_key: Optional[str] = None) -> ReservationResponse:
        if idempotency_key:
            existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
            if existing:
                return self._reservation_to_response(existing)

        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        if sku.available_stock < quantity:
            raise InsufficientStockError(f"Not enough stock for {sku_id}: need {quantity}, have {sku.available_stock}")

        self.repo.update_sku_stock(sku_id, -quantity, quantity)

        reservation_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=self.RESERVATION_TTL_MINUTES)

        reservation = self.repo.create_reservation(
            reservation_id, sku_id, quantity, expires_at, idempotency_key=idempotency_key
        )

        return self._reservation_to_response(reservation)

    def confirm_reservation(self, reservation_id: str) -> ReservationResponse:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.state != ReservationState.RESERVED:
            raise InvalidStateTransitionError(
                f"Cannot confirm reservation in state {reservation.state}; must be {ReservationState.RESERVED}"
            )

        if reservation.expires_at and reservation.expires_at < datetime.utcnow():
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        updated = self.repo.update_reservation_state(reservation_id, ReservationState.CONFIRMED)
        return self._reservation_to_response(updated)

    def cancel_reservation(self, reservation_id: str) -> ReservationResponse:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.state == ReservationState.CANCELLED:
            return self._reservation_to_response(reservation)

        if reservation.state == ReservationState.CONFIRMED:
            raise InvalidStateTransitionError(
                f"Cannot cancel a confirmed reservation {reservation_id}"
            )

        if reservation.state == ReservationState.RESERVED:
            self.repo.update_sku_stock(reservation.sku_id, reservation.quantity, -reservation.quantity)

        updated = self.repo.update_reservation_state(reservation_id, ReservationState.CANCELLED)
        return self._reservation_to_response(updated)

    def get_reservation(self, reservation_id: str) -> ReservationResponse:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")
        return self._reservation_to_response(reservation)

    def cleanup_expired_reservations(self) -> int:
        expired = self.repo.get_expired_reservations()
        count = 0
        for reservation in expired:
            self.repo.update_sku_stock(
                reservation.sku_id, reservation.quantity, -reservation.quantity
            )
            self.repo.update_reservation_state(reservation.id, ReservationState.CANCELLED)
            count += 1
        return count

    # ========================================================================
    # Helpers
    # ========================================================================

    def _reservation_to_response(self, reservation) -> ReservationResponse:
        return ReservationResponse(
            id=reservation.id,
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            state=reservation.state,
            created_at=reservation.created_at,
            expires_at=reservation.expires_at,
            confirmed_at=reservation.confirmed_at,
        )
