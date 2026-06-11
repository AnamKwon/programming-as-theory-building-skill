from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
from typing import Optional

DATABASE_URL = "sqlite:///./commerce.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class SKUModel(Base):
    __tablename__ = "skus"

    sku = Column(String, primary_key=True)
    stock = Column(Integer, nullable=False)


class ReservationModel(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sku = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, default="PENDING")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    idempotency_key = Column(String, unique=True, nullable=False)


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=False)
    sku = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class Repository:
    def __init__(self, db: Session):
        self.db = db

    def create_sku(self, sku: str, stock: int) -> SKUModel:
        sku_obj = SKUModel(sku=sku, stock=stock)
        self.db.add(sku_obj)
        self.db.commit()
        self.db.refresh(sku_obj)
        return sku_obj

    def get_sku(self, sku: str) -> Optional[SKUModel]:
        return self.db.query(SKUModel).filter(SKUModel.sku == sku).first()

    def update_sku_stock(self, sku: str, amount: int) -> Optional[SKUModel]:
        sku_obj = self.get_sku(sku)
        if sku_obj:
            sku_obj.stock += amount
            self.db.commit()
            self.db.refresh(sku_obj)
        return sku_obj

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> ReservationModel:
        reservation = ReservationModel(
            sku=sku,
            quantity=quantity,
            idempotency_key=idempotency_key,
            status="PENDING"
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[ReservationModel]:
        return self.db.query(ReservationModel).filter(
            ReservationModel.idempotency_key == idempotency_key
        ).first()

    def get_reservation(self, reservation_id: int) -> Optional[ReservationModel]:
        return self.db.query(ReservationModel).filter(
            ReservationModel.id == reservation_id
        ).first()

    def update_reservation_status(self, reservation_id: int, status: str) -> Optional[ReservationModel]:
        reservation = self.get_reservation(reservation_id)
        if reservation:
            reservation.status = status
            reservation.updated_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(reservation)
        return reservation

    def create_order(self, reservation_id: int, sku: str, quantity: int) -> OrderModel:
        order = OrderModel(
            reservation_id=reservation_id,
            sku=sku,
            quantity=quantity
        )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def get_orders_paginated(self, page: int = 1, size: int = 10):
        offset = (page - 1) * size
        total = self.db.query(OrderModel).count()
        orders = self.db.query(OrderModel).offset(offset).limit(size).all()
        return orders, total
