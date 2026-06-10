from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .models import (
    OrderModel,
    OrderState,
    ReservationModel,
    ReservationState,
    SKUModel,
)


class Repository:
    def __init__(self, session: Session):
        self.session = session

    # SKU operations

    def create_sku(self, name: str, initial_stock: int = 0) -> SKUModel:
        sku = SKUModel(name=name, stock=initial_stock)
        self.session.add(sku)
        self.session.commit()
        return sku

    def get_sku(self, sku_id: int) -> Optional[SKUModel]:
        return self.session.query(SKUModel).filter(SKUModel.id == sku_id).first()

    def get_sku_by_name(self, name: str) -> Optional[SKUModel]:
        return self.session.query(SKUModel).filter(SKUModel.name == name).first()

    def adjust_stock(self, sku_id: int, delta: int) -> Optional[SKUModel]:
        sku = self.get_sku(sku_id)
        if not sku:
            return None
        sku.stock += delta
        self.session.commit()
        return sku

    # Reservation operations

    def create_reservation(
        self, sku_id: int, quantity: int, idempotency_key: str, expires_at: datetime
    ) -> ReservationModel:
        reservation = ReservationModel(
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            state=ReservationState.PENDING.value,
            expires_at=expires_at,
        )
        self.session.add(reservation)
        self.session.commit()
        return reservation

    def get_reservation(self, reservation_id: int) -> Optional[ReservationModel]:
        return (
            self.session.query(ReservationModel)
            .filter(ReservationModel.id == reservation_id)
            .first()
        )

    def get_reservation_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[ReservationModel]:
        return (
            self.session.query(ReservationModel)
            .filter(ReservationModel.idempotency_key == idempotency_key)
            .first()
        )

    def update_reservation_state(
        self, reservation_id: int, new_state: ReservationState
    ) -> Optional[ReservationModel]:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            return None
        reservation.state = new_state.value
        self.session.commit()
        return reservation

    # Order operations

    def create_order(
        self, reservation_id: int, sku_id: int, quantity: int
    ) -> OrderModel:
        order = OrderModel(
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            state=OrderState.PENDING.value,
        )
        self.session.add(order)
        self.session.commit()
        return order

    def get_order(self, order_id: int) -> Optional[OrderModel]:
        return self.session.query(OrderModel).filter(OrderModel.id == order_id).first()

    def get_orders_paginated(
        self, limit: int = 10, cursor: Optional[int] = None
    ) -> tuple[list[OrderModel], Optional[int]]:
        query = self.session.query(OrderModel).order_by(OrderModel.id)

        if cursor is not None:
            query = query.filter(OrderModel.id > cursor)

        items = query.limit(limit + 1).all()

        next_cursor = None
        if len(items) > limit:
            next_cursor = items[limit].id
            items = items[:limit]

        return items, next_cursor

    def get_orders_by_reservation(self, reservation_id: int) -> list[OrderModel]:
        return (
            self.session.query(OrderModel)
            .filter(OrderModel.reservation_id == reservation_id)
            .all()
        )

    def update_order_state(
        self, order_id: int, new_state: OrderState
    ) -> Optional[OrderModel]:
        order = self.get_order(order_id)
        if not order:
            return None
        order.state = new_state.value
        self.session.commit()
        return order
