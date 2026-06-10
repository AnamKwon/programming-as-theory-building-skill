from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .models import (
    SKUModel,
    ReservationModel,
    OrderModel,
    CreateSKURequest,
    AdjustStockRequest,
    CreateReservationRequest,
    ReservationResponse,
    OrderResponse,
    OrderListResponse,
)
from .repository import Repository


class CommerceService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = Repository(db)

    def create_sku(self, request: CreateSKURequest) -> SKUModel:
        """Create a new SKU with initial stock."""
        return self.repo.create_sku(request.sku, request.initial_stock)

    def adjust_stock(self, request: AdjustStockRequest) -> dict:
        """Adjust stock for a SKU by a given amount (positive or negative)."""
        sku_model = self.repo.get_sku_by_code(request.sku)
        if sku_model is None:
            raise ValueError(f"SKU {request.sku} not found")

        updated = self.repo.update_sku_stock(request.sku, request.amount)
        return {"sku": updated.sku, "available_stock": updated.available_stock}

    def create_reservation(self, request: CreateReservationRequest) -> ReservationResponse:
        """
        Create a reservation for a SKU.

        Rules:
        1. Check if sufficient stock is available
        2. Check idempotency: if key exists, return previous result
        3. Deduct stock and create reservation with PENDING status
        """
        sku_model = self.repo.get_sku_by_code(request.sku)
        if sku_model is None:
            raise ValueError(f"SKU {request.sku} not found")

        if sku_model.available_stock < request.quantity:
            raise ValueError("Insufficient stock")

        existing = self.repo.get_reservation_by_idempotency_key(request.idempotency_key)
        if existing is not None:
            return ReservationResponse(
                id=existing.id,
                sku=existing.sku,
                quantity=existing.quantity,
                status=existing.status,
                created_at=existing.created_at,
            )

        self.repo.update_sku_stock(request.sku, -request.quantity)

        reservation = self.repo.create_reservation(
            request.sku, request.quantity, request.idempotency_key
        )

        return ReservationResponse(
            id=reservation.id,
            sku=reservation.sku,
            quantity=reservation.quantity,
            status=reservation.status,
            created_at=reservation.created_at,
        )

    def confirm_reservation(self, reservation_id: int) -> OrderResponse:
        """
        Confirm a reservation and create an order.

        Rules:
        1. Reservation must be in PENDING status
        2. Reservation must not be expired (> 300 seconds old)
        3. Change status to CONFIRMED
        4. Create corresponding Order record
        """
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if reservation is None:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != "PENDING":
            raise ValueError(f"Reservation is not in PENDING state (current: {reservation.status})")

        age_seconds = (datetime.utcnow() - reservation.created_at).total_seconds()
        if age_seconds > 300:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.update_sku_stock(reservation.sku, reservation.quantity)
            raise ValueError("Reservation expired")

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        order = self.repo.create_order(reservation_id, reservation.sku, reservation.quantity)

        return OrderResponse(
            id=order.id,
            reservation_id=order.reservation_id,
            sku=order.sku,
            quantity=order.quantity,
            created_at=order.created_at,
        )

    def cancel_reservation(self, reservation_id: int) -> ReservationResponse:
        """
        Cancel a reservation and restore stock.

        Rules:
        1. Reservation must be in PENDING status
        2. Change status to CANCELLED
        3. Restore the reserved quantity to available stock
        """
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if reservation is None:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != "PENDING":
            raise ValueError(f"Reservation is not in PENDING state (current: {reservation.status})")

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        self.repo.update_sku_stock(reservation.sku, reservation.quantity)

        updated = self.repo.get_reservation_by_id(reservation_id)
        return ReservationResponse(
            id=updated.id,
            sku=updated.sku,
            quantity=updated.quantity,
            status=updated.status,
            created_at=updated.created_at,
        )

    def get_orders(self, page: int = 1, size: int = 10) -> OrderListResponse:
        """Get paginated list of orders."""
        orders, total = self.repo.get_orders_paginated(page, size)
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
        return OrderListResponse(total=total, page=page, size=size, items=items)
