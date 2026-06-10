from typing import Optional
from datetime import datetime

from sqlalchemy.orm import Session

from .models import SKURecord, ReservationRecord, OrderRecord, Base, engine, SessionLocal


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class SKURepository:
    def __init__(self, session: Session):
        self.session = session

    def create_sku(self, sku: str, initial_stock: int) -> SKURecord:
        record = SKURecord(sku=sku, available_stock=initial_stock)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def get_sku(self, sku: str) -> Optional[SKURecord]:
        return self.session.query(SKURecord).filter(SKURecord.sku == sku).first()

    def adjust_stock(self, sku: str, amount: int) -> Optional[SKURecord]:
        record = self.get_sku(sku)
        if record:
            record.available_stock += amount
            self.session.commit()
            self.session.refresh(record)
        return record

    def get_available_stock(self, sku: str) -> int:
        record = self.get_sku(sku)
        return record.available_stock if record else 0


class ReservationRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> ReservationRecord:
        record = ReservationRecord(
            sku=sku, quantity=quantity, idempotency_key=idempotency_key, status="PENDING"
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def get_reservation(self, reservation_id: int) -> Optional[ReservationRecord]:
        return self.session.query(ReservationRecord).filter(
            ReservationRecord.id == reservation_id
        ).first()

    def get_reservation_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[ReservationRecord]:
        return self.session.query(ReservationRecord).filter(
            ReservationRecord.idempotency_key == idempotency_key
        ).first()

    def update_reservation_status(
        self, reservation_id: int, status: str
    ) -> Optional[ReservationRecord]:
        record = self.get_reservation(reservation_id)
        if record:
            record.status = status
            self.session.commit()
            self.session.refresh(record)
        return record


class OrderRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_order(
        self, reservation_id: int, sku: str, quantity: int
    ) -> OrderRecord:
        record = OrderRecord(reservation_id=reservation_id, sku=sku, quantity=quantity)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[OrderRecord], int]:
        query = self.session.query(OrderRecord)
        total = query.count()
        offset = (page - 1) * size
        orders = query.offset(offset).limit(size).all()
        return orders, total

    def get_order_count(self) -> int:
        return self.session.query(OrderRecord).count()
