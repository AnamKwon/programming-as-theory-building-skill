from datetime import datetime, timedelta, timezone
from typing import Optional

from commerce_service.models import OrderStatus, ReservationStatus
from commerce_service.repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class InvalidStateTransitionError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class SKUNotFoundError(Exception):
    pass


class Service:
    @staticmethod
    def create_sku(code: str, name: str, initial_stock: int) -> dict:
        sku_id = Repository.create_sku(code, name, initial_stock)
        return Repository.get_sku(sku_id)

    @staticmethod
    def adjust_stock(sku_id: int, quantity: int) -> dict:
        sku = Repository.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        if sku["current_stock"] + quantity < 0:
            raise InsufficientStockError(
                f"Cannot reduce stock below 0. Current: {sku['current_stock']}, adjustment: {quantity}"
            )

        Repository.adjust_stock(sku_id, quantity)
        return Repository.get_sku(sku_id)

    @staticmethod
    def create_reservation(
        sku_id: int, quantity: int, idempotency_key: str, ttl_seconds: int
    ) -> dict:
        existing = Repository.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        sku = Repository.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        if sku["current_stock"] < quantity:
            raise InsufficientStockError(
                f"Insufficient stock. Available: {sku['current_stock']}, requested: {quantity}"
            )

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expires_at = now + timedelta(seconds=ttl_seconds)

        reservation_id = Repository.create_reservation(
            sku_id, quantity, idempotency_key, now, expires_at
        )
        return Repository.get_reservation(reservation_id)

    @staticmethod
    def confirm_reservation(reservation_id: int) -> tuple[dict, int]:
        reservation = Repository.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation["status"] != ReservationStatus.PENDING.value:
            raise InvalidStateTransitionError(
                f"Cannot confirm reservation in {reservation['status']} state"
            )

        expires_at = datetime.fromisoformat(reservation["expires_at"])
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if now > expires_at:
            Repository.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
            raise ReservationExpiredError("Reservation has expired")

        sku = Repository.get_sku(reservation["sku_id"])
        if sku["current_stock"] < reservation["quantity"]:
            raise InsufficientStockError(
                f"Insufficient stock for confirmation. Available: {sku['current_stock']}, needed: {reservation['quantity']}"
            )

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        Repository.update_reservation_status(
            reservation_id, ReservationStatus.CONFIRMED, confirmed_at=now
        )
        Repository.adjust_stock(reservation["sku_id"], -reservation["quantity"])

        order_id = Repository.create_order(
            reservation_id, reservation["sku_id"], reservation["quantity"], now
        )
        Repository.update_order_status(order_id, OrderStatus.CONFIRMED, confirmed_at=now)

        updated_reservation = Repository.get_reservation(reservation_id)
        return updated_reservation, order_id

    @staticmethod
    def cancel_reservation(reservation_id: int) -> dict:
        reservation = Repository.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation["status"] not in (
            ReservationStatus.PENDING.value,
            ReservationStatus.CONFIRMED.value,
        ):
            raise InvalidStateTransitionError(
                f"Cannot cancel reservation in {reservation['status']} state"
            )

        Repository.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)

        if reservation["status"] == ReservationStatus.CONFIRMED.value:
            Repository.adjust_stock(reservation["sku_id"], reservation["quantity"])

        return Repository.get_reservation(reservation_id)

    @staticmethod
    def get_order(order_id: int) -> dict:
        order = Repository.get_order(order_id)
        if not order:
            raise Exception(f"Order {order_id} not found")
        return order

    @staticmethod
    def list_orders(offset: int = 0, limit: int = 20) -> tuple[list[dict], int]:
        return Repository.list_orders(offset, limit)
