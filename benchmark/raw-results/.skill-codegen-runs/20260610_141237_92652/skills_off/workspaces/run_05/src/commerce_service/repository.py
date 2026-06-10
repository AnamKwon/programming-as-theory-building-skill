from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .models import SKUModel, ReservationModel, OrderModel


class Repository:
    def __init__(self, db: Session):
        self.db = db

    # SKU operations
    def create_sku(self, sku: str, initial_stock: int) -> SKUModel:
        sku_model = SKUModel(sku=sku, available_stock=initial_stock)
        self.db.add(sku_model)
        self.db.commit()
        self.db.refresh(sku_model)
        return sku_model

    def get_sku_by_code(self, sku: str) -> Optional[SKUModel]:
        return self.db.query(SKUModel).filter(SKUModel.sku == sku).first()

    def update_sku_stock(self, sku: str, amount: int) -> Optional[SKUModel]:
        sku_model = self.get_sku_by_code(sku)
        if sku_model is None:
            return None
        sku_model.available_stock += amount
        self.db.commit()
        self.db.refresh(sku_model)
        return sku_model

    # Reservation operations
    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: Optional[str] = None
    ) -> ReservationModel:
        reservation = ReservationModel(
            sku=sku, quantity=quantity, status="PENDING", idempotency_key=idempotency_key
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def get_reservation_by_id(self, reservation_id: int) -> Optional[ReservationModel]:
        return self.db.query(ReservationModel).filter(ReservationModel.id == reservation_id).first()

    def get_reservation_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[ReservationModel]:
        return (
            self.db.query(ReservationModel)
            .filter(ReservationModel.idempotency_key == idempotency_key)
            .first()
        )

    def update_reservation_status(self, reservation_id: int, status: str) -> Optional[ReservationModel]:
        reservation = self.get_reservation_by_id(reservation_id)
        if reservation is None:
            return None
        reservation.status = status
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    # Order operations
    def create_order(self, reservation_id: int, sku: str, quantity: int) -> OrderModel:
        order = OrderModel(reservation_id=reservation_id, sku=sku, quantity=quantity)
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def get_orders_paginated(self, page: int = 1, size: int = 10) -> tuple[list[OrderModel], int]:
        query = self.db.query(OrderModel)
        total = query.count()
        offset = (page - 1) * size
        orders = query.offset(offset).limit(size).all()
        return orders, total

    def get_order_by_reservation_id(self, reservation_id: int) -> Optional[OrderModel]:
        return self.db.query(OrderModel).filter(OrderModel.reservation_id == reservation_id).first()
