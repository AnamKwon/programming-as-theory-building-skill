from sqlalchemy.orm import Session
from .repository import Repository
from .models import (
    ReservationResponse,
    OrderResponse,
    OrderListResponse,
)
from datetime import datetime


class Service:
    def __init__(self, db: Session):
        self.repo = Repository(db)

    def create_sku(self, sku: str, initial_stock: int):
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int):
        return self.repo.adjust_stock(sku, amount)

    def reserve_stock(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> ReservationResponse:
        # Check for idempotency
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return ReservationResponse(
                id=existing.id,
                sku=existing.sku,
                quantity=existing.quantity,
                status=existing.status,
                created_at=existing.created_at,
            )

        # Check stock
        sku_record = self.repo.get_sku_by_name(sku)
        if not sku_record:
            raise ValueError(f"SKU {sku} not found")
        if sku_record.stock < quantity:
            raise ValueError("Insufficient stock")

        # Deduct stock
        self.repo.adjust_stock(sku, -quantity)

        # Create reservation
        reservation = self.repo.create_reservation(sku, quantity, idempotency_key)

        return ReservationResponse(
            id=reservation.id,
            sku=reservation.sku,
            quantity=reservation.quantity,
            status=reservation.status,
            created_at=reservation.created_at,
        )

    def confirm_reservation(self, reservation_id: int) -> OrderResponse:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != "PENDING":
            raise ValueError(
                f"Cannot confirm reservation with status {reservation.status}"
            )

        # Check expiration (300 seconds)
        now = datetime.utcnow()
        elapsed = (now - reservation.created_at).total_seconds()
        if elapsed > 300:
            # Mark as expired and restore stock
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.adjust_stock(reservation.sku, reservation.quantity)
            raise ValueError("Reservation expired")

        # Confirm reservation
        self.repo.update_reservation_status(reservation_id, "CONFIRMED")

        # Create order
        order = self.repo.create_order(reservation_id)

        return OrderResponse(id=order.id, created_at=order.created_at)

    def cancel_reservation(self, reservation_id: int) -> ReservationResponse:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != "PENDING":
            raise ValueError(
                f"Cannot cancel reservation with status {reservation.status}"
            )

        # Restore stock
        self.repo.adjust_stock(reservation.sku, reservation.quantity)

        # Cancel reservation
        self.repo.update_reservation_status(reservation_id, "CANCELLED")

        return ReservationResponse(
            id=reservation.id,
            sku=reservation.sku,
            quantity=reservation.quantity,
            status="CANCELLED",
            created_at=reservation.created_at,
        )

    def get_orders(self, page: int = 1, size: int = 10) -> OrderListResponse:
        orders, total = self.repo.get_orders(page, size)
        items = [OrderResponse(id=order.id, created_at=order.created_at) for order in orders]
        return OrderListResponse(items=items, page=page, size=size, total=total)
