from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import OrderModel, ReservationModel, SKUModel


class Repository:
    def __init__(self, session: Session):
        self.session = session

    def create_sku(self, sku_id: str, name: str, total_stock: int) -> SKUModel:
        sku = SKUModel(sku_id=sku_id, name=name, total_stock=total_stock)
        self.session.add(sku)
        self.session.commit()
        return sku

    def get_sku(self, sku_id: str) -> SKUModel | None:
        return self.session.execute(
            select(SKUModel).where(SKUModel.sku_id == sku_id)
        ).scalar_one_or_none()

    def update_sku_stock(self, sku_id: str, total_adjustment: int) -> SKUModel | None:
        sku = self.get_sku(sku_id)
        if not sku:
            return None
        sku.total_stock += total_adjustment
        self.session.commit()
        return sku

    def create_reservation(
        self,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        idempotency_key: str,
        expires_at: datetime,
    ) -> ReservationModel:
        reservation = ReservationModel(
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
        )
        self.session.add(reservation)
        self.session.commit()
        return reservation

    def get_reservation(self, reservation_id: str) -> ReservationModel | None:
        return self.session.execute(
            select(ReservationModel).where(ReservationModel.reservation_id == reservation_id)
        ).scalar_one_or_none()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> ReservationModel | None:
        return self.session.execute(
            select(ReservationModel).where(ReservationModel.idempotency_key == idempotency_key)
        ).scalar_one_or_none()

    def update_reservation_status(self, reservation_id: str, status: str) -> ReservationModel | None:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            return None
        reservation.status = status
        self.session.commit()
        return reservation

    def update_reservation_confirmed(
        self, reservation_id: str, status: str, confirmed_at: datetime
    ) -> ReservationModel | None:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            return None
        reservation.status = status
        reservation.confirmed_at = confirmed_at
        self.session.commit()
        return reservation

    def update_sku_reserved_stock(self, sku_id: str, reserved_adjustment: int) -> SKUModel | None:
        sku = self.get_sku(sku_id)
        if not sku:
            return None
        sku.reserved_stock += reserved_adjustment
        self.session.commit()
        return sku

    def create_order(self, order_id: str, reservation_id: str, status: str) -> OrderModel:
        order = OrderModel(order_id=order_id, reservation_id=reservation_id, status=status)
        self.session.add(order)
        self.session.commit()
        return order

    def get_order(self, order_id: str) -> OrderModel | None:
        return self.session.execute(
            select(OrderModel).where(OrderModel.order_id == order_id)
        ).scalar_one_or_none()

    def list_orders(self, limit: int, offset: int) -> tuple[list[OrderModel], int]:
        total = self.session.query(OrderModel).count()
        orders = self.session.execute(
            select(OrderModel).limit(limit).offset(offset)
        ).scalars().all()
        return orders, total

    def update_order_status(self, order_id: str, status: str) -> OrderModel | None:
        order = self.get_order(order_id)
        if not order:
            return None
        order.status = status
        self.session.commit()
        return order
