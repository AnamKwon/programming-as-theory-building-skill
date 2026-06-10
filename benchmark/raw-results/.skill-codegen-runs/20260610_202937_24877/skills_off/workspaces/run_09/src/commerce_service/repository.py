from datetime import datetime
from typing import Optional, List, Tuple
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError

from .models import (
    Base,
    SKUModel,
    ReservationModel,
    OrderModel,
    ReservationStatus,
)

DATABASE_URL = "sqlite:///./commerce.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db():
    Base.metadata.create_all(bind=engine)


class Repository:
    def __init__(self, session: Optional[Session] = None):
        self.session = session or SessionLocal()

    def close(self):
        self.session.close()

    def create_sku(self, sku: str, initial_stock: int) -> SKUModel:
        db_sku = SKUModel(sku=sku, available_stock=initial_stock)
        self.session.add(db_sku)
        self.session.commit()
        self.session.refresh(db_sku)
        return db_sku

    def get_sku_by_sku_code(self, sku: str) -> Optional[SKUModel]:
        stmt = select(SKUModel).where(SKUModel.sku == sku)
        return self.session.execute(stmt).scalars().first()

    def get_sku_by_id(self, sku_id: int) -> Optional[SKUModel]:
        return self.session.query(SKUModel).filter(SKUModel.id == sku_id).first()

    def update_sku_stock(self, sku_id: int, amount: int) -> Optional[SKUModel]:
        sku = self.get_sku_by_id(sku_id)
        if sku:
            sku.available_stock += amount
            self.session.commit()
            self.session.refresh(sku)
        return sku

    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        idempotency_key: str,
    ) -> ReservationModel:
        db_reservation = ReservationModel(
            sku_id=sku_id,
            quantity=quantity,
            status=ReservationStatus.PENDING,
            created_at=datetime.utcnow(),
            idempotency_key=idempotency_key,
        )
        self.session.add(db_reservation)
        self.session.commit()
        self.session.refresh(db_reservation)
        return db_reservation

    def get_reservation_by_id(self, reservation_id: int) -> Optional[ReservationModel]:
        return self.session.query(ReservationModel).filter(ReservationModel.id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[ReservationModel]:
        return (
            self.session.query(ReservationModel)
            .filter(ReservationModel.idempotency_key == idempotency_key)
            .first()
        )

    def update_reservation_status(self, reservation_id: int, status: ReservationStatus) -> Optional[ReservationModel]:
        reservation = self.get_reservation_by_id(reservation_id)
        if reservation:
            reservation.status = status
            self.session.commit()
            self.session.refresh(reservation)
        return reservation

    def create_order(self, reservation_id: int) -> OrderModel:
        db_order = OrderModel(
            reservation_id=reservation_id,
            created_at=datetime.utcnow(),
        )
        self.session.add(db_order)
        self.session.commit()
        self.session.refresh(db_order)
        return db_order

    def get_orders_paginated(self, page: int = 1, size: int = 10) -> Tuple[List[OrderModel], int]:
        skip = (page - 1) * size
        stmt = select(OrderModel)
        total = self.session.execute(select(OrderModel)).rowcount if hasattr(self.session.execute(select(OrderModel)), 'rowcount') else len(self.session.execute(select(OrderModel)).scalars().all())
        total = self.session.query(OrderModel).count()
        orders = self.session.query(OrderModel).offset(skip).limit(size).all()
        return orders, total


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
