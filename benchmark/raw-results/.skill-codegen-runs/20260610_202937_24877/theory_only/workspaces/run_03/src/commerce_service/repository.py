from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .models import SKUOrm, ReservationOrm, OrderOrm


class SKURepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, sku: str, initial_stock: int) -> SKUOrm:
        sku_record = SKUOrm(sku=sku, initial_stock=initial_stock, available_stock=initial_stock)
        self.session.add(sku_record)
        self.session.commit()
        return sku_record

    def get_by_sku(self, sku: str) -> Optional[SKUOrm]:
        return self.session.query(SKUOrm).filter(SKUOrm.sku == sku).first()

    def update_stock(self, sku: str, amount: int) -> SKUOrm:
        sku_record = self.get_by_sku(sku)
        if sku_record:
            sku_record.available_stock += amount
            self.session.commit()
        return sku_record


class ReservationRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(
        self, sku: str, quantity: int, idempotency_key: str, created_at: datetime
    ) -> ReservationOrm:
        reservation = ReservationOrm(
            sku=sku,
            quantity=quantity,
            idempotency_key=idempotency_key,
            status="PENDING",
            created_at=created_at,
        )
        self.session.add(reservation)
        self.session.commit()
        return reservation

    def get_by_id(self, reservation_id: int) -> Optional[ReservationOrm]:
        return self.session.query(ReservationOrm).filter(ReservationOrm.id == reservation_id).first()

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[ReservationOrm]:
        return (
            self.session.query(ReservationOrm)
            .filter(ReservationOrm.idempotency_key == idempotency_key)
            .first()
        )

    def update_status(self, reservation_id: int, status: str) -> ReservationOrm:
        reservation = self.get_by_id(reservation_id)
        if reservation:
            reservation.status = status
            self.session.commit()
        return reservation


class OrderRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, reservation_id: int, created_at: datetime) -> OrderOrm:
        order = OrderOrm(
            reservation_id=reservation_id,
            status="CONFIRMED",
            created_at=created_at,
        )
        self.session.add(order)
        self.session.commit()
        return order

    def get_by_id(self, order_id: int) -> Optional[OrderOrm]:
        return self.session.query(OrderOrm).filter(OrderOrm.id == order_id).first()

    def list_orders(self, page: int = 1, size: int = 10) -> tuple[list[OrderOrm], int]:
        offset = (page - 1) * size
        query = self.session.query(OrderOrm)
        total = query.count()
        orders = query.offset(offset).limit(size).all()
        return orders, total
