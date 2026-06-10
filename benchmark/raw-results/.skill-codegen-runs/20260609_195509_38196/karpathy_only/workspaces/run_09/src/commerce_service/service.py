import uuid
from datetime import datetime, timedelta
from typing import Optional

from .models import ReservationStatus
from .repository import Repository


class InsufficientStockError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class ReservationExpiredError(Exception):
    pass


class ReservationAlreadyConfirmedError(Exception):
    pass


class IdempotencyConflictError(Exception):
    pass


class CommerceService:
    RESERVATION_EXPIRY_HOURS = 1

    def __init__(self, repository: Repository):
        self.repo = repository

    # SKU Management
    def create_sku(self, sku_id: str, initial_stock: int) -> dict:
        sku = self.repo.create_sku(sku_id, initial_stock)
        return {"sku_id": sku.id, "available_stock": sku.available_stock}

    def adjust_stock(self, sku_id: str, adjustment: int) -> dict:
        sku = self.repo.adjust_stock(sku_id, adjustment)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        return {"sku_id": sku.id, "available_stock": sku.available_stock}

    # Reservation Management
    def create_reservation(
        self,
        sku_id: str,
        quantity: int,
        idempotency_key: Optional[str] = None,
    ) -> dict:
        # Check for idempotency: if key exists, return existing reservation
        if idempotency_key:
            existing = self.repo.get_reservation_by_idempotency_key(idempotency_key)
            if existing:
                if existing.status == ReservationStatus.CONFIRMED:
                    raise IdempotencyConflictError(
                        "Idempotency key used with confirmed reservation"
                    )
                return {
                    "reservation_id": existing.id,
                    "sku_id": existing.sku_id,
                    "quantity": existing.quantity,
                    "status": existing.status,
                    "expires_at": existing.expires_at,
                }

        # Check SKU exists
        sku = self.repo.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        # Calculate available stock accounting for pending reservations
        reserved_qty = sum(
            r.quantity for r in self.repo.get_pending_reservations_for_sku(sku_id)
        )
        available = sku.available_stock - reserved_qty

        if available < quantity:
            raise InsufficientStockError(
                f"Insufficient stock: {available} available, {quantity} requested"
            )

        # Create reservation
        reservation_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(hours=self.RESERVATION_EXPIRY_HOURS)

        reservation = self.repo.create_reservation(
            reservation_id, sku_id, quantity, expires_at, idempotency_key
        )

        return {
            "reservation_id": reservation.id,
            "sku_id": reservation.sku_id,
            "quantity": reservation.quantity,
            "status": reservation.status,
            "expires_at": reservation.expires_at,
        }

    def confirm_reservation(self, reservation_id: str) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status == ReservationStatus.CONFIRMED:
            raise ReservationAlreadyConfirmedError(
                f"Reservation {reservation_id} already confirmed"
            )

        if reservation.status == ReservationStatus.CANCELLED:
            raise ValueError(f"Reservation {reservation_id} is cancelled")

        if reservation.expires_at < datetime.utcnow():
            raise ReservationExpiredError(
                f"Reservation {reservation_id} has expired"
            )

        # Update status to confirmed
        self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)

        # Create order
        order_id = str(uuid.uuid4())
        order = self.repo.create_order(
            order_id, reservation.sku_id, reservation.quantity, reservation_id
        )

        return {
            "order_id": order.id,
            "sku_id": order.sku_id,
            "quantity": order.quantity,
            "created_at": order.created_at,
        }

    def cancel_reservation(self, reservation_id: str) -> dict:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        if reservation.status == ReservationStatus.CONFIRMED:
            raise ValueError("Cannot cancel a confirmed reservation")

        if reservation.status == ReservationStatus.CANCELLED:
            raise ValueError(f"Reservation {reservation_id} already cancelled")

        self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)

        return {
            "reservation_id": reservation.id,
            "status": reservation.status,
        }

    def get_orders(self, page: int = 1, page_size: int = 20) -> dict:
        records, total = self.repo.get_orders(page, page_size)
        return {
            "orders": [
                {
                    "order_id": r.id,
                    "sku_id": r.sku_id,
                    "quantity": r.quantity,
                    "created_at": r.created_at,
                }
                for r in records
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
