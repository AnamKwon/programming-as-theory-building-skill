"""Database repository layer using SQLAlchemy."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, Session

Base = declarative_base()


class SKU(Base):
    __tablename__ = "skus"
    sku = Column(String, primary_key=True)
    stock = Column(Integer, nullable=False)


class Reservation(Base):
    __tablename__ = "reservations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    sku = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="PENDING")
    idempotency_key = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, autoincrement=True)
    reservation_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Repository:
    def __init__(self, db_url: str = "sqlite:///./commerce.db"):
        self.engine = create_engine(db_url, connect_args={"check_same_thread": False} if "sqlite" in db_url else {})
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        session = self.get_session()
        try:
            existing = session.query(SKU).filter(SKU.sku == sku).first()
            if existing:
                existing.stock = initial_stock
                session.commit()
                return {"sku": existing.sku, "stock": existing.stock}

            new_sku = SKU(sku=sku, stock=initial_stock)
            session.add(new_sku)
            session.commit()
            return {"sku": new_sku.sku, "stock": new_sku.stock}
        finally:
            session.close()

    def get_sku_stock(self, sku: str) -> Optional[int]:
        session = self.get_session()
        try:
            sku_obj = session.query(SKU).filter(SKU.sku == sku).first()
            return sku_obj.stock if sku_obj else None
        finally:
            session.close()

    def adjust_stock(self, sku: str, amount: int) -> dict:
        session = self.get_session()
        try:
            sku_obj = session.query(SKU).filter(SKU.sku == sku).first()
            if not sku_obj:
                raise ValueError(f"SKU {sku} not found")
            sku_obj.stock += amount
            session.commit()
            return {"sku": sku_obj.sku, "stock": sku_obj.stock}
        finally:
            session.close()

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> dict:
        session = self.get_session()
        try:
            existing = session.query(Reservation).filter(
                Reservation.idempotency_key == idempotency_key
            ).first()
            if existing:
                return {
                    "id": existing.id,
                    "sku": existing.sku,
                    "quantity": existing.quantity,
                    "status": existing.status,
                    "idempotency_key": existing.idempotency_key,
                    "created_at": existing.created_at,
                }

            now = datetime.utcnow()
            reservation = Reservation(
                sku=sku,
                quantity=quantity,
                status="PENDING",
                idempotency_key=idempotency_key,
                created_at=now,
            )
            session.add(reservation)
            session.commit()
            return {
                "id": reservation.id,
                "sku": reservation.sku,
                "quantity": reservation.quantity,
                "status": reservation.status,
                "idempotency_key": reservation.idempotency_key,
                "created_at": reservation.created_at,
            }
        finally:
            session.close()

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        session = self.get_session()
        try:
            res = session.query(Reservation).filter(Reservation.id == reservation_id).first()
            if res:
                return {
                    "id": res.id,
                    "sku": res.sku,
                    "quantity": res.quantity,
                    "status": res.status,
                    "idempotency_key": res.idempotency_key,
                    "created_at": res.created_at,
                }
            return None
        finally:
            session.close()

    def update_reservation_status(self, reservation_id: int, status: str) -> dict:
        session = self.get_session()
        try:
            res = session.query(Reservation).filter(Reservation.id == reservation_id).first()
            if not res:
                raise ValueError(f"Reservation {reservation_id} not found")
            res.status = status
            session.commit()
            return {
                "id": res.id,
                "sku": res.sku,
                "quantity": res.quantity,
                "status": res.status,
                "idempotency_key": res.idempotency_key,
                "created_at": res.created_at,
            }
        finally:
            session.close()

    def create_order(self, reservation_id: int) -> dict:
        session = self.get_session()
        try:
            now = datetime.utcnow()
            order = Order(reservation_id=reservation_id, created_at=now)
            session.add(order)
            session.commit()
            return {
                "id": order.id,
                "reservation_id": order.reservation_id,
                "created_at": order.created_at,
            }
        finally:
            session.close()

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[dict], int]:
        session = self.get_session()
        try:
            offset = (page - 1) * size
            query = session.query(Order).offset(offset).limit(size)
            total = session.query(Order).count()
            orders = [
                {
                    "id": o.id,
                    "reservation_id": o.reservation_id,
                    "created_at": o.created_at,
                }
                for o in query.all()
            ]
            return orders, total
        finally:
            session.close()
