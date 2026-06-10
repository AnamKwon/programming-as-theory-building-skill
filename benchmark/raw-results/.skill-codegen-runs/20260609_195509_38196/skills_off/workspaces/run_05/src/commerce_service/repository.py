import base64
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .models import (
    IdempotencyOrm,
    OrderOrm,
    OrderState,
    ReservationOrm,
    SKUOrm,
)


class Repository:
    def __init__(self, session: Session):
        self.session = session

    def create_sku(self, sku_id: str, initial_stock: int) -> SKUOrm:
        sku = SKUOrm(sku_id=sku_id, stock_level=initial_stock)
        self.session.add(sku)
        self.session.commit()
        return sku

    def get_sku(self, sku_id: str) -> Optional[SKUOrm]:
        return self.session.query(SKUOrm).filter(SKUOrm.sku_id == sku_id).first()

    def update_stock(self, sku_id: str, quantity_delta: int) -> SKUOrm:
        sku = self.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        sku.stock_level += quantity_delta
        self.session.commit()
        return sku

    def create_reservation(
        self, reservation_id: str, sku_id: str, quantity: int, expires_at: datetime
    ) -> ReservationOrm:
        reservation = ReservationOrm(
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            state=OrderState.PENDING,
        )
        self.session.add(reservation)
        self.session.commit()
        return reservation

    def get_reservation(self, reservation_id: str) -> Optional[ReservationOrm]:
        return self.session.query(ReservationOrm).filter(
            ReservationOrm.reservation_id == reservation_id
        ).first()

    def update_reservation_state(
        self, reservation_id: str, new_state: OrderState
    ) -> ReservationOrm:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")
        reservation.state = new_state
        self.session.commit()
        return reservation

    def create_order(
        self,
        order_id: str,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        confirmed_at: datetime,
    ) -> OrderOrm:
        order = OrderOrm(
            order_id=order_id,
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            state=OrderState.CONFIRMED,
            confirmed_at=confirmed_at,
        )
        self.session.add(order)
        self.session.commit()
        return order

    def get_orders_paginated(
        self, limit: int = 10, cursor: Optional[str] = None
    ) -> tuple[list[OrderOrm], bool, Optional[str]]:
        query = self.session.query(OrderOrm).order_by(OrderOrm.created_at.desc())

        offset = 0
        if cursor:
            try:
                offset = int(base64.b64decode(cursor).decode())
            except Exception:
                offset = 0

        total_count = query.count()
        orders = query.offset(offset).limit(limit + 1).all()

        has_more = len(orders) > limit
        if has_more:
            orders = orders[:limit]

        next_cursor = None
        if has_more:
            next_offset = offset + limit
            next_cursor = base64.b64encode(str(next_offset).encode()).decode()

        return orders, has_more, next_cursor

    def get_idempotency_response(self, idempotency_key: str) -> Optional[str]:
        record = self.session.query(IdempotencyOrm).filter(
            IdempotencyOrm.idempotency_key == idempotency_key
        ).first()
        return record.response_data if record else None

    def store_idempotency_response(self, idempotency_key: str, response_data: str) -> None:
        record = IdempotencyOrm(
            idempotency_key=idempotency_key,
            response_data=response_data,
        )
        self.session.add(record)
        self.session.commit()
