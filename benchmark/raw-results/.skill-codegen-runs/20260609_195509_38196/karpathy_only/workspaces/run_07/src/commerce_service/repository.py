from datetime import datetime

from sqlalchemy.orm import Session

from .models import Order, OrderStatus, Reservation, ReservationStatus, SKU


class SKURepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, sku_id: str, name: str, current_stock: int) -> SKU:
        sku = SKU(id=sku_id, name=name, current_stock=current_stock)
        self.session.add(sku)
        self.session.commit()
        return sku

    def get(self, sku_id: str) -> SKU | None:
        return self.session.query(SKU).filter(SKU.id == sku_id).first()

    def update_stock(self, sku_id: str, quantity_delta: int) -> SKU | None:
        sku = self.get(sku_id)
        if sku:
            sku.current_stock += quantity_delta
            self.session.commit()
        return sku


class ReservationRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        expires_at: datetime,
        idempotency_key: str | None = None,
    ) -> Reservation:
        reservation = Reservation(
            id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
            status=ReservationStatus.PENDING,
        )
        self.session.add(reservation)
        self.session.commit()
        return reservation

    def get(self, reservation_id: str) -> Reservation | None:
        return self.session.query(Reservation).filter(Reservation.id == reservation_id).first()

    def get_by_idempotency_key(self, idempotency_key: str) -> Reservation | None:
        return (
            self.session.query(Reservation)
            .filter(Reservation.idempotency_key == idempotency_key)
            .first()
        )

    def update_status(self, reservation_id: str, status: ReservationStatus) -> Reservation | None:
        reservation = self.get(reservation_id)
        if reservation:
            reservation.status = status
            self.session.commit()
        return reservation

    def get_expired(self, now: datetime) -> list[Reservation]:
        return (
            self.session.query(Reservation)
            .filter(
                Reservation.status == ReservationStatus.PENDING,
                Reservation.expires_at <= now,
            )
            .all()
        )


class OrderRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(
        self, order_id: str, reservation_id: str, sku_id: str, quantity: int
    ) -> Order:
        order = Order(
            id=order_id,
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            status=OrderStatus.CONFIRMED,
        )
        self.session.add(order)
        self.session.commit()
        return order

    def get(self, order_id: str) -> Order | None:
        return self.session.query(Order).filter(Order.id == order_id).first()

    def list_paginated(self, limit: int = 10, offset: int = 0) -> tuple[list[Order], int]:
        total = self.session.query(Order).count()
        orders = self.session.query(Order).limit(limit).offset(offset).all()
        return orders, total

    def update_status(self, order_id: str, status: OrderStatus) -> Order | None:
        order = self.get(order_id)
        if order:
            order.status = status
            self.session.commit()
        return order
