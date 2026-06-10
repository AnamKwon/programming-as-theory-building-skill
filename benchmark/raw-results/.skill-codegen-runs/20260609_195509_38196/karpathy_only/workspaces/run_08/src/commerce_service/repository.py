from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_

from .models import (
    SKUModel,
    ReservationModel,
    OrderModel,
    ReservationStatus,
    OrderStatus,
)


class Repository:
    def __init__(self, db: Session):
        self.db = db

    # SKU operations
    def create_sku(self, sku_id: str, name: str, initial_stock: int) -> SKUModel:
        sku = SKUModel(sku_id=sku_id, name=name, available_stock=initial_stock)
        self.db.add(sku)
        self.db.commit()
        self.db.refresh(sku)
        return sku

    def get_sku(self, sku_id: str) -> Optional[SKUModel]:
        return self.db.query(SKUModel).filter(SKUModel.sku_id == sku_id).first()

    def adjust_stock(self, sku_id: str, adjustment: int) -> SKUModel:
        sku = self.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        sku.available_stock += adjustment
        self.db.commit()
        self.db.refresh(sku)
        return sku

    # Reservation operations
    def create_reservation(
        self,
        reservation_id: str,
        sku_id: str,
        customer_id: str,
        quantity: int,
        expires_at: datetime,
        idempotency_key: Optional[str] = None,
    ) -> ReservationModel:
        reservation = ReservationModel(
            reservation_id=reservation_id,
            sku_id=sku_id,
            customer_id=customer_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def get_reservation(self, reservation_id: str) -> Optional[ReservationModel]:
        return self.db.query(ReservationModel).filter(
            ReservationModel.reservation_id == reservation_id
        ).first()

    def get_reservation_by_idempotency_key(self, key: str) -> Optional[ReservationModel]:
        return self.db.query(ReservationModel).filter(
            ReservationModel.idempotency_key == key
        ).first()

    def update_reservation_status(
        self, reservation_id: str, status: ReservationStatus
    ) -> ReservationModel:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")
        reservation.status = status
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    # Order operations
    def create_order(
        self,
        order_id: str,
        reservation_id: str,
        sku_id: str,
        customer_id: str,
        quantity: int,
    ) -> OrderModel:
        order = OrderModel(
            order_id=order_id,
            reservation_id=reservation_id,
            sku_id=sku_id,
            customer_id=customer_id,
            quantity=quantity,
            status=OrderStatus.PENDING,
        )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def get_order(self, order_id: str) -> Optional[OrderModel]:
        return self.db.query(OrderModel).filter(OrderModel.order_id == order_id).first()

    def list_orders(self, customer_id: str, skip: int = 0, limit: int = 10) -> List[OrderModel]:
        return self.db.query(OrderModel).filter(
            OrderModel.customer_id == customer_id
        ).offset(skip).limit(limit).all()

    def count_orders(self, customer_id: str) -> int:
        return self.db.query(OrderModel).filter(
            OrderModel.customer_id == customer_id
        ).count()

    def update_sku_reserved_stock(self, sku_id: str, quantity: int) -> None:
        sku = self.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        sku.reserved_stock += quantity
        self.db.commit()
