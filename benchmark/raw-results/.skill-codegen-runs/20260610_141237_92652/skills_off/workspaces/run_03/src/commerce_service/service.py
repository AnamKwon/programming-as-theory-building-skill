"""Business logic layer."""
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from commerce_service.repository import (
    SKURepository,
    ReservationRepository,
    OrderRepository,
    ReservationModel,
    OrderModel,
)


RESERVATION_EXPIRY_SECONDS = 300


class CommerceService:
    def __init__(self, session: Session):
        self.sku_repo = SKURepository(session)
        self.reservation_repo = ReservationRepository(session)
        self.order_repo = OrderRepository(session)
        self.session = session

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        sku_model = self.sku_repo.create_sku(sku, initial_stock)
        return {
            "sku": sku_model.sku,
            "initial_stock": sku_model.initial_stock,
            "available_stock": sku_model.available_stock,
        }

    def adjust_stock(self, sku: str, amount: int) -> dict:
        sku_model = self.sku_repo.adjust_stock(sku, amount)
        if not sku_model:
            raise ValueError(f"SKU {sku} not found")
        return {
            "sku": sku_model.sku,
            "available_stock": sku_model.available_stock,
        }

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> Tuple[dict, int]:
        # Check for existing reservation with same idempotency key
        existing = self.reservation_repo.get_by_idempotency_key(idempotency_key)
        if existing:
            return self._reservation_to_dict(existing), 201

        # Check stock availability
        sku_model = self.sku_repo.get_sku(sku)
        if not sku_model or sku_model.available_stock < quantity:
            raise ValueError("Insufficient stock")

        # Create reservation and deduct stock
        now = datetime.now(timezone.utc)
        reservation = self.reservation_repo.create_reservation(
            sku, quantity, idempotency_key, now
        )
        self.sku_repo.adjust_stock(sku, -quantity)

        return self._reservation_to_dict(reservation), 201

    def confirm_reservation(self, reservation_id: int) -> dict:
        reservation = self.reservation_repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != "PENDING":
            raise ValueError(f"Cannot confirm reservation in {reservation.status} status")

        # Check expiration
        now = datetime.now(timezone.utc)
        age_seconds = (now - reservation.created_at).total_seconds()
        if age_seconds > RESERVATION_EXPIRY_SECONDS:
            self.reservation_repo.update_status(reservation_id, "EXPIRED")
            # Restore stock
            self.sku_repo.adjust_stock(reservation.sku, reservation.quantity)
            raise ValueError("Reservation expired")

        # Update status and create order
        self.reservation_repo.update_status(reservation_id, "CONFIRMED")
        order = self.order_repo.create_order(
            reservation_id, datetime.now(timezone.utc)
        )

        return {
            "id": reservation_id,
            "status": "CONFIRMED",
            "order_id": order.id,
        }

    def cancel_reservation(self, reservation_id: int) -> dict:
        reservation = self.reservation_repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != "PENDING":
            raise ValueError(f"Cannot cancel reservation in {reservation.status} status")

        # Update status and restore stock
        self.reservation_repo.update_status(reservation_id, "CANCELLED")
        self.sku_repo.adjust_stock(reservation.sku, reservation.quantity)

        return {
            "id": reservation_id,
            "status": "CANCELLED",
        }

    def list_orders(self, page: int = 1, size: int = 10) -> dict:
        orders, total = self.order_repo.list_orders(page, size)
        return {
            "items": [
                {
                    "id": order.id,
                    "reservation_id": order.reservation_id,
                    "created_at": order.created_at,
                }
                for order in orders
            ],
            "page": page,
            "size": size,
            "total": total,
        }

    @staticmethod
    def _reservation_to_dict(reservation: ReservationModel) -> dict:
        return {
            "id": reservation.id,
            "sku": reservation.sku,
            "quantity": reservation.quantity,
            "status": reservation.status,
            "created_at": reservation.created_at,
            "idempotency_key": reservation.idempotency_key,
        }
