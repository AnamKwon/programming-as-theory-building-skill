"""Repository layer for database access."""

import sqlite3
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .models import SKU, Reservation, Order, ReservationStatus


class SKURepository:
    def __init__(self, session: Session):
        self.session = session

    def create_sku(self, sku: str, initial_stock: int) -> SKU:
        sku_record = SKU(sku=sku, initial_stock=initial_stock, available_stock=initial_stock)
        self.session.add(sku_record)
        self.session.commit()
        self.session.refresh(sku_record)
        return sku_record

    def get_sku_by_code(self, sku: str) -> Optional[SKU]:
        return self.session.query(SKU).filter(SKU.sku == sku).first()

    def adjust_stock(self, sku: str, amount: int) -> Optional[SKU]:
        sku_record = self.get_sku_by_code(sku)
        if sku_record:
            sku_record.available_stock += amount
            self.session.commit()
            self.session.refresh(sku_record)
        return sku_record


class ReservationRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> Reservation:
        now = datetime.utcnow()
        reservation = Reservation(
            sku=sku,
            quantity=quantity,
            idempotency_key=idempotency_key,
            status=ReservationStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        self.session.add(reservation)
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    def get_reservation_by_id(self, reservation_id: int) -> Optional[Reservation]:
        return self.session.query(Reservation).filter(Reservation.id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, key: str) -> Optional[Reservation]:
        return (
            self.session.query(Reservation)
            .filter(Reservation.idempotency_key == key)
            .first()
        )

    def update_reservation_status(self, reservation_id: int, status: str) -> Optional[Reservation]:
        reservation = self.get_reservation_by_id(reservation_id)
        if reservation:
            reservation.status = status
            reservation.updated_at = datetime.utcnow()
            self.session.commit()
            self.session.refresh(reservation)
        return reservation


class OrderRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_order(self, reservation_id: int) -> Order:
        order = Order(reservation_id=reservation_id, created_at=datetime.utcnow())
        self.session.add(order)
        self.session.commit()
        self.session.refresh(order)
        return order

    def get_orders_paginated(self, page: int = 1, size: int = 10) -> tuple[list[Order], int]:
        total = self.session.query(Order).count()
        offset = (page - 1) * size
        orders = self.session.query(Order).offset(offset).limit(size).all()
        return orders, total
