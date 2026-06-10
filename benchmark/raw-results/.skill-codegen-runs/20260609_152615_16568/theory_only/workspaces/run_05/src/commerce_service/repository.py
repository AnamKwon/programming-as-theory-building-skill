from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime, timezone
from commerce_service.models import SKU, Stock, Reservation, Order, ReservationState


class Repository:
    def __init__(self, db: Session):
        self.db = db

    def create_sku(self, sku_id: str, name: str) -> SKU:
        sku = SKU(id=sku_id, name=name)
        self.db.add(sku)
        self.db.commit()
        return sku

    def get_sku(self, sku_id: str) -> SKU | None:
        return self.db.query(SKU).filter(SKU.id == sku_id).first()

    def create_stock(self, sku_id: str, quantity: int) -> Stock:
        stock = Stock(sku_id=sku_id, quantity=quantity)
        self.db.add(stock)
        self.db.commit()
        return stock

    def get_stock(self, sku_id: str) -> Stock | None:
        return self.db.query(Stock).filter(Stock.sku_id == sku_id).first()

    def update_stock(self, sku_id: str, quantity_delta: int) -> Stock:
        stock = self.get_stock(sku_id)
        if stock is None:
            raise ValueError(f"Stock not found for SKU {sku_id}")
        stock.quantity += quantity_delta
        stock.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        return stock

    def create_reservation(self, reservation_id: str, sku_id: str, quantity: int, idempotency_key: str, expires_at: datetime) -> Reservation:
        reservation = Reservation(
            id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
        )
        self.db.add(reservation)
        self.db.commit()
        return reservation

    def get_reservation(self, reservation_id: str) -> Reservation | None:
        return self.db.query(Reservation).filter(Reservation.id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Reservation | None:
        return self.db.query(Reservation).filter(Reservation.idempotency_key == idempotency_key).first()

    def update_reservation_state(self, reservation_id: str, state: ReservationState, state_changed_at: datetime | None = None) -> Reservation:
        reservation = self.get_reservation(reservation_id)
        if reservation is None:
            raise ValueError(f"Reservation not found: {reservation_id}")
        reservation.state = state
        if state == ReservationState.CONFIRMED and state_changed_at:
            reservation.confirmed_at = state_changed_at
        elif state == ReservationState.CANCELLED and state_changed_at:
            reservation.cancelled_at = state_changed_at
        self.db.commit()
        return reservation

    def create_order(self, order_id: str, reservation_id: str, sku_id: str, quantity: int) -> Order:
        order = Order(
            id=order_id,
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
        )
        self.db.add(order)
        self.db.commit()
        return order

    def get_order(self, order_id: str) -> Order | None:
        return self.db.query(Order).filter(Order.id == order_id).first()

    def get_orders_paginated(self, skip: int = 0, limit: int = 10) -> tuple[list[Order], int]:
        query = self.db.query(Order)
        total = query.count()
        orders = query.offset(skip).limit(limit).all()
        return orders, total

    def update_order_state(self, order_id: str, state: ReservationState, state_changed_at: datetime | None = None) -> Order:
        order = self.get_order(order_id)
        if order is None:
            raise ValueError(f"Order not found: {order_id}")
        order.state = state
        if state == ReservationState.CONFIRMED and state_changed_at:
            order.confirmed_at = state_changed_at
        elif state == ReservationState.CANCELLED and state_changed_at:
            order.cancelled_at = state_changed_at
        self.db.commit()
        return order
