from datetime import datetime, timezone
from typing import Optional, Tuple

from .models import OrderResponse, ReservationResponse, StockAdjustResponse
from .repository import Repository


class CommerceService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        sku_model = self.repo.create_sku(sku, initial_stock)
        return {"sku": sku_model.sku, "available_stock": sku_model.available_stock}

    def adjust_stock(self, sku: str, amount: int) -> StockAdjustResponse:
        sku_model = self.repo.adjust_stock(sku, amount)
        if not sku_model:
            raise ValueError(f"SKU {sku} not found")
        return StockAdjustResponse(sku=sku_model.sku, available_stock=sku_model.available_stock)

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> ReservationResponse:
        existing_reservation = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing_reservation:
            return self._format_reservation(existing_reservation)

        sku_model = self.repo.get_sku(sku)
        if not sku_model:
            raise ValueError(f"SKU {sku} not found")

        if sku_model.available_stock < quantity:
            raise InsufficientStockError(f"Insufficient stock for SKU {sku}")

        self.repo.adjust_stock(sku, -quantity)

        reservation = self.repo.create_reservation(sku, quantity, idempotency_key)
        return self._format_reservation(reservation)

    def confirm_reservation(self, reservation_id: int) -> Tuple[ReservationResponse, OrderResponse]:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != "PENDING":
            raise InvalidStateError(f"Reservation is not PENDING, current status: {reservation.status}")

        now = datetime.now(timezone.utc)
        created_at = reservation.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        age_seconds = (now - created_at).total_seconds()
        if age_seconds > 300:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.adjust_stock(reservation.sku, reservation.quantity)
            raise ReservationExpiredError("Reservation expired")

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        order = self.repo.create_order(reservation_id, reservation.sku, reservation.quantity)

        return (
            self._format_reservation(self.repo.get_reservation(reservation_id)),
            self._format_order(order),
        )

    def cancel_reservation(self, reservation_id: int) -> ReservationResponse:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != "PENDING":
            raise InvalidStateError(f"Reservation is not PENDING, current status: {reservation.status}")

        self.repo.adjust_stock(reservation.sku, reservation.quantity)
        self.repo.update_reservation_status(reservation_id, "CANCELLED")

        return self._format_reservation(self.repo.get_reservation(reservation_id))

    def get_orders(self, page: int = 1, size: int = 10) -> Tuple[list[OrderResponse], int]:
        orders, total = self.repo.get_orders(page, size)
        return [self._format_order(order) for order in orders], total

    def _format_reservation(self, reservation) -> ReservationResponse:
        return ReservationResponse(
            id=reservation.id,
            sku=reservation.sku,
            quantity=reservation.quantity,
            status=reservation.status,
            idempotency_key=reservation.idempotency_key,
            created_at=reservation.created_at,
        )

    def _format_order(self, order) -> OrderResponse:
        return OrderResponse(
            id=order.id,
            reservation_id=order.reservation_id,
            sku=order.sku,
            quantity=order.quantity,
            created_at=order.created_at,
        )


class InsufficientStockError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class InvalidStateError(Exception):
    pass
