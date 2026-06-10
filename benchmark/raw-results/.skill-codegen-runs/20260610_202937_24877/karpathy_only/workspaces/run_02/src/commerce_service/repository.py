"""Database repository layer using SQLAlchemy."""

from datetime import datetime, timezone
from typing import Optional, Tuple
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.types import TypeDecorator

Base = declarative_base()


class SKURecord(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    sku = Column(String, unique=True, nullable=False, index=True)
    available_stock = Column(Integer, nullable=False, default=0)
    reserved_stock = Column(Integer, nullable=False, default=0)


class ReservationRecord(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    sku = Column(String, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="PENDING")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    idempotency_key = Column(String, unique=True, nullable=False, index=True)


class OrderRecord(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, nullable=False, index=True)
    sku = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class IdempotencyRecord(Base):
    __tablename__ = "idempotencies"

    id = Column(Integer, primary_key=True)
    idempotency_key = Column(String, unique=True, nullable=False, index=True)
    response_data = Column(String, nullable=False)


class Repository:
    def __init__(self, db_url: str = "sqlite:///commerce.db"):
        self.engine = create_engine(db_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()

    # SKU operations
    def create_sku(self, sku: str, initial_stock: int) -> SKURecord:
        session = self.get_session()
        try:
            sku_record = SKURecord(sku=sku, available_stock=initial_stock, reserved_stock=0)
            session.add(sku_record)
            session.commit()
            session.refresh(sku_record)
            return sku_record
        finally:
            session.close()

    def get_sku(self, sku: str) -> Optional[SKURecord]:
        session = self.get_session()
        try:
            return session.query(SKURecord).filter(SKURecord.sku == sku).first()
        finally:
            session.close()

    def adjust_stock(self, sku: str, amount: int) -> Tuple[int, int]:
        session = self.get_session()
        try:
            sku_record = session.query(SKURecord).filter(SKURecord.sku == sku).with_for_update().first()
            sku_record.available_stock += amount
            session.commit()
            return sku_record.available_stock, sku_record.reserved_stock
        finally:
            session.close()

    # Reservation operations
    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> ReservationRecord:
        session = self.get_session()
        try:
            reservation = ReservationRecord(
                sku=sku,
                quantity=quantity,
                status="PENDING",
                idempotency_key=idempotency_key,
            )
            session.add(reservation)
            session.commit()
            session.refresh(reservation)
            return reservation
        finally:
            session.close()

    def get_reservation(self, reservation_id: int) -> Optional[ReservationRecord]:
        session = self.get_session()
        try:
            return session.query(ReservationRecord).filter(ReservationRecord.id == reservation_id).first()
        finally:
            session.close()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[ReservationRecord]:
        session = self.get_session()
        try:
            return session.query(ReservationRecord).filter(
                ReservationRecord.idempotency_key == idempotency_key
            ).first()
        finally:
            session.close()

    def update_reservation_status(self, reservation_id: int, status: str) -> ReservationRecord:
        session = self.get_session()
        try:
            reservation = session.query(ReservationRecord).filter(
                ReservationRecord.id == reservation_id
            ).with_for_update().first()
            reservation.status = status
            session.commit()
            session.refresh(reservation)
            return reservation
        finally:
            session.close()

    def reserve_stock(self, sku: str, quantity: int) -> bool:
        session = self.get_session()
        try:
            sku_record = session.query(SKURecord).filter(SKURecord.sku == sku).with_for_update().first()
            if sku_record.available_stock >= quantity:
                sku_record.available_stock -= quantity
                sku_record.reserved_stock += quantity
                session.commit()
                return True
            return False
        finally:
            session.close()

    def release_reserved_stock(self, sku: str, quantity: int):
        session = self.get_session()
        try:
            sku_record = session.query(SKURecord).filter(SKURecord.sku == sku).with_for_update().first()
            sku_record.reserved_stock -= quantity
            sku_record.available_stock += quantity
            session.commit()
        finally:
            session.close()

    def reserve_confirmed(self, sku: str, quantity: int):
        session = self.get_session()
        try:
            sku_record = session.query(SKURecord).filter(SKURecord.sku == sku).with_for_update().first()
            sku_record.reserved_stock -= quantity
            session.commit()
        finally:
            session.close()

    # Order operations
    def create_order(self, reservation_id: int, sku: str, quantity: int) -> OrderRecord:
        session = self.get_session()
        try:
            order = OrderRecord(
                reservation_id=reservation_id,
                sku=sku,
                quantity=quantity,
            )
            session.add(order)
            session.commit()
            session.refresh(order)
            return order
        finally:
            session.close()

    def get_orders(self, page: int = 1, size: int = 10) -> Tuple[list[OrderRecord], int]:
        session = self.get_session()
        try:
            total = session.query(OrderRecord).count()
            offset = (page - 1) * size
            orders = session.query(OrderRecord).offset(offset).limit(size).all()
            return orders, total
        finally:
            session.close()
