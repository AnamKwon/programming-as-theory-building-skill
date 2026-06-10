from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Order, OrderItem, Reservation, SKU


class SKURepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, sku_id: str, name: str, initial_stock: int) -> SKU:
        sku = SKU(id=sku_id, name=name, available_stock=initial_stock)
        self.session.add(sku)
        self.session.commit()
        return sku

    def get(self, sku_id: str) -> Optional[SKU]:
        return self.session.query(SKU).filter(SKU.id == sku_id).first()

    def update_available_stock(self, sku_id: str, delta: int) -> None:
        sku = self.get(sku_id)
        if sku:
            sku.available_stock += delta
            self.session.commit()

    def update_reserved_stock(self, sku_id: str, delta: int) -> None:
        sku = self.get(sku_id)
        if sku:
            sku.reserved_stock += delta
            self.session.commit()


class ReservationRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        expires_at: datetime,
        idempotency_key: Optional[str] = None,
    ) -> Reservation:
        reservation = Reservation(
            id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            created_at=datetime.utcnow(),
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )
        self.session.add(reservation)
        self.session.commit()
        return reservation

    def get(self, reservation_id: str) -> Optional[Reservation]:
        return self.session.query(Reservation).filter(
            Reservation.id == reservation_id
        ).first()

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[Reservation]:
        return self.session.query(Reservation).filter(
            Reservation.idempotency_key == idempotency_key
        ).first()

    def update_status(self, reservation_id: str, status: str) -> None:
        reservation = self.get(reservation_id)
        if reservation:
            reservation.status = status
            self.session.commit()

    def get_pending_by_sku(self, sku_id: str) -> list[Reservation]:
        return self.session.query(Reservation).filter(
            Reservation.sku_id == sku_id,
            Reservation.status == "pending",
        ).all()


class OrderRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, order_id: str) -> Order:
        now = datetime.utcnow()
        order = Order(id=order_id, status="pending", created_at=now, updated_at=now)
        self.session.add(order)
        self.session.commit()
        return order

    def get(self, order_id: str) -> Optional[Order]:
        return self.session.query(Order).filter(Order.id == order_id).first()

    def update_status(self, order_id: str, status: str) -> None:
        order = self.get(order_id)
        if order:
            order.status = status
            order.updated_at = datetime.utcnow()
            self.session.commit()

    def add_item(
        self, order_id: str, item_id: str, sku_id: str, quantity: int
    ) -> OrderItem:
        item = OrderItem(id=item_id, order_id=order_id, sku_id=sku_id, quantity=quantity)
        self.session.add(item)
        self.session.commit()
        return item

    def list_paginated(self, page: int = 1, page_size: int = 10) -> tuple[list[Order], int]:
        total = self.session.query(func.count(Order.id)).scalar() or 0
        offset = (page - 1) * page_size
        orders = self.session.query(Order).offset(offset).limit(page_size).all()
        return orders, total
