from datetime import datetime
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from .models import Order, OrderReservation, OrderStatus, Reservation, ReservationStatus, SKU


class SKURepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, sku_code: str, name: str, stock_quantity: int) -> SKU:
        sku = SKU(sku_code=sku_code, name=name, stock_quantity=stock_quantity)
        self.session.add(sku)
        self.session.commit()
        self.session.refresh(sku)
        return sku

    def get_by_id(self, sku_id: int) -> Optional[SKU]:
        return self.session.query(SKU).filter(SKU.id == sku_id).first()

    def get_by_code(self, sku_code: str) -> Optional[SKU]:
        return self.session.query(SKU).filter(SKU.sku_code == sku_code).first()

    def adjust_stock(self, sku_id: int, adjustment: int) -> Optional[SKU]:
        sku = self.get_by_id(sku_id)
        if sku:
            sku.stock_quantity += adjustment
            self.session.commit()
            self.session.refresh(sku)
        return sku


class ReservationRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        sku_id: int,
        quantity: int,
        expires_at: datetime,
        idempotency_key: Optional[str] = None,
    ) -> Reservation:
        reservation = Reservation(
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )
        self.session.add(reservation)
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    def get_by_id(self, reservation_id: int) -> Optional[Reservation]:
        return self.session.query(Reservation).filter(Reservation.id == reservation_id).first()

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[Reservation]:
        return self.session.query(Reservation).filter(
            Reservation.idempotency_key == idempotency_key
        ).first()

    def get_pending_for_sku(self, sku_id: int) -> list[Reservation]:
        return self.session.query(Reservation).filter(
            and_(
                Reservation.sku_id == sku_id,
                Reservation.status == ReservationStatus.PENDING,
                Reservation.expires_at > datetime.utcnow(),
            )
        ).all()

    def update_status(self, reservation_id: int, status: str) -> Optional[Reservation]:
        reservation = self.get_by_id(reservation_id)
        if reservation:
            reservation.status = status
            self.session.commit()
            self.session.refresh(reservation)
        return reservation

    def expire_stale_reservations(self) -> int:
        now = datetime.utcnow()
        result = self.session.query(Reservation).filter(
            and_(
                Reservation.status == ReservationStatus.PENDING,
                Reservation.expires_at <= now,
            )
        ).update({Reservation.status: ReservationStatus.EXPIRED})
        self.session.commit()
        return result


class OrderRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self) -> Order:
        order = Order(status=OrderStatus.PENDING)
        self.session.add(order)
        self.session.commit()
        self.session.refresh(order)
        return order

    def get_by_id(self, order_id: int) -> Optional[Order]:
        return self.session.query(Order).filter(Order.id == order_id).first()

    def update_status(self, order_id: int, status: str) -> Optional[Order]:
        order = self.get_by_id(order_id)
        if order:
            order.status = status
            self.session.commit()
            self.session.refresh(order)
        return order

    def list_paginated(self, page: int = 1, page_size: int = 10) -> tuple[list[Order], int]:
        query = self.session.query(Order)
        total = query.count()
        orders = query.offset((page - 1) * page_size).limit(page_size).all()
        return orders, total

    def add_reservation_to_order(self, order_id: int, reservation_id: int) -> OrderReservation:
        order_res = OrderReservation(order_id=order_id, reservation_id=reservation_id)
        self.session.add(order_res)
        self.session.commit()
        self.session.refresh(order_res)
        return order_res

    def get_reservations_for_order(self, order_id: int) -> list[int]:
        rows = self.session.query(OrderReservation.reservation_id).filter(
            OrderReservation.order_id == order_id
        ).all()
        return [row[0] for row in rows]
