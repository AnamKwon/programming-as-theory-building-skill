from datetime import datetime
from typing import Optional

from .models import (
    OrderListResponse,
    OrderResponse,
    ReservationResponse,
    SKUResponse,
    StockAdjustResponse,
)
from .repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class ReservationNotPendingError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class SKUNotFoundError(Exception):
    pass


class DuplicateIdempotencyKeyError(Exception):
    pass


class Service:
    EXPIRATION_SECONDS = 300

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> SKUResponse:
        sku_id = self.repo.create_sku(sku, initial_stock)
        sku_data = self.repo.get_sku_by_id(sku_id)
        if not sku_data:
            raise RuntimeError("Failed to retrieve created SKU")
        return SKUResponse(
            id=sku_data["id"],
            sku=sku_data["sku"],
            available_stock=sku_data["available_stock"],
            created_at=datetime.fromisoformat(sku_data["created_at"]),
        )

    def adjust_stock(self, sku: str, amount: int) -> StockAdjustResponse:
        sku_data = self.repo.get_sku_by_name(sku)
        if not sku_data:
            raise SKUNotFoundError(f"SKU not found: {sku}")

        previous_stock = sku_data["available_stock"]
        new_stock = previous_stock + amount

        self.repo.update_sku_stock(sku_data["id"], new_stock)

        return StockAdjustResponse(
            sku=sku,
            previous_stock=previous_stock,
            adjusted_amount=amount,
            new_stock=new_stock,
        )

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> ReservationResponse:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            raise DuplicateIdempotencyKeyError(
                f"Idempotency key already exists: {idempotency_key}"
            )

        sku_data = self.repo.get_sku_by_name(sku)
        if not sku_data:
            raise SKUNotFoundError(f"SKU not found: {sku}")

        if sku_data["available_stock"] < quantity:
            raise InsufficientStockError("Insufficient stock")

        reservation_id = self.repo.create_reservation(sku_data["id"], quantity, idempotency_key)
        new_stock = sku_data["available_stock"] - quantity
        self.repo.update_sku_stock(sku_data["id"], new_stock)

        reservation_data = self.repo.get_reservation_by_id(reservation_id)
        if not reservation_data:
            raise RuntimeError("Failed to retrieve created reservation")

        return self._reservation_to_response(reservation_data)

    def confirm_reservation(self, reservation_id: int) -> ReservationResponse:
        reservation_data = self.repo.get_reservation_by_id(reservation_id)
        if not reservation_data:
            raise ReservationNotFoundError(f"Reservation not found: {reservation_id}")

        if reservation_data["status"] != "PENDING":
            raise ReservationNotPendingError(
                f"Reservation is not PENDING: {reservation_data['status']}"
            )

        created_at = datetime.fromisoformat(reservation_data["created_at"])
        now = datetime.utcnow()
        elapsed = (now - created_at).total_seconds()

        if elapsed > self.EXPIRATION_SECONDS:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            sku_data = self.repo.get_sku_by_name(reservation_data["sku"])
            if sku_data:
                current_stock = sku_data["available_stock"]
                new_stock = current_stock + reservation_data["quantity"]
                self.repo.update_sku_stock(sku_data["id"], new_stock)
            raise ReservationExpiredError("Reservation has expired")

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        self.repo.create_order(reservation_id)

        reservation_data = self.repo.get_reservation_by_id(reservation_id)
        if not reservation_data:
            raise RuntimeError("Failed to retrieve updated reservation")

        return self._reservation_to_response(reservation_data)

    def cancel_reservation(self, reservation_id: int) -> ReservationResponse:
        reservation_data = self.repo.get_reservation_by_id(reservation_id)
        if not reservation_data:
            raise ReservationNotFoundError(f"Reservation not found: {reservation_id}")

        if reservation_data["status"] != "PENDING":
            raise ReservationNotPendingError(
                f"Reservation is not PENDING: {reservation_data['status']}"
            )

        self.repo.update_reservation_status(reservation_id, "CANCELLED")

        sku_data = self.repo.get_sku_by_name(reservation_data["sku"])
        if sku_data:
            current_stock = sku_data["available_stock"]
            new_stock = current_stock + reservation_data["quantity"]
            self.repo.update_sku_stock(sku_data["id"], new_stock)

        reservation_data = self.repo.get_reservation_by_id(reservation_id)
        if not reservation_data:
            raise RuntimeError("Failed to retrieve updated reservation")

        return self._reservation_to_response(reservation_data)

    def get_orders(self, page: int = 1, size: int = 10) -> OrderListResponse:
        if page < 1:
            page = 1
        if size < 1:
            size = 10

        orders, total = self.repo.get_orders_paginated(page, size)
        order_responses = [
            OrderResponse(
                id=order["id"],
                reservation_id=order["reservation_id"],
                created_at=datetime.fromisoformat(order["created_at"]),
            )
            for order in orders
        ]

        return OrderListResponse(
            page=page,
            size=size,
            total=total,
            orders=order_responses,
        )

    def _reservation_to_response(self, data: dict) -> ReservationResponse:
        return ReservationResponse(
            id=data["id"],
            sku=data["sku"],
            quantity=data["quantity"],
            status=data["status"],
            idempotency_key=data["idempotency_key"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )
