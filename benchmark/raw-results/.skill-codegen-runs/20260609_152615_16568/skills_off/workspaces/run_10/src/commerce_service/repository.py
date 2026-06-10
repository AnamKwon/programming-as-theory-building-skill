from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from commerce_service.models import (
    SKUModel,
    ReservationModel,
    OrderModel,
    ReservationStatus,
)


class Repository:
    def __init__(self, db: Session):
        self.db = db

    # SKU operations

    def create_sku(self, sku_code: str) -> SKUModel:
        sku = SKUModel(sku_code=sku_code, stock_available=0)
        self.db.add(sku)
        self.db.commit()
        self.db.refresh(sku)
        return sku

    def get_sku(self, sku_id: int) -> Optional[SKUModel]:
        return self.db.query(SKUModel).filter(SKUModel.id == sku_id).first()

    def get_sku_by_code(self, sku_code: str) -> Optional[SKUModel]:
        return self.db.query(SKUModel).filter(SKUModel.sku_code == sku_code).first()

    def update_stock(self, sku_id: int, delta: int) -> Optional[SKUModel]:
        sku = self.get_sku(sku_id)
        if not sku:
            return None
        sku.stock_available += delta
        self.db.commit()
        self.db.refresh(sku)
        return sku

    # Reservation operations

    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        idempotency_key: Optional[str],
    ) -> ReservationModel:
        reservation = ReservationModel(
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            status=ReservationStatus.PENDING,
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def get_reservation(self, reservation_id: int) -> Optional[ReservationModel]:
        return self.db.query(ReservationModel).filter(ReservationModel.id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, key: str) -> Optional[ReservationModel]:
        return self.db.query(ReservationModel).filter(
            ReservationModel.idempotency_key == key
        ).first()

    def update_reservation_status(
        self,
        reservation_id: int,
        status: ReservationStatus,
    ) -> Optional[ReservationModel]:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            return None
        reservation.status = status
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def update_reservation_order(
        self,
        reservation_id: int,
        order_id: int,
    ) -> Optional[ReservationModel]:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            return None
        reservation.order_id = order_id
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    # Order operations

    def create_order(self) -> OrderModel:
        order = OrderModel()
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def get_order(self, order_id: int) -> Optional[OrderModel]:
        return self.db.query(OrderModel).filter(OrderModel.id == order_id).first()

    def list_orders(self, offset: int = 0, limit: int = 20) -> tuple[list[OrderModel], int]:
        total = self.db.query(func.count(OrderModel.id)).scalar() or 0
        orders = (
            self.db.query(OrderModel)
            .order_by(OrderModel.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return orders, total
