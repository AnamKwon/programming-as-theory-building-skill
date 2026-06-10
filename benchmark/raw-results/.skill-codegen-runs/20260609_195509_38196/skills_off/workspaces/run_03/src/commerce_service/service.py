from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from .models import OrderState, ReservationState
from .repository import Repository


class ServiceError(Exception):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


class Commerce:
    def __init__(self, session: Session, reservation_ttl_minutes: int = 15):
        self.repo = Repository(session)
        self.reservation_ttl = timedelta(minutes=reservation_ttl_minutes)

    def create_sku(self, name: str, initial_stock: int = 0) -> dict:
        existing = self.repo.get_sku_by_name(name)
        if existing:
            raise ServiceError("SKU with this name already exists", "SKU_EXISTS")

        sku = self.repo.create_sku(name, initial_stock)
        return {
            "id": sku.id,
            "name": sku.name,
            "stock": sku.stock,
            "created_at": sku.created_at,
        }

    def adjust_stock(self, sku_id: int, quantity_delta: int) -> dict:
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ServiceError("SKU not found", "SKU_NOT_FOUND")

        if sku.stock + quantity_delta < 0:
            raise ServiceError("Insufficient stock for adjustment", "INSUFFICIENT_STOCK")

        updated_sku = self.repo.adjust_stock(sku_id, quantity_delta)
        return {
            "id": updated_sku.id,
            "name": updated_sku.name,
            "stock": updated_sku.stock,
            "created_at": updated_sku.created_at,
        }

    def create_reservation(
        self, sku_id: int, quantity: int, idempotency_key: str
    ) -> dict:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing.state == ReservationState.CANCELLED.value:
                raise ServiceError(
                    "Idempotency key was previously cancelled", "KEY_ALREADY_USED"
                )
            return self._reservation_to_dict(existing)

        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ServiceError("SKU not found", "SKU_NOT_FOUND")

        if sku.stock < quantity:
            raise ServiceError("Insufficient stock", "INSUFFICIENT_STOCK")

        expires_at = datetime.now(timezone.utc) + self.reservation_ttl
        reservation = self.repo.create_reservation(
            sku_id, quantity, idempotency_key, expires_at
        )

        self.repo.adjust_stock(sku_id, -quantity)

        return self._reservation_to_dict(reservation)

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ServiceError("Reservation not found", "RESERVATION_NOT_FOUND")

        if reservation.state == ReservationState.CONFIRMED.value:
            return self._reservation_to_dict(reservation)

        if reservation.state != ReservationState.PENDING.value:
            raise ServiceError(
                f"Cannot confirm reservation in {reservation.state} state",
                "INVALID_STATE",
            )

        if datetime.now(timezone.utc) > reservation.expires_at:
            self.repo.update_reservation_state(
                reservation_id, ReservationState.EXPIRED
            )
            raise ServiceError("Reservation has expired", "RESERVATION_EXPIRED")

        updated = self.repo.update_reservation_state(
            reservation_id, ReservationState.CONFIRMED
        )

        order = self.repo.create_order(
            reservation_id, reservation.sku_id, reservation.quantity
        )

        return self._reservation_to_dict(updated)

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ServiceError("Reservation not found", "RESERVATION_NOT_FOUND")

        if reservation.state == ReservationState.CANCELLED.value:
            return self._reservation_to_dict(reservation)

        if reservation.state == ReservationState.CONFIRMED.value:
            raise ServiceError("Cannot cancel confirmed reservation", "INVALID_STATE")

        updated = self.repo.update_reservation_state(
            reservation_id, ReservationState.CANCELLED
        )

        self.repo.adjust_stock(reservation.sku_id, reservation.quantity)

        return self._reservation_to_dict(updated)

    def get_orders(self, limit: int = 10, cursor: Optional[int] = None) -> dict:
        orders, next_cursor = self.repo.get_orders_paginated(limit, cursor)
        return {
            "items": [self._order_to_dict(o) for o in orders],
            "next_cursor": next_cursor,
        }

    def _reservation_to_dict(self, reservation) -> dict:
        return {
            "id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "state": reservation.state,
            "expires_at": reservation.expires_at,
            "created_at": reservation.created_at,
        }

    def _order_to_dict(self, order) -> dict:
        return {
            "id": order.id,
            "reservation_id": order.reservation_id,
            "sku_id": order.sku_id,
            "quantity": order.quantity,
            "state": order.state,
            "created_at": order.created_at,
        }
