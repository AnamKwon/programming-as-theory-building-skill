from datetime import datetime
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from .models import (
    OrderORM,
    OrderSchema,
    OrderState,
    ReservationORM,
    ReservationSchema,
    ReservationState,
    SKUSchema,
    SKUorm,
)


class Repository:
    def __init__(self, db: Session):
        self.db = db

    def create_sku(self, sku_code: str, name: str, quantity: int) -> SKUSchema:
        sku = SKUorm(sku_code=sku_code, name=name, quantity=quantity)
        self.db.add(sku)
        self.db.commit()
        self.db.refresh(sku)
        return SKUSchema.model_validate(sku)

    def get_sku(self, sku_id: int) -> Optional[SKUSchema]:
        sku = self.db.query(SKUorm).filter(SKUorm.id == sku_id).first()
        return SKUSchema.model_validate(sku) if sku else None

    def update_sku_quantity(self, sku_id: int, quantity_delta: int) -> Optional[SKUSchema]:
        sku = self.db.query(SKUorm).filter(SKUorm.id == sku_id).with_for_update().first()
        if not sku:
            return None
        sku.quantity += quantity_delta
        self.db.commit()
        self.db.refresh(sku)
        return SKUSchema.model_validate(sku)

    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        expires_at: datetime,
        idempotency_key: Optional[str] = None,
    ) -> ReservationSchema:
        reservation = ReservationORM(
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
            state=ReservationState.PENDING,
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return ReservationSchema.model_validate(reservation)

    def get_reservation(self, reservation_id: int) -> Optional[ReservationSchema]:
        res = self.db.query(ReservationORM).filter(ReservationORM.id == reservation_id).first()
        return ReservationSchema.model_validate(res) if res else None

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[ReservationSchema]:
        res = self.db.query(ReservationORM).filter(
            ReservationORM.idempotency_key == idempotency_key
        ).first()
        return ReservationSchema.model_validate(res) if res else None

    def update_reservation_state(self, reservation_id: int, state: str) -> Optional[ReservationSchema]:
        res = self.db.query(ReservationORM).filter(
            ReservationORM.id == reservation_id
        ).with_for_update().first()
        if not res:
            return None
        res.state = state
        self.db.commit()
        self.db.refresh(res)
        return ReservationSchema.model_validate(res)

    def create_order(self, reservation_id: int) -> OrderSchema:
        order = OrderORM(
            reservation_id=reservation_id,
            state=OrderState.CONFIRMED,
        )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return OrderSchema.model_validate(order)

    def get_order(self, order_id: int) -> Optional[OrderSchema]:
        order = self.db.query(OrderORM).filter(OrderORM.id == order_id).first()
        return OrderSchema.model_validate(order) if order else None

    def get_order_by_reservation_id(self, reservation_id: int) -> Optional[OrderSchema]:
        order = self.db.query(OrderORM).filter(
            OrderORM.reservation_id == reservation_id
        ).first()
        return OrderSchema.model_validate(order) if order else None

    def list_orders(self, limit: int = 10, offset: int = 0) -> tuple[list[OrderSchema], int]:
        total = self.db.query(OrderORM).count()
        orders = self.db.query(OrderORM).offset(offset).limit(limit).all()
        return [OrderSchema.model_validate(o) for o in orders], total
