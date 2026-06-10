from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from .models import OrderModel, ReservationModel, SKUModel


class SKURepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, sku_id: int) -> SKUModel | None:
        return self.db.query(SKUModel).filter(SKUModel.id == sku_id).first()

    def get_by_code(self, code: str) -> SKUModel | None:
        return self.db.query(SKUModel).filter(SKUModel.code == code).first()

    def create(self, code: str, price: Decimal, stock_quantity: int) -> SKUModel:
        sku = SKUModel(code=code, price=price, stock_quantity=stock_quantity)
        self.db.add(sku)
        self.db.commit()
        self.db.refresh(sku)
        return sku

    def update_stock(self, sku_id: int, delta: int) -> SKUModel:
        sku = self.get_by_id(sku_id)
        if sku:
            sku.stock_quantity += delta
            self.db.commit()
            self.db.refresh(sku)
        return sku


class ReservationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, reservation_id: int) -> ReservationModel | None:
        return self.db.query(ReservationModel).filter(
            ReservationModel.id == reservation_id
        ).first()

    def get_by_idempotency_key(self, key: str) -> ReservationModel | None:
        return self.db.query(ReservationModel).filter(
            ReservationModel.idempotency_key == key
        ).first()

    def create(
        self,
        sku_id: int,
        quantity: int,
        customer_id: str,
        expires_at: datetime,
        idempotency_key: str | None = None,
    ) -> ReservationModel:
        reservation = ReservationModel(
            sku_id=sku_id,
            quantity=quantity,
            customer_id=customer_id,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
            status="pending",
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def update_status(self, reservation_id: int, status: str) -> ReservationModel | None:
        reservation = self.get_by_id(reservation_id)
        if reservation:
            reservation.status = status
            self.db.commit()
            self.db.refresh(reservation)
        return reservation


class OrderRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, sku_id: int, quantity: int, customer_id: str) -> OrderModel:
        order = OrderModel(sku_id=sku_id, quantity=quantity, customer_id=customer_id)
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def list_paginated(self, offset: int = 0, limit: int = 20) -> tuple[list[OrderModel], int]:
        total = self.db.query(OrderModel).count()
        items = (
            self.db.query(OrderModel)
            .order_by(OrderModel.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return items, total
