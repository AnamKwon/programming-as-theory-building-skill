from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_

from commerce_service.models import SKU, Reservation, Order, ReservationStatus, OrderStatus


class SKURepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, sku_id: int) -> Optional[SKU]:
        return self.db.query(SKU).filter(SKU.id == sku_id).first()

    def get_by_code(self, code: str) -> Optional[SKU]:
        return self.db.query(SKU).filter(SKU.code == code).first()

    def create(self, code: str, stock: int) -> SKU:
        sku = SKU(code=code, stock=stock)
        self.db.add(sku)
        self.db.commit()
        self.db.refresh(sku)
        return sku

    def adjust_stock(self, sku_id: int, quantity: int) -> Optional[SKU]:
        sku = self.get_by_id(sku_id)
        if not sku:
            return None
        sku.stock += quantity
        self.db.commit()
        self.db.refresh(sku)
        return sku


class ReservationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, reservation_id: int) -> Optional[Reservation]:
        return self.db.query(Reservation).filter(Reservation.id == reservation_id).first()

    def get_by_idempotency_key(self, key: str) -> Optional[Reservation]:
        return self.db.query(Reservation).filter(Reservation.idempotency_key == key).first()

    def create(
        self,
        sku_id: int,
        quantity: int,
        idempotency_key: str,
        expires_at: datetime,
    ) -> Reservation:
        reservation = Reservation(
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def confirm(self, reservation_id: int) -> Optional[Reservation]:
        reservation = self.get_by_id(reservation_id)
        if not reservation:
            return None
        reservation.status = ReservationStatus.CONFIRMED
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def cancel(self, reservation_id: int) -> Optional[Reservation]:
        reservation = self.get_by_id(reservation_id)
        if not reservation:
            return None
        if reservation.status == ReservationStatus.PENDING:
            reservation.status = ReservationStatus.CANCELLED
            sku = reservation.sku
            sku.reserved_count -= reservation.quantity
            self.db.commit()
            self.db.refresh(reservation)
        return reservation

    def expire_stale(self) -> int:
        now = datetime.utcnow()
        expired = self.db.query(Reservation).filter(
            and_(
                Reservation.expires_at <= now,
                Reservation.status == ReservationStatus.PENDING,
            )
        ).all()

        count = 0
        for res in expired:
            res.status = ReservationStatus.EXPIRED
            res.sku.reserved_count -= res.quantity
            count += 1

        if count > 0:
            self.db.commit()

        return count


class OrderRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, order_id: int) -> Optional[Order]:
        return self.db.query(Order).filter(Order.id == order_id).first()

    def get_by_reservation_id(self, reservation_id: int) -> Optional[Order]:
        return self.db.query(Order).filter(Order.reservation_id == reservation_id).first()

    def create(
        self,
        reservation_id: int,
        sku_id: int,
        quantity: int,
    ) -> Order:
        order = Order(
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            status=OrderStatus.RESERVED,
        )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def list_paginated(self, skip: int = 0, limit: int = 10) -> tuple[List[Order], int]:
        total = self.db.query(Order).count()
        orders = self.db.query(Order).offset(skip).limit(limit).all()
        return orders, total
