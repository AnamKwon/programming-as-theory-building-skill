from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from .models import ReservationOrm, OrderOrm, SKUOrm
from .repository import SKURepository, ReservationRepository, OrderRepository


class CommerceService:
    def __init__(self, session: Session):
        self.session = session
        self.sku_repo = SKURepository(session)
        self.reservation_repo = ReservationRepository(session)
        self.order_repo = OrderRepository(session)

    def create_sku(self, sku: str, initial_stock: int) -> SKUOrm:
        return self.sku_repo.create(sku, initial_stock)

    def adjust_stock(self, sku: str, amount: int) -> SKUOrm:
        return self.sku_repo.update_stock(sku, amount)

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> ReservationOrm:
        existing_reservation = self.reservation_repo.get_by_idempotency_key(idempotency_key)
        if existing_reservation:
            return existing_reservation

        sku_record = self.sku_repo.get_by_sku(sku)
        if not sku_record or sku_record.available_stock < quantity:
            raise ValueError("Insufficient stock")

        now = datetime.now(timezone.utc)
        reservation = self.reservation_repo.create(sku, quantity, idempotency_key, now)
        self.sku_repo.update_stock(sku, -quantity)

        return reservation

    def confirm_reservation(self, reservation_id: int) -> OrderOrm:
        reservation = self.reservation_repo.get_by_id(reservation_id)
        if not reservation:
            raise ValueError("Reservation not found")

        if reservation.status != "PENDING":
            raise ValueError("Reservation is not pending")

        now = datetime.now(timezone.utc)
        time_elapsed = (now - reservation.created_at.replace(tzinfo=timezone.utc)).total_seconds()

        if time_elapsed > 300:
            self.reservation_repo.update_status(reservation_id, "EXPIRED")
            self.sku_repo.update_stock(reservation.sku, reservation.quantity)
            raise ValueError("Reservation expired")

        self.reservation_repo.update_status(reservation_id, "CONFIRMED")
        order = self.order_repo.create(reservation_id, now)

        return order

    def cancel_reservation(self, reservation_id: int) -> ReservationOrm:
        reservation = self.reservation_repo.get_by_id(reservation_id)
        if not reservation:
            raise ValueError("Reservation not found")

        if reservation.status != "PENDING":
            raise ValueError("Reservation is not pending")

        self.reservation_repo.update_status(reservation_id, "CANCELLED")
        self.sku_repo.update_stock(reservation.sku, reservation.quantity)

        return reservation

    def list_orders(self, page: int = 1, size: int = 10) -> tuple[list[OrderOrm], int]:
        return self.order_repo.list_orders(page, size)
