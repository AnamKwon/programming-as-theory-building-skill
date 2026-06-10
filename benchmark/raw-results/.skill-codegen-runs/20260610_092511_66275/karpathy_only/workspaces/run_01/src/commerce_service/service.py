import uuid
from datetime import datetime, timedelta
from typing import Optional

from .repository import Repository
from .models import (
    SKUResponse,
    StockResponse,
    ReservationResponse,
    OrderResponse,
)


class CommerceService:
    RESERVATION_EXPIRY_HOURS = 24

    def __init__(self, repo: Repository):
        self.repo = repo

    def create_sku(self, name: str, price: float) -> SKUResponse:
        sku_id = f"sku_{uuid.uuid4().hex[:12]}"
        sku = self.repo.create_sku(sku_id, name, price)
        return SKUResponse.model_validate(sku)

    def adjust_stock(self, sku_id: str, quantity_change: int) -> StockResponse:
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        stock = self.repo.adjust_stock(sku_id, quantity_change)
        return StockResponse.model_validate(stock)

    def create_reservation(
        self,
        sku_id: str,
        quantity: int,
        idempotency_key: str,
    ) -> ReservationResponse:
        # Check for idempotent retry
        existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            if existing.status == "expired":
                raise ValueError("Reservation has expired")
            return ReservationResponse.model_validate(existing)

        # Validate SKU exists
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        # Check stock availability
        stock = self.repo.get_stock(sku_id)
        if not stock or stock.quantity_available < quantity:
            raise ValueError(f"Insufficient stock for SKU {sku_id}")

        # Create reservation and reserve stock
        reservation_id = f"res_{uuid.uuid4().hex[:12]}"
        expires_at = datetime.utcnow() + timedelta(hours=self.RESERVATION_EXPIRY_HOURS)

        reservation = self.repo.create_reservation(
            reservation_id,
            sku_id,
            quantity,
            expires_at,
            idempotency_key,
        )

        # Reserve stock
        reserved = self.repo.reserve_stock(sku_id, quantity)
        if not reserved:
            # This shouldn't happen if we checked availability, but handle it
            self.repo.update_reservation_status(reservation_id, "failed")
            raise ValueError("Failed to reserve stock")

        return ReservationResponse.model_validate(reservation)

    def confirm_reservation(self, reservation_id: str) -> ReservationResponse:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status == "cancelled":
            raise ValueError("Cannot confirm a cancelled reservation")

        if reservation.status == "expired":
            raise ValueError("Reservation has expired")

        # Check if reservation has expired
        if datetime.utcnow() > reservation.expires_at:
            self.repo.update_reservation_status(reservation_id, "expired")
            # Release reserved stock
            self.repo.release_reservation(reservation.sku_id, reservation.quantity)
            raise ValueError("Reservation has expired")

        if reservation.status == "confirmed":
            return ReservationResponse.model_validate(reservation)

        # Confirm and deduct from reserved stock
        self.repo.confirm_reservation(reservation.sku_id, reservation.quantity)
        updated = self.repo.update_reservation_status(reservation_id, "confirmed")

        return ReservationResponse.model_validate(updated)

    def cancel_reservation(self, reservation_id: str) -> ReservationResponse:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status == "cancelled":
            return ReservationResponse.model_validate(reservation)

        if reservation.status == "confirmed":
            raise ValueError("Cannot cancel a confirmed reservation")

        # Release reserved stock back to available
        self.repo.release_reservation(reservation.sku_id, reservation.quantity)
        updated = self.repo.update_reservation_status(reservation_id, "cancelled")

        return ReservationResponse.model_validate(updated)

    def create_order(self) -> OrderResponse:
        order_id = f"ord_{uuid.uuid4().hex[:12]}"
        order = self.repo.create_order(order_id)
        return OrderResponse.model_validate(order)

    def get_order(self, order_id: str) -> OrderResponse:
        order = self.repo.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        return OrderResponse.model_validate(order)

    def list_orders(self, skip: int = 0, limit: int = 10) -> dict:
        orders, total = self.repo.list_orders(skip, limit)
        return {
            "items": [OrderResponse.model_validate(o) for o in orders],
            "total": total,
            "skip": skip,
            "limit": limit,
        }

    def cleanup_expired_reservations(self) -> int:
        """Mark expired reservations and release their stock. Returns count of expired."""
        expired = self.repo.get_expired_reservations()
        count = 0
        for reservation in expired:
            self.repo.update_reservation_status(reservation.id, "expired")
            self.repo.release_reservation(reservation.sku_id, reservation.quantity)
            count += 1
        return count
