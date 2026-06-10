import os
from datetime import datetime
from typing import Optional, Tuple, List
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def set_engine(new_engine, new_session_local):
    """Override the engine and session factory (for testing)"""
    global engine, SessionLocal
    engine = new_engine
    SessionLocal = new_session_local


class SKUModel(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    sku = Column(String, unique=True, index=True)
    available_stock = Column(Integer)


class ReservationModel(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    sku = Column(String)
    quantity = Column(Integer)
    status = Column(String, default="PENDING")
    idempotency_key = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class Repository:
    def __init__(self, session: Session):
        self.session = session

    def create_sku(self, sku: str, initial_stock: int) -> SKUModel:
        db_sku = SKUModel(sku=sku, available_stock=initial_stock)
        self.session.add(db_sku)
        self.session.commit()
        self.session.refresh(db_sku)
        return db_sku

    def get_sku(self, sku: str) -> Optional[SKUModel]:
        return self.session.query(SKUModel).filter(SKUModel.sku == sku).first()

    def update_stock(self, sku: str, amount: int) -> Optional[SKUModel]:
        db_sku = self.get_sku(sku)
        if db_sku:
            db_sku.available_stock += amount
            self.session.commit()
            self.session.refresh(db_sku)
        return db_sku

    def get_reservation(self, reservation_id: int) -> Optional[ReservationModel]:
        return self.session.query(ReservationModel).filter(ReservationModel.id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, key: str) -> Optional[ReservationModel]:
        return self.session.query(ReservationModel).filter(ReservationModel.idempotency_key == key).first()

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> ReservationModel:
        db_reservation = ReservationModel(
            sku=sku,
            quantity=quantity,
            idempotency_key=idempotency_key,
            status="PENDING"
        )
        self.session.add(db_reservation)
        self.session.commit()
        self.session.refresh(db_reservation)
        return db_reservation

    def update_reservation_status(self, reservation_id: int, status: str) -> Optional[ReservationModel]:
        db_reservation = self.get_reservation(reservation_id)
        if db_reservation:
            db_reservation.status = status
            self.session.commit()
            self.session.refresh(db_reservation)
        return db_reservation

    def create_order(self, reservation_id: int) -> OrderModel:
        db_order = OrderModel(reservation_id=reservation_id)
        self.session.add(db_order)
        self.session.commit()
        self.session.refresh(db_order)
        return db_order

    def list_orders(self, skip: int = 0, limit: int = 10) -> Tuple[List[OrderModel], int]:
        orders = self.session.query(OrderModel).offset(skip).limit(limit).all()
        total = self.session.query(OrderModel).count()
        return orders, total
