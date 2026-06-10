from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Order, Reservation, ReservationStatus, SKU, Stock


class Repository:
    def __init__(self, session: Session):
        self.session = session

    # SKU operations

    def get_sku(self, sku_code: str) -> Optional[SKU]:
        return self.session.query(SKU).filter(SKU.sku_code == sku_code).first()

    def create_sku(self, sku_code: str, description: Optional[str]) -> SKU:
        sku = SKU(sku_code=sku_code, description=description)
        self.session.add(sku)
        self.session.commit()
        return sku

    # Stock operations

    def get_stock(self, sku_code: str) -> Optional[Stock]:
        return self.session.query(Stock).filter(Stock.sku_code == sku_code).first()

    def create_stock(self, sku_code: str, quantity: int) -> Stock:
        stock = Stock(sku_code=sku_code, quantity=quantity, reserved_quantity=0)
        self.session.add(stock)
        self.session.commit()
        return stock

    def update_stock(self, sku_code: str, quantity_delta: int):
        stock = self.get_stock(sku_code)
        if stock:
            stock.quantity += quantity_delta
            stock.last_updated = datetime.now(timezone.utc)
            self.session.commit()

    def reserve_stock(self, sku_code: str, quantity: int):
        stock = self.get_stock(sku_code)
        if stock:
            stock.reserved_quantity += quantity
            stock.last_updated = datetime.now(timezone.utc)
            self.session.commit()

    def release_reservation(self, sku_code: str, quantity: int):
        stock = self.get_stock(sku_code)
        if stock:
            stock.reserved_quantity = max(0, stock.reserved_quantity - quantity)
            stock.last_updated = datetime.now(timezone.utc)
            self.session.commit()

    def confirm_reservation_stock(self, sku_code: str, quantity: int):
        stock = self.get_stock(sku_code)
        if stock:
            stock.quantity -= quantity
            stock.reserved_quantity = max(0, stock.reserved_quantity - quantity)
            stock.last_updated = datetime.now(timezone.utc)
            self.session.commit()

    # Reservation operations

    def get_reservation(self, reservation_id: str) -> Optional[Reservation]:
        return self.session.query(Reservation).filter(Reservation.reservation_id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, sku_code: str, idempotency_key: str) -> Optional[Reservation]:
        return (
            self.session.query(Reservation)
            .filter(Reservation.sku_code == sku_code, Reservation.idempotency_key == idempotency_key)
            .first()
        )

    def create_reservation(
        self, reservation_id: str, sku_code: str, quantity: int, idempotency_key: str, expires_at: datetime
    ) -> Reservation:
        reservation = Reservation(
            reservation_id=reservation_id,
            sku_code=sku_code,
            quantity=quantity,
            idempotency_key=idempotency_key,
            status=ReservationStatus.PENDING,
            expires_at=expires_at,
        )
        self.session.add(reservation)
        self.session.commit()
        return reservation

    def update_reservation_status(self, reservation_id: str, status: ReservationStatus, confirmed_at: Optional[datetime] = None):
        reservation = self.get_reservation(reservation_id)
        if reservation:
            reservation.status = status
            if confirmed_at:
                reservation.confirmed_at = confirmed_at
            self.session.commit()

    def get_expired_reservations(self, now: datetime) -> list[Reservation]:
        return (
            self.session.query(Reservation)
            .filter(
                Reservation.status == ReservationStatus.PENDING,
                Reservation.expires_at <= now,
            )
            .all()
        )

    # Order operations

    def get_order(self, order_id: str) -> Optional[Order]:
        return self.session.query(Order).filter(Order.order_id == order_id).first()

    def create_order(self, order_id: str, sku_code: str, quantity: int, created_from_reservation_id: Optional[str] = None) -> Order:
        order = Order(
            order_id=order_id,
            sku_code=sku_code,
            quantity=quantity,
            created_from_reservation_id=created_from_reservation_id,
        )
        self.session.add(order)
        self.session.commit()
        return order

    def update_order_status(self, order_id: str, status: str):
        order = self.get_order(order_id)
        if order:
            order.status = status
            self.session.commit()

    def get_orders_paginated(self, page: int, page_size: int) -> tuple[list[Order], int]:
        query = self.session.query(Order)
        total = query.count()
        orders = query.offset((page - 1) * page_size).limit(page_size).all()
        return orders, total
