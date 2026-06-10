"""Business logic service layer."""

from datetime import datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from .models import Reservation, ReservationStatus
from .repository import SKURepository, ReservationRepository, OrderRepository


class CommerceService:
    def __init__(self, session: Session):
        self.session = session
        self.sku_repo = SKURepository(session)
        self.reservation_repo = ReservationRepository(session)
        self.order_repo = OrderRepository(session)

    def create_sku(self, sku: str, initial_stock: int):
        return self.sku_repo.create_sku(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int):
        return self.sku_repo.adjust_stock(sku, amount)

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> Tuple[Reservation, int]:
        existing = self.reservation_repo.get_reservation_by_idempotency_key(idempotency_key)
        if existing:
            return existing, 201

        sku_record = self.sku_repo.get_sku_by_code(sku)
        if not sku_record or sku_record.available_stock < quantity:
            return None, 400

        self.sku_repo.adjust_stock(sku, -quantity)
        reservation = self.reservation_repo.create_reservation(sku, quantity, idempotency_key)
        return reservation, 201

    def confirm_reservation(self, reservation_id: int) -> Tuple[Optional[dict], int]:
        reservation = self.reservation_repo.get_reservation_by_id(reservation_id)

        if not reservation:
            return None, 404

        if reservation.status != ReservationStatus.PENDING:
            return None, 400

        now = datetime.utcnow()
        created_at = reservation.created_at
        elapsed = (now - created_at).total_seconds()

        if elapsed > 300:
            self.reservation_repo.update_reservation_status(reservation_id, ReservationStatus.EXPIRED)
            self.sku_repo.adjust_stock(reservation.sku, reservation.quantity)
            return None, 400

        self.reservation_repo.update_reservation_status(reservation_id, ReservationStatus.CONFIRMED)
        order = self.order_repo.create_order(reservation_id)
        return {"id": order.id, "reservation_id": order.reservation_id, "created_at": order.created_at}, 200

    def cancel_reservation(self, reservation_id: int) -> Tuple[Optional[dict], int]:
        reservation = self.reservation_repo.get_reservation_by_id(reservation_id)

        if not reservation:
            return None, 404

        if reservation.status != ReservationStatus.PENDING:
            return None, 400

        self.reservation_repo.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)
        self.sku_repo.adjust_stock(reservation.sku, reservation.quantity)
        return {}, 200

    def get_orders_paginated(self, page: int = 1, size: int = 10):
        orders, total = self.order_repo.get_orders_paginated(page, size)
        return orders, total
