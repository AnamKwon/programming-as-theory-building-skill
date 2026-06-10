from datetime import datetime, timezone
from typing import Optional, Tuple, List
from .repository import SKURepository, ReservationRepository, OrderRepository
from .models import (
    ReservationResponse, OrderResponse, PaginatedOrders, SKUResponse,
    StockAdjustResponse
)


RESERVATION_TTL_SECONDS = 300


class CommerceService:
    def __init__(self):
        self.sku_repo = SKURepository()
        self.reservation_repo = ReservationRepository()
        self.order_repo = OrderRepository()

    def create_sku(self, sku: str, initial_stock: int) -> SKUResponse:
        result = self.sku_repo.create_sku(sku, initial_stock)
        return SKUResponse(**result)

    def adjust_stock(self, sku: str, amount: int) -> StockAdjustResponse:
        result = self.sku_repo.adjust_stock(sku, amount)
        return StockAdjustResponse(**result)

    def create_reservation(
        self,
        sku: str,
        quantity: int,
        idempotency_key: str
    ) -> Tuple[ReservationResponse, int]:
        # Check idempotency key first
        existing = self.reservation_repo.check_idempotency_key(idempotency_key)
        if existing:
            return ReservationResponse(**existing), 200

        # Check stock
        current_stock = self.sku_repo.get_stock(sku)
        if current_stock is None:
            raise ValueError(f"SKU {sku} not found")
        if current_stock < quantity:
            raise ValueError("Insufficient stock")

        # Create reservation and deduct stock
        now = datetime.now(timezone.utc).isoformat()
        self.sku_repo.adjust_stock(sku, -quantity)
        result = self.reservation_repo.create_reservation(
            sku, quantity, idempotency_key, now
        )
        return ReservationResponse(**result), 201

    def confirm_reservation(self, reservation_id: int) -> ReservationResponse:
        reservation = self.reservation_repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation["status"] != "PENDING":
            raise ValueError(f"Reservation is not in PENDING state")

        # Check if expired
        created_at = datetime.fromisoformat(reservation["created_at"])
        now = datetime.now(timezone.utc)
        age_seconds = (now - created_at).total_seconds()

        if age_seconds > RESERVATION_TTL_SECONDS:
            # Mark as expired and restore stock
            self.reservation_repo.update_reservation_status(reservation_id, "EXPIRED")
            self.sku_repo.adjust_stock(reservation["sku"], reservation["quantity"])
            raise ValueError("Reservation expired")

        # Update status and create order
        updated = self.reservation_repo.update_reservation_status(
            reservation_id, "CONFIRMED"
        )
        now_iso = datetime.now(timezone.utc).isoformat()
        self.order_repo.create_order(reservation_id, now_iso)

        return ReservationResponse(**updated)

    def cancel_reservation(self, reservation_id: int) -> ReservationResponse:
        reservation = self.reservation_repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation["status"] != "PENDING":
            raise ValueError(f"Reservation is not in PENDING state")

        # Update status and restore stock
        updated = self.reservation_repo.update_reservation_status(
            reservation_id, "CANCELLED"
        )
        self.sku_repo.adjust_stock(reservation["sku"], reservation["quantity"])

        return ReservationResponse(**updated)

    def get_orders_paginated(self, page: int, size: int) -> PaginatedOrders:
        orders, total = self.order_repo.get_orders_paginated(page, size)
        return PaginatedOrders(
            items=[OrderResponse(**order) for order in orders],
            page=page,
            size=size,
            total=total
        )
