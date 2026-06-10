"""Business logic service layer."""

from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from .repository import Repository
from .models import (
    SKUCreate,
    SKUResponse,
    StockAdjustRequest,
    StockAdjustResponse,
    ReservationCreate,
    ReservationResponse,
    ReservationConfirmResponse,
    OrderResponse,
    OrderListResponse,
)


class CommerceService:
    RESERVATION_EXPIRATION_SECONDS = 300

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, request: SKUCreate) -> SKUResponse:
        sku_record = self.repo.create_sku(request.sku, request.initial_stock)
        return SKUResponse(
            sku=sku_record.sku,
            available_stock=sku_record.available_stock,
            reserved_stock=sku_record.reserved_stock,
        )

    def adjust_stock(self, request: StockAdjustRequest) -> StockAdjustResponse:
        available, reserved = self.repo.adjust_stock(request.sku, request.amount)
        return StockAdjustResponse(
            sku=request.sku,
            available_stock=available,
            reserved_stock=reserved,
        )

    def create_reservation(self, request: ReservationCreate) -> Tuple[ReservationResponse, bool]:
        existing = self.repo.get_reservation_by_idempotency_key(request.idempotency_key)
        if existing:
            return ReservationResponse(
                id=existing.id,
                sku=existing.sku,
                quantity=existing.quantity,
                status=existing.status,
                created_at=existing.created_at,
                idempotency_key=existing.idempotency_key,
            ), True

        sku_record = self.repo.get_sku(request.sku)
        if sku_record is None or sku_record.available_stock < request.quantity:
            raise ValueError("Insufficient stock")

        if not self.repo.reserve_stock(request.sku, request.quantity):
            raise ValueError("Insufficient stock")

        reservation = self.repo.create_reservation(
            request.sku,
            request.quantity,
            request.idempotency_key,
        )

        return ReservationResponse(
            id=reservation.id,
            sku=reservation.sku,
            quantity=reservation.quantity,
            status=reservation.status,
            created_at=reservation.created_at,
            idempotency_key=reservation.idempotency_key,
        ), False

    def confirm_reservation(self, reservation_id: int) -> ReservationConfirmResponse:
        reservation = self.repo.get_reservation(reservation_id)
        if reservation is None:
            raise ValueError("Reservation not found")

        if reservation.status != "PENDING":
            raise ValueError(f"Reservation is not in PENDING state")

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        age = (now - reservation.created_at).total_seconds()
        if age > self.RESERVATION_EXPIRATION_SECONDS:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.release_reserved_stock(reservation.sku, reservation.quantity)
            raise ValueError("Reservation expired")

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        self.repo.reserve_confirmed(reservation.sku, reservation.quantity)

        order = self.repo.create_order(reservation_id, reservation.sku, reservation.quantity)

        return ReservationConfirmResponse(
            id=reservation.id,
            sku=reservation.sku,
            quantity=reservation.quantity,
            status="CONFIRMED",
            created_at=reservation.created_at,
            order_id=order.id,
        )

    def cancel_reservation(self, reservation_id: int) -> ReservationResponse:
        reservation = self.repo.get_reservation(reservation_id)
        if reservation is None:
            raise ValueError("Reservation not found")

        if reservation.status != "PENDING":
            raise ValueError(f"Reservation is not in PENDING state")

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        self.repo.release_reserved_stock(reservation.sku, reservation.quantity)

        return ReservationResponse(
            id=reservation.id,
            sku=reservation.sku,
            quantity=reservation.quantity,
            status="CANCELLED",
            created_at=reservation.created_at,
            idempotency_key=reservation.idempotency_key,
        )

    def get_orders(self, page: int = 1, size: int = 10) -> OrderListResponse:
        orders, total = self.repo.get_orders(page, size)
        items = [
            OrderResponse(
                id=order.id,
                reservation_id=order.reservation_id,
                sku=order.sku,
                quantity=order.quantity,
                created_at=order.created_at,
            )
            for order in orders
        ]
        return OrderListResponse(
            items=items,
            page=page,
            size=size,
            total=total,
        )
