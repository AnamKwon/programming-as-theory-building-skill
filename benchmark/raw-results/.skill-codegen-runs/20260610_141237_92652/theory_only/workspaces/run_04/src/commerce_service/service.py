from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .models import ReservationResponse, OrderResponse, StockAdjustmentResponse
from .repository import SKURepository, ReservationRepository, OrderRepository


class CommerceService:
    def __init__(self, session: Session):
        self.sku_repo = SKURepository(session)
        self.reservation_repo = ReservationRepository(session)
        self.order_repo = OrderRepository(session)

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        record = self.sku_repo.create_sku(sku, initial_stock)
        return {"sku": record.sku, "available_stock": record.available_stock}

    def adjust_stock(self, sku: str, amount: int) -> StockAdjustmentResponse:
        record = self.sku_repo.adjust_stock(sku, amount)
        if not record:
            raise ValueError(f"SKU {sku} not found")
        return StockAdjustmentResponse(
            sku=record.sku, available_stock=record.available_stock
        )

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> tuple[ReservationResponse, int]:
        # Check idempotency
        existing = self.reservation_repo.get_reservation_by_idempotency_key(
            idempotency_key
        )
        if existing:
            return (
                ReservationResponse.model_validate(existing),
                200,
            )

        # Check stock availability
        available = self.sku_repo.get_available_stock(sku)
        if available < quantity:
            raise ValueError("Insufficient stock")

        # Deduct stock and create reservation
        self.sku_repo.adjust_stock(sku, -quantity)
        record = self.reservation_repo.create_reservation(sku, quantity, idempotency_key)

        return (ReservationResponse.model_validate(record), 201)

    def confirm_reservation(self, reservation_id: int) -> OrderResponse:
        reservation = self.reservation_repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != "PENDING":
            raise ValueError(f"Reservation is not in PENDING state")

        # Check expiration (300 seconds)
        elapsed = (datetime.utcnow() - reservation.created_at).total_seconds()
        if elapsed > 300:
            # Mark as expired and restore stock
            self.reservation_repo.update_reservation_status(reservation_id, "EXPIRED")
            self.sku_repo.adjust_stock(reservation.sku, reservation.quantity)
            raise ValueError("Reservation expired")

        # Update status to CONFIRMED
        self.reservation_repo.update_reservation_status(reservation_id, "CONFIRMED")

        # Create order
        order = self.order_repo.create_order(
            reservation_id, reservation.sku, reservation.quantity
        )

        return OrderResponse.model_validate(order)

    def cancel_reservation(self, reservation_id: int) -> ReservationResponse:
        reservation = self.reservation_repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != "PENDING":
            raise ValueError(f"Reservation is not in PENDING state")

        # Update status to CANCELLED
        self.reservation_repo.update_reservation_status(reservation_id, "CANCELLED")

        # Restore stock
        self.sku_repo.adjust_stock(reservation.sku, reservation.quantity)

        return ReservationResponse.model_validate(reservation)

    def get_orders(
        self, page: int = 1, size: int = 10
    ) -> tuple[list[OrderResponse], int]:
        orders, total = self.order_repo.get_orders(page, size)
        return [OrderResponse.model_validate(order) for order in orders], total
