from datetime import datetime
from sqlalchemy.orm import Session

from .models import ReservationStatus, ReservationResponse, OrderResponse
from .repository import Repository


class CommerceService:
    def __init__(self, db: Session):
        self.repo = Repository(db)

    def create_sku(self, sku_name: str, initial_stock: int):
        """Create a new SKU with initial stock."""
        existing = self.repo.get_sku_by_name(sku_name)
        if existing:
            raise ValueError(f"SKU {sku_name} already exists")
        return self.repo.create_sku(sku_name, initial_stock)

    def adjust_stock(self, sku_name: str, amount: int):
        """Adjust stock level for a SKU."""
        sku = self.repo.get_sku_by_name(sku_name)
        if not sku:
            raise ValueError(f"SKU {sku_name} not found")
        return self.repo.adjust_stock(sku.id, amount)

    def create_reservation(self, sku_name: str, quantity: int, idempotency_key: str) -> ReservationResponse:
        """Create a reservation with idempotency support."""
        existing_reservation = self.repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing_reservation:
            return ReservationResponse.model_validate(existing_reservation)

        sku = self.repo.get_sku_by_name(sku_name)
        if not sku:
            raise ValueError(f"SKU {sku_name} not found")

        if sku.available_stock < quantity:
            raise ValueError("Insufficient stock")

        reservation = self.repo.create_reservation(sku.id, sku_name, quantity, idempotency_key)
        return ReservationResponse.model_validate(reservation)

    def confirm_reservation(self, reservation_id: int) -> OrderResponse:
        """Confirm a reservation and create an order."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != ReservationStatus.PENDING:
            raise ValueError(f"cannot be confirmed: reservation in {reservation.status} status")

        now = datetime.utcnow()
        created_age = (now - reservation.created_at).total_seconds()
        if created_age > 300:
            self.repo.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
            self.repo.restore_stock(reservation.sku_id, reservation.quantity)
            raise ValueError("Reservation expired")

        self.repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)
        order = self.repo.create_order(reservation_id)
        return OrderResponse.model_validate(order)

    def cancel_reservation(self, reservation_id: int):
        """Cancel a reservation and restore stock."""
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != ReservationStatus.PENDING:
            raise ValueError(f"cannot be cancelled: reservation in {reservation.status} status")

        self.repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)
        self.repo.restore_stock(reservation.sku_id, reservation.quantity)
        return reservation

    def get_orders_paginated(self, page: int, size: int):
        """Get paginated orders."""
        orders, total = self.repo.get_orders_paginated(page, size)
        return orders, total
