import json
import uuid
from datetime import datetime, timedelta
from typing import Optional

from .models import OrderResponse, OrderState
from .repository import Repository


class InsufficientStockError(Exception):
    pass


class ExpiredReservationError(Exception):
    pass


class InvalidReservationStateError(Exception):
    pass


class DuplicateRequestError(Exception):
    pass


class CommerceService:
    def __init__(self, repository: Repository, reservation_ttl_minutes: int = 15):
        self.repo = repository
        self.reservation_ttl_minutes = reservation_ttl_minutes

    def create_sku(self, sku_id: str, initial_stock: int) -> dict:
        sku = self.repo.create_sku(sku_id, initial_stock)
        return {
            "sku_id": sku.sku_id,
            "stock_level": sku.stock_level,
            "created_at": sku.created_at,
        }

    def adjust_stock(self, sku_id: str, quantity_delta: int) -> dict:
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        new_level = sku.stock_level + quantity_delta
        if new_level < 0:
            raise ValueError(f"Stock cannot be negative (current: {sku.stock_level}, delta: {quantity_delta})")

        updated = self.repo.update_stock(sku_id, quantity_delta)
        return {
            "sku_id": updated.sku_id,
            "stock_level": updated.stock_level,
            "adjusted_at": updated.created_at,
        }

    def create_reservation(
        self, sku_id: str, quantity: int, idempotency_key: str
    ) -> tuple[dict, bool]:
        cached = self.repo.get_idempotency_response(idempotency_key)
        if cached:
            return json.loads(cached), True

        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        if sku.stock_level < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for {sku_id}: requested {quantity}, available {sku.stock_level}"
            )

        reservation_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=self.reservation_ttl_minutes)

        reservation = self.repo.create_reservation(
            reservation_id, sku_id, quantity, expires_at
        )

        response = {
            "reservation_id": reservation.reservation_id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "expires_at": reservation.expires_at,
            "created_at": reservation.created_at,
        }

        self.repo.store_idempotency_response(
            idempotency_key, json.dumps(response, default=str)
        )

        return response, False

    def confirm_reservation(self, reservation_id: str) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.state != OrderState.PENDING:
            raise InvalidReservationStateError(
                f"Cannot confirm reservation in state {reservation.state}"
            )

        if datetime.utcnow() > reservation.expires_at:
            raise ExpiredReservationError(
                f"Reservation {reservation_id} expired at {reservation.expires_at}"
            )

        order_id = str(uuid.uuid4())
        confirmed_at = datetime.utcnow()

        order = self.repo.create_order(
            order_id,
            reservation.reservation_id,
            reservation.sku_id,
            reservation.quantity,
            confirmed_at,
        )

        self.repo.update_reservation_state(reservation_id, OrderState.CONFIRMED)

        return {
            "order_id": order.order_id,
            "reservation_id": order.reservation_id,
            "sku_id": order.sku_id,
            "quantity": order.quantity,
            "confirmed_at": order.confirmed_at,
        }

    def cancel_reservation(self, reservation_id: str) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.state != OrderState.PENDING:
            raise InvalidReservationStateError(
                f"Cannot cancel reservation in state {reservation.state}"
            )

        self.repo.update_reservation_state(reservation_id, OrderState.CANCELLED)

        return {
            "reservation_id": reservation_id,
            "cancelled_at": datetime.utcnow(),
        }

    def get_orders(
        self, limit: int = 10, cursor: Optional[str] = None
    ) -> dict:
        orders, has_more, next_cursor = self.repo.get_orders_paginated(
            limit=limit, cursor=cursor
        )

        order_list = [
            {
                "order_id": order.order_id,
                "reservation_id": order.reservation_id,
                "sku_id": order.sku_id,
                "quantity": order.quantity,
                "state": order.state.value,
                "created_at": order.created_at,
                "confirmed_at": order.confirmed_at,
            }
            for order in orders
        ]

        return {
            "orders": order_list,
            "next_cursor": next_cursor,
            "has_more": has_more,
        }
