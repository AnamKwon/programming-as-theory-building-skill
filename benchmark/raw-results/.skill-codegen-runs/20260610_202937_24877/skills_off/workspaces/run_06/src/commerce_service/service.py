"""Business logic layer for commerce service."""

from datetime import datetime, timezone
from typing import Optional

from .models import OrderResponse, ReservationResponse, StockResponse
from .repository import Repository


class CommerceService:
    RESERVATION_EXPIRY_SECONDS = 300

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, sku: str, initial_stock: int):
        return self.repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> Optional[StockResponse]:
        sku_model = self.repo.update_sku_stock(sku, amount)
        if not sku_model:
            return None
        return StockResponse(sku=sku_model.sku, available_stock=sku_model.available_stock)

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> tuple[Optional[ReservationResponse], Optional[str]]:
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return (
                ReservationResponse(
                    id=existing.id,
                    sku=existing.sku,
                    quantity=existing.quantity,
                    status=existing.status,
                    created_at=existing.created_at,
                ),
                None,
            )

        sku_model = self.repo.get_sku_by_sku(sku)
        if not sku_model or sku_model.available_stock < quantity:
            return None, "Insufficient stock"

        reservation = self.repo.create_reservation(sku, quantity, idempotency_key)
        self.repo.update_sku_stock(sku, -quantity)

        return (
            ReservationResponse(
                id=reservation.id,
                sku=reservation.sku,
                quantity=reservation.quantity,
                status=reservation.status,
                created_at=reservation.created_at,
            ),
            None,
        )

    def confirm_reservation(self, reservation_id: int) -> tuple[Optional[dict], Optional[str]]:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            return None, "Reservation not found"
        if reservation.status != "PENDING":
            return None, f"Reservation is not in PENDING state"

        created_at_utc = reservation.created_at.replace(tzinfo=timezone.utc)
        now_utc = datetime.now(timezone.utc)
        elapsed = (now_utc - created_at_utc).total_seconds()

        if elapsed > self.RESERVATION_EXPIRY_SECONDS:
            self.repo.update_reservation_status(reservation_id, "EXPIRED")
            self.repo.update_sku_stock(reservation.sku, reservation.quantity)
            return None, "Reservation expired"

        self.repo.update_reservation_status(reservation_id, "CONFIRMED")
        order = self.repo.create_order(
            reservation_id, reservation.sku, reservation.quantity
        )

        return (
            OrderResponse(
                id=order.id,
                reservation_id=order.reservation_id,
                sku=order.sku,
                quantity=order.quantity,
                created_at=order.created_at,
            ),
            None,
        )

    def cancel_reservation(self, reservation_id: int) -> tuple[Optional[dict], Optional[str]]:
        reservation = self.repo.get_reservation_by_id(reservation_id)
        if not reservation:
            return None, "Reservation not found"
        if reservation.status != "PENDING":
            return None, f"Reservation is not in PENDING state"

        self.repo.update_reservation_status(reservation_id, "CANCELLED")
        self.repo.update_sku_stock(reservation.sku, reservation.quantity)

        return (
            ReservationResponse(
                id=reservation.id,
                sku=reservation.sku,
                quantity=reservation.quantity,
                status="CANCELLED",
                created_at=reservation.created_at,
            ),
            None,
        )
