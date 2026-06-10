from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from .models import (
    SKUModel,
    StockModel,
    ReservationModel,
    OrderModel,
    ReservationStatus,
    OrderStatus,
)


class Repository:
    def __init__(self, session: Session):
        self.session = session

    # SKU operations
    def create_sku(self, sku_id: str, name: str, description: Optional[str]) -> SKUModel:
        sku = SKUModel(id=sku_id, name=name, description=description)
        self.session.add(sku)
        self.session.flush()
        return sku

    def get_sku(self, sku_id: str) -> Optional[SKUModel]:
        return self.session.query(SKUModel).filter(SKUModel.id == sku_id).first()

    # Stock operations
    def get_stock(self, sku_id: str) -> Optional[StockModel]:
        return self.session.query(StockModel).filter(StockModel.sku_id == sku_id).first()

    def get_or_create_stock(self, sku_id: str) -> StockModel:
        stock = self.get_stock(sku_id)
        if stock is None:
            stock = StockModel(sku_id=sku_id, available=0, reserved=0)
            self.session.add(stock)
            self.session.flush()
        return stock

    def update_stock(self, sku_id: str, available_delta: int, reserved_delta: int = 0) -> StockModel:
        stock = self.get_or_create_stock(sku_id)
        stock.available += available_delta
        stock.reserved += reserved_delta
        stock.updated_at = datetime.utcnow()
        self.session.flush()
        return stock

    # Reservation operations
    def create_reservation(
        self, res_id: str, sku_id: str, quantity: int, expires_at: datetime, idempotency_key: Optional[str]
    ) -> ReservationModel:
        reservation = ReservationModel(
            id=res_id,
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )
        self.session.add(reservation)
        self.session.flush()
        return reservation

    def get_reservation(self, res_id: str) -> Optional[ReservationModel]:
        return self.session.query(ReservationModel).filter(ReservationModel.id == res_id).first()

    def get_reservation_by_idempotency_key(self, key: str) -> Optional[ReservationModel]:
        return self.session.query(ReservationModel).filter(ReservationModel.idempotency_key == key).first()

    def update_reservation_status(self, res_id: str, status: ReservationStatus) -> ReservationModel:
        reservation = self.get_reservation(res_id)
        reservation.status = status
        reservation.updated_at = datetime.utcnow()
        self.session.flush()
        return reservation

    def get_expired_reservations(self, now: datetime) -> list[ReservationModel]:
        return (
            self.session.query(ReservationModel)
            .filter(
                ReservationModel.status == ReservationStatus.ACTIVE,
                ReservationModel.expires_at < now,
            )
            .all()
        )

    # Order operations
    def create_order(
        self, order_id: str, reservation_id: str, sku_id: str, quantity: int
    ) -> OrderModel:
        order = OrderModel(
            id=order_id,
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
        )
        self.session.add(order)
        self.session.flush()
        return order

    def get_order(self, order_id: str) -> Optional[OrderModel]:
        return self.session.query(OrderModel).filter(OrderModel.id == order_id).first()

    def get_orders_paginated(self, cursor: Optional[str], limit: int = 20) -> tuple[list[OrderModel], Optional[str]]:
        query = self.session.query(OrderModel).order_by(desc(OrderModel.created_at))

        if cursor:
            # Cursor is the order ID; fetch orders created before this one
            cursor_order = self.get_order(cursor)
            if cursor_order:
                query = query.filter(OrderModel.created_at < cursor_order.created_at)

        orders = query.limit(limit + 1).all()
        next_cursor = None
        if len(orders) > limit:
            next_cursor = orders[limit].id
            orders = orders[:limit]

        return orders, next_cursor

    def update_order_status(self, order_id: str, status: OrderStatus) -> OrderModel:
        order = self.get_order(order_id)
        order.status = status
        order.updated_at = datetime.utcnow()
        self.session.flush()
        return order

    def commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()
