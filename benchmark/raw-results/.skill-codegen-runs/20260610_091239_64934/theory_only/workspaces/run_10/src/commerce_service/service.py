import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .models import OrderModel, ReservationModel, SKUModel
from .repository import Repository


class CommerceService:
    RESERVATION_TTL_MINUTES = 15

    def __init__(self, repository: Repository):
        self.repo = repository

    def create_sku(self, session: Session, sku_id: str, stock: int) -> SKUModel:
        existing = self.repo.get_sku(session, sku_id)
        if existing:
            raise ValueError(f"SKU {sku_id} already exists")
        return self.repo.create_sku(session, sku_id, stock)

    def adjust_stock(self, session: Session, sku_id: str, delta: int) -> SKUModel:
        sku = self.repo.get_sku(session, sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        if sku.total_stock + delta < 0:
            raise ValueError("Stock adjustment would result in negative total stock")
        return self.repo.update_sku_stock(session, sku_id, delta)

    def create_reservation(
        self,
        session: Session,
        sku_id: str,
        quantity: int,
        idempotency_key: Optional[str] = None,
    ) -> ReservationModel:
        # Check idempotency: if key exists, return existing reservation
        if idempotency_key:
            existing = self.repo.get_reservation_by_idempotency_key(session, idempotency_key)
            if existing:
                return existing

        sku = self.repo.get_sku(session, sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")

        if sku.available_stock < quantity:
            raise ValueError(
                f"Insufficient stock for {sku_id}: need {quantity}, "
                f"available {sku.available_stock}"
            )

        reservation_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=self.RESERVATION_TTL_MINUTES)
        reservation = self.repo.create_reservation(
            session, reservation_id, sku_id, quantity, expires_at, idempotency_key
        )

        # Reserve stock
        self.repo.update_sku_reserved(session, sku_id, quantity)

        return reservation

    def confirm_reservation(self, session: Session, reservation_id: str) -> OrderModel:
        reservation = self.repo.get_reservation(session, reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != "active":
            raise ValueError(f"Reservation {reservation_id} is not active")

        if reservation.is_expired():
            raise ValueError(f"Reservation {reservation_id} has expired")

        # Create order from reservation
        order_id = str(uuid.uuid4())
        order = self.repo.create_order(
            session,
            order_id,
            reservation.sku_id,
            reservation.quantity,
            reservation_id=reservation_id,
            status="confirmed",
        )

        # Move reserved to sold
        self.repo.update_sku_reserved(session, reservation.sku_id, -reservation.quantity)
        self.repo.update_sku_sold(session, reservation.sku_id, reservation.quantity)

        # Mark reservation as confirmed
        self.repo.update_reservation_status(session, reservation_id, "confirmed")

        return order

    def cancel_reservation(self, session: Session, reservation_id: str) -> ReservationModel:
        reservation = self.repo.get_reservation(session, reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != "active":
            # Idempotent: if already cancelled, return it
            return reservation

        # Release reserved stock
        self.repo.update_sku_reserved(session, reservation.sku_id, -reservation.quantity)

        # Mark reservation as cancelled
        return self.repo.update_reservation_status(session, reservation_id, "cancelled")

    def get_order(self, session: Session, order_id: str) -> Optional[OrderModel]:
        return self.repo.get_order(session, order_id)

    def list_orders(
        self, session: Session, page: int = 1, page_size: int = 20
    ) -> tuple[list[OrderModel], int]:
        if page < 1:
            raise ValueError("Page must be >= 1")
        if page_size < 1 or page_size > 100:
            raise ValueError("Page size must be between 1 and 100")

        skip = (page - 1) * page_size
        return self.repo.list_orders(session, skip=skip, limit=page_size)
