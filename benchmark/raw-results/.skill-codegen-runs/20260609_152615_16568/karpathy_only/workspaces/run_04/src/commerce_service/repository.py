from datetime import datetime
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from .models import Order, OrderStatus, Reservation, ReservationStatus, SKU


class SKURepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, code: str, name: str, initial_stock: int) -> SKU:
        sku = SKU(code=code, name=name, available_stock=initial_stock)
        self.db.add(sku)
        self.db.commit()
        self.db.refresh(sku)
        return sku

    def get_by_id(self, sku_id: int) -> Optional[SKU]:
        return self.db.query(SKU).filter(SKU.id == sku_id).first()

    def get_by_code(self, code: str) -> Optional[SKU]:
        return self.db.query(SKU).filter(SKU.code == code).first()

    def adjust_stock(self, sku_id: int, amount: int) -> Optional[SKU]:
        sku = self.get_by_id(sku_id)
        if not sku:
            return None
        sku.available_stock += amount
        self.db.commit()
        self.db.refresh(sku)
        return sku


class ReservationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        sku_id: int,
        amount: int,
        idempotency_key: str,
        expires_at: datetime,
    ) -> Reservation:
        reservation = Reservation(
            sku_id=sku_id,
            amount=amount,
            idempotency_key=idempotency_key,
            status=ReservationStatus.PENDING,
            expires_at=expires_at,
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def get_by_id(self, reservation_id: int) -> Optional[Reservation]:
        return self.db.query(Reservation).filter(Reservation.id == reservation_id).first()

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[Reservation]:
        return (
            self.db.query(Reservation)
            .filter(Reservation.idempotency_key == idempotency_key)
            .first()
        )

    def update_status(self, reservation_id: int, status: ReservationStatus) -> Optional[Reservation]:
        reservation = self.get_by_id(reservation_id)
        if not reservation:
            return None
        reservation.status = status
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def get_reserved_amount_for_sku(self, sku_id: int) -> int:
        result = self.db.query(func.sum(Reservation.amount)).filter(
            and_(
                Reservation.sku_id == sku_id,
                Reservation.status == ReservationStatus.PENDING,
                Reservation.expires_at > func.now(),
            )
        ).scalar()
        return result or 0


class OrderRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, sku_id: int, amount: int) -> Order:
        order = Order(sku_id=sku_id, amount=amount, status=OrderStatus.PENDING)
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def get_by_id(self, order_id: int) -> Optional[Order]:
        return self.db.query(Order).filter(Order.id == order_id).first()

    def update_status(self, order_id: int, status: OrderStatus) -> Optional[Order]:
        order = self.get_by_id(order_id)
        if not order:
            return None
        order.status = status
        self.db.commit()
        self.db.refresh(order)
        return order

    def list_paginated(self, page: int, page_size: int) -> tuple[list[Order], int]:
        total = self.db.query(func.count(Order.id)).scalar()
        orders = (
            self.db.query(Order)
            .order_by(Order.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return orders, total
