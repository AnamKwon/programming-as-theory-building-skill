from datetime import datetime

from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import Session

from .models import OrderOrmModel, ReservationOrmModel, SKUOrmModel


class SKURepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, code: str, name: str, initial_stock: int) -> SKUOrmModel:
        sku = SKUOrmModel(code=code, name=name, available_stock=initial_stock)
        self.session.add(sku)
        self.session.flush()
        return sku

    def get_by_id(self, sku_id: int) -> SKUOrmModel | None:
        return self.session.execute(select(SKUOrmModel).where(SKUOrmModel.id == sku_id)).scalar_one_or_none()

    def get_by_code(self, code: str) -> SKUOrmModel | None:
        return self.session.execute(select(SKUOrmModel).where(SKUOrmModel.code == code)).scalar_one_or_none()

    def update_stock(self, sku_id: int, available_delta: int, reserved_delta: int = 0) -> SKUOrmModel | None:
        sku = self.get_by_id(sku_id)
        if not sku:
            return None
        sku.available_stock = max(0, sku.available_stock + available_delta)
        sku.reserved_stock = max(0, sku.reserved_stock + reserved_delta)
        self.session.flush()
        return sku


class ReservationRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(
        self, sku_id: int, quantity: int, idempotency_key: str, expires_at: datetime
    ) -> ReservationOrmModel:
        reservation = ReservationOrmModel(
            sku_id=sku_id, quantity=quantity, idempotency_key=idempotency_key, expires_at=expires_at
        )
        self.session.add(reservation)
        self.session.flush()
        return reservation

    def get_by_id(self, reservation_id: int) -> ReservationOrmModel | None:
        return self.session.execute(select(ReservationOrmModel).where(ReservationOrmModel.id == reservation_id)).scalar_one_or_none()

    def get_by_idempotency_key(self, idempotency_key: str) -> ReservationOrmModel | None:
        return self.session.execute(
            select(ReservationOrmModel).where(ReservationOrmModel.idempotency_key == idempotency_key)
        ).scalar_one_or_none()

    def update_status(self, reservation_id: int, status: str) -> ReservationOrmModel | None:
        reservation = self.get_by_id(reservation_id)
        if not reservation:
            return None
        reservation.status = status
        self.session.flush()
        return reservation

    def get_expired(self, now: datetime) -> list[ReservationOrmModel]:
        return self.session.execute(
            select(ReservationOrmModel).where(
                and_(
                    ReservationOrmModel.expires_at <= now,
                    ReservationOrmModel.status == "pending",
                )
            )
        ).scalars().all()


class OrderRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, sku_id: int, quantity: int) -> OrderOrmModel:
        order = OrderOrmModel(sku_id=sku_id, quantity=quantity)
        self.session.add(order)
        self.session.flush()
        return order

    def get_by_id(self, order_id: int) -> OrderOrmModel | None:
        return self.session.execute(select(OrderOrmModel).where(OrderOrmModel.id == order_id)).scalar_one_or_none()

    def list_paginated(self, limit: int = 20, offset: int = 0) -> tuple[list[OrderOrmModel], int]:
        total = self.session.execute(select(func.count()).select_from(OrderOrmModel)).scalar()
        items = self.session.execute(
            select(OrderOrmModel).order_by(desc(OrderOrmModel.created_at)).limit(limit).offset(offset)
        ).scalars().all()
        return items, total
