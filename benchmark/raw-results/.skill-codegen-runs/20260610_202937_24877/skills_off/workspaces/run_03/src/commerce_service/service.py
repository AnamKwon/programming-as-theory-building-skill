from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from .repository import SKURepository, ReservationRepository, OrderRepository
from .models import (
    SKUCreate,
    ReservationCreate,
    ReservationResponse,
    OrderResponse,
    OrderListResponse,
)


class CommerceService:
    def __init__(self, db: Session):
        self.db = db
        self.sku_repo = SKURepository(db)
        self.reservation_repo = ReservationRepository(db)
        self.order_repo = OrderRepository(db)

    def create_sku(self, sku_create: SKUCreate):
        return self.sku_repo.create(sku_create.sku, sku_create.initial_stock)

    def adjust_stock(self, sku: str, amount: int):
        return self.sku_repo.update_stock(sku, amount)

    def create_reservation(self, reservation_create: ReservationCreate):
        existing = self.reservation_repo.get_by_idempotency_key(reservation_create.idempotency_key)
        if existing:
            return existing

        sku_record = self.sku_repo.get_by_sku(reservation_create.sku)
        if not sku_record or sku_record.available_stock < reservation_create.quantity:
            return None

        self.sku_repo.update_stock(reservation_create.sku, -reservation_create.quantity)

        return self.reservation_repo.create(
            reservation_create.sku,
            reservation_create.quantity,
            reservation_create.idempotency_key,
        )

    def confirm_reservation(self, reservation_id: int):
        reservation = self.reservation_repo.get_by_id(reservation_id)
        if not reservation:
            return None, "not_found"

        if reservation.status != "PENDING":
            return None, "invalid_state"

        now = datetime.utcnow()
        created_at = reservation.created_at
        age_seconds = (now - created_at).total_seconds()

        if age_seconds > 300:
            self.reservation_repo.update_status(reservation_id, "EXPIRED")
            sku_record = self.sku_repo.get_by_sku(reservation.sku)
            if sku_record:
                self.sku_repo.update_stock(reservation.sku, reservation.quantity)
            return None, "expired"

        self.reservation_repo.update_status(reservation_id, "CONFIRMED")
        self.order_repo.create(reservation_id)

        updated_reservation = self.reservation_repo.get_by_id(reservation_id)
        return updated_reservation, "success"

    def cancel_reservation(self, reservation_id: int):
        reservation = self.reservation_repo.get_by_id(reservation_id)
        if not reservation:
            return None, "not_found"

        if reservation.status != "PENDING":
            return None, "invalid_state"

        self.reservation_repo.update_status(reservation_id, "CANCELLED")
        self.sku_repo.update_stock(reservation.sku, reservation.quantity)

        updated_reservation = self.reservation_repo.get_by_id(reservation_id)
        return updated_reservation, "success"

    def get_orders(self, page: int = 1, size: int = 10) -> OrderListResponse:
        orders, total = self.order_repo.get_all(page, size)
        return OrderListResponse(
            items=[OrderResponse(id=o.id, reservation_id=o.reservation_id, created_at=o.created_at) for o in orders],
            page=page,
            size=size,
            total=total,
        )
