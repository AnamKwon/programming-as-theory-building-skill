from datetime import datetime
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from .models import (
    OrderModel,
    OrderReservationModel,
    OrderStatus,
    ReservationModel,
    ReservationStatus,
    SKUModel,
    StockModel,
)


class Repository:
    def __init__(self, db: Session):
        self.db = db

    def create_sku(self, sku_id: str, name: str, description: Optional[str]) -> SKUModel:
        sku = SKUModel(id=sku_id, name=name, description=description)
        stock = StockModel(sku_id=sku_id, quantity=0)
        self.db.add(sku)
        self.db.add(stock)
        self.db.commit()
        self.db.refresh(sku)
        return sku

    def get_sku(self, sku_id: str) -> Optional[SKUModel]:
        return self.db.execute(select(SKUModel).where(SKUModel.id == sku_id)).scalar_one_or_none()

    def get_stock(self, sku_id: str) -> Optional[StockModel]:
        return self.db.execute(select(StockModel).where(StockModel.sku_id == sku_id)).scalar_one_or_none()

    def adjust_stock(self, sku_id: str, delta: int) -> StockModel:
        stock = self.db.execute(select(StockModel).where(StockModel.sku_id == sku_id)).scalar_one()
        stock.quantity += delta
        if stock.quantity < 0:
            stock.quantity = 0
        self.db.commit()
        self.db.refresh(stock)
        return stock

    def create_reservation(
        self,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        idempotency_key: str,
        expires_at: datetime,
    ) -> ReservationModel:
        reservation = ReservationModel(
            id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            status=ReservationStatus.PENDING,
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def get_reservation(self, reservation_id: str) -> Optional[ReservationModel]:
        return self.db.execute(
            select(ReservationModel).where(ReservationModel.id == reservation_id)
        ).scalar_one_or_none()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[ReservationModel]:
        return self.db.execute(
            select(ReservationModel).where(ReservationModel.idempotency_key == idempotency_key)
        ).scalar_one_or_none()

    def update_reservation_status(
        self, reservation_id: str, status: ReservationStatus, confirmed_at: Optional[datetime] = None
    ) -> ReservationModel:
        reservation = self.db.execute(
            select(ReservationModel).where(ReservationModel.id == reservation_id)
        ).scalar_one()
        reservation.status = status
        if confirmed_at:
            reservation.confirmed_at = confirmed_at
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def create_order(self, order_id: str, reservation_ids: list[str]) -> OrderModel:
        order = OrderModel(id=order_id, status=OrderStatus.PENDING)
        self.db.add(order)

        for res_id in reservation_ids:
            order_res = OrderReservationModel(order_id=order_id, reservation_id=res_id)
            self.db.add(order_res)

        self.db.commit()
        self.db.refresh(order)
        return order

    def get_order(self, order_id: str) -> Optional[OrderModel]:
        return self.db.execute(select(OrderModel).where(OrderModel.id == order_id)).scalar_one_or_none()

    def list_orders(self, skip: int = 0, limit: int = 10) -> tuple[list[OrderModel], int]:
        total = self.db.query(OrderModel).count()
        orders = self.db.execute(
            select(OrderModel).offset(skip).limit(limit)
        ).scalars().all()
        return orders, total

    def confirm_order(self, order_id: str, confirmed_at: datetime) -> OrderModel:
        order = self.db.execute(select(OrderModel).where(OrderModel.id == order_id)).scalar_one()
        order.status = OrderStatus.CONFIRMED
        order.confirmed_at = confirmed_at
        self.db.commit()
        self.db.refresh(order)
        return order

    def cancel_order(self, order_id: str) -> OrderModel:
        order = self.db.execute(select(OrderModel).where(OrderModel.id == order_id)).scalar_one()
        order.status = OrderStatus.CANCELLED
        self.db.commit()
        self.db.refresh(order)
        return order

    def cancel_reservation(self, reservation_id: str) -> ReservationModel:
        return self.update_reservation_status(reservation_id, ReservationStatus.CANCELLED)

    def mark_expired_reservations(self) -> int:
        now = datetime.utcnow()
        stmt = select(ReservationModel).where(
            and_(
                ReservationModel.expires_at <= now,
                ReservationModel.status == ReservationStatus.PENDING,
            )
        )
        expired = self.db.execute(stmt).scalars().all()
        for res in expired:
            res.status = ReservationStatus.EXPIRED
        self.db.commit()
        return len(expired)
