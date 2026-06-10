import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from .models import (
    OrderResponse,
    OrderStatus,
    ReservationResponse,
    ReservationStatus,
    SKUResponse,
)
from .repository import Repository

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class InvalidStateTransitionError(Exception):
    pass


class SKUNotFoundError(Exception):
    pass


class Service:
    RESERVATION_TTL_HOURS = 24

    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, sku_id: str, name: str, total_stock: int) -> SKUResponse:
        self.repo.create_sku(sku_id, name, total_stock)
        return self._get_sku_response(sku_id)

    def adjust_stock(self, sku_id: str, quantity_change: int) -> SKUResponse:
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")
        self.repo.adjust_stock(sku_id, quantity_change)
        return self._get_sku_response(sku_id)

    def create_reservation(
        self, sku_id: str, quantity: int, idempotency_key: Optional[str] = None
    ) -> ReservationResponse:
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        if idempotency_key:
            existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
            if existing:
                return self._reservation_row_to_response(existing)

        reserved = self.repo.get_reserved_stock(sku_id)
        available = sku["total_stock"] - reserved

        if quantity > available:
            raise InsufficientStockError(
                f"Requested {quantity}, but only {available} available"
            )

        reservation_id = str(uuid.uuid4())
        expires_at = utc_now() + timedelta(hours=self.RESERVATION_TTL_HOURS)

        self.repo.create_reservation(
            reservation_id, sku_id, quantity, expires_at, idempotency_key
        )

        return self._get_reservation_response(reservation_id)

    def confirm_reservation(self, reservation_id: str) -> ReservationResponse:
        self.repo.expire_reservations()

        res = self.repo.get_reservation(reservation_id)
        if not res:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if res["status"] == ReservationStatus.EXPIRED.value:
            raise ReservationExpiredError(f"Reservation {reservation_id} has expired")

        if res["status"] != ReservationStatus.PENDING.value:
            raise InvalidStateTransitionError(
                f"Cannot confirm reservation in {res['status']} state"
            )

        self.repo.confirm_reservation(reservation_id)
        return self._get_reservation_response(reservation_id)

    def cancel_reservation(self, reservation_id: str) -> ReservationResponse:
        res = self.repo.get_reservation(reservation_id)
        if not res:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if res["status"] not in (
            ReservationStatus.PENDING.value,
            ReservationStatus.CONFIRMED.value,
        ):
            raise InvalidStateTransitionError(
                f"Cannot cancel reservation in {res['status']} state"
            )

        self.repo.cancel_reservation(reservation_id)
        return self._get_reservation_response(reservation_id)

    def get_orders(self, offset: int = 0, limit: int = 10) -> tuple[list[OrderResponse], int]:
        orders, total = self.repo.list_orders(offset, limit)
        responses = []
        for order in orders:
            res_ids = self.repo.get_order_reservations(order["order_id"])
            responses.append(
                OrderResponse(
                    order_id=order["order_id"],
                    reservation_ids=res_ids,
                    status=OrderStatus(order["status"]),
                    created_at=datetime.fromisoformat(order["created_at"]),
                )
            )
        return responses, total

    def _get_sku_response(self, sku_id: str) -> SKUResponse:
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise SKUNotFoundError(f"SKU {sku_id} not found")

        reserved = self.repo.get_reserved_stock(sku_id)
        return SKUResponse(
            sku_id=sku["sku_id"],
            name=sku["name"],
            total_stock=sku["total_stock"],
            available_stock=sku["total_stock"] - reserved,
            reserved_stock=reserved,
            created_at=datetime.fromisoformat(sku["created_at"]),
        )

    def _get_reservation_response(self, reservation_id: str) -> ReservationResponse:
        res = self.repo.get_reservation(reservation_id)
        if not res:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")
        return self._reservation_row_to_response(res)

    def _reservation_row_to_response(self, row: dict) -> ReservationResponse:
        return ReservationResponse(
            reservation_id=row["reservation_id"],
            sku_id=row["sku_id"],
            quantity=row["quantity"],
            status=ReservationStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
            confirmed_at=datetime.fromisoformat(row["confirmed_at"])
            if row["confirmed_at"]
            else None,
            cancelled_at=datetime.fromisoformat(row["cancelled_at"])
            if row["cancelled_at"]
            else None,
        )
