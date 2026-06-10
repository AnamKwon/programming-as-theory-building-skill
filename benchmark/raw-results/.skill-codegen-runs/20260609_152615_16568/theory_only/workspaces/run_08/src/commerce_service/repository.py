from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from commerce_service.models import (
    OrderOrm,
    OrderStatus,
    ReservationOrm,
    ReservationStatus,
    SKUOrm,
)


class Repository:
    def __init__(self, session: Session):
        self.session = session

    def create_sku(self, sku_id: str, name: str, initial_stock: int) -> SKUOrm:
        sku = SKUOrm(id=sku_id, name=name, stock_quantity=initial_stock)
        self.session.add(sku)
        self.session.commit()
        return sku

    def get_sku(self, sku_id: str) -> Optional[SKUOrm]:
        return self.session.query(SKUOrm).filter(SKUOrm.id == sku_id).first()

    def update_stock(self, sku_id: str, adjustment: int) -> SKUOrm:
        sku = self.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        sku.stock_quantity += adjustment
        self.session.commit()
        return sku

    def create_reservation(
        self,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        idempotency_key: str,
        expires_at: datetime,
    ) -> ReservationOrm:
        reservation = ReservationOrm(
            id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            status=ReservationStatus.PENDING,
        )
        self.session.add(reservation)
        self.session.commit()
        return reservation

    def get_reservation(self, reservation_id: str) -> Optional[ReservationOrm]:
        return self.session.query(ReservationOrm).filter(
            ReservationOrm.id == reservation_id
        ).first()

    def get_reservation_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[ReservationOrm]:
        return self.session.query(ReservationOrm).filter(
            ReservationOrm.idempotency_key == idempotency_key
        ).first()

    def update_reservation_status(
        self, reservation_id: str, status: ReservationStatus
    ) -> ReservationOrm:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")
        reservation.status = status
        self.session.commit()
        return reservation

    def list_expired_reservations(self, now: datetime) -> list[ReservationOrm]:
        return self.session.query(ReservationOrm).filter(
            ReservationOrm.expires_at <= now,
            ReservationOrm.status == ReservationStatus.PENDING,
        ).all()

    def create_order(
        self, order_id: str, reservation_id: str, status: OrderStatus = OrderStatus.PENDING
    ) -> OrderOrm:
        order = OrderOrm(id=order_id, reservation_id=reservation_id, status=status)
        self.session.add(order)
        self.session.commit()
        return order

    def get_order(self, order_id: str) -> Optional[OrderOrm]:
        return self.session.query(OrderOrm).filter(OrderOrm.id == order_id).first()

    def list_orders(self, limit: int = 10, offset: int = 0) -> tuple[list[OrderOrm], int]:
        query = self.session.query(OrderOrm)
        total = query.count()
        orders = query.order_by(OrderOrm.created_at.desc()).limit(limit).offset(offset).all()
        return orders, total

    def update_order_status(self, order_id: str, status: OrderStatus) -> OrderOrm:
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        order.status = status
        self.session.commit()
        return order

    def get_reserved_quantity(self, sku_id: str) -> int:
        result = self.session.query(ReservationOrm).filter(
            ReservationOrm.sku_id == sku_id,
            ReservationOrm.status == ReservationStatus.PENDING,
        ).all()
        return sum(r.quantity for r in result)
