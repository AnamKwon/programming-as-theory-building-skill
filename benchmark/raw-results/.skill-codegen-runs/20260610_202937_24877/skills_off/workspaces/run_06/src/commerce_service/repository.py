"""Data access layer for commerce service."""

from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import OrderModel, ReservationModel, SKUModel


class Repository:
    def __init__(self, session: Session):
        self.session = session

    def create_sku(self, sku: str, initial_stock: int) -> SKUModel:
        sku_model = SKUModel(sku=sku, available_stock=initial_stock)
        self.session.add(sku_model)
        self.session.commit()
        self.session.refresh(sku_model)
        return sku_model

    def get_sku_by_sku(self, sku: str) -> Optional[SKUModel]:
        return self.session.query(SKUModel).filter(SKUModel.sku == sku).first()

    def update_sku_stock(self, sku: str, amount: int) -> Optional[SKUModel]:
        sku_model = self.get_sku_by_sku(sku)
        if not sku_model:
            return None
        sku_model.available_stock += amount
        self.session.commit()
        self.session.refresh(sku_model)
        return sku_model

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> ReservationModel:
        reservation = ReservationModel(
            sku=sku, quantity=quantity, idempotency_key=idempotency_key
        )
        self.session.add(reservation)
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    def get_reservation_by_id(self, reservation_id: int) -> Optional[ReservationModel]:
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

    def update_reservation_status(
        self, reservation_id: int, status: str
    ) -> Optional[ReservationModel]:
        reservation = self.get_reservation_by_id(reservation_id)
        if not reservation:
            return None
        reservation.status = status
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    def create_order(self, reservation_id: int, sku: str, quantity: int) -> OrderModel:
        order = OrderModel(reservation_id=reservation_id, sku=sku, quantity=quantity)
        self.session.add(order)
        self.session.commit()
        self.session.refresh(order)
        return order

    def get_orders_paginated(
        self, page: int = 1, size: int = 10
    ) -> tuple[list[OrderModel], int]:
        total = self.session.query(func.count(OrderModel.id)).scalar()
        offset = (page - 1) * size
        orders = (
            self.session.query(OrderModel)
            .order_by(OrderModel.created_at.desc())
            .offset(offset)
            .limit(size)
            .all()
        )
        return orders, total
