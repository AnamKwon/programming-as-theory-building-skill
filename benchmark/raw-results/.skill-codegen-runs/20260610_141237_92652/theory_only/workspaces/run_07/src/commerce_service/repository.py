"""Data access layer using SQLAlchemy."""

from datetime import datetime
from typing import Optional
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker, Session

from .models import Base, SKU, Reservation, Order, ReservationStatus


class Repository:
    def __init__(self, db_url: str = "sqlite:///commerce.db"):
        self.engine = create_engine(db_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()

    def create_sku(self, sku: str, initial_stock: int) -> SKU:
        session = self.get_session()
        try:
            sku_obj = SKU(sku=sku, available_stock=initial_stock)
            session.add(sku_obj)
            session.commit()
            session.refresh(sku_obj)
            return sku_obj
        finally:
            session.close()

    def get_sku_by_name(self, sku: str) -> Optional[SKU]:
        session = self.get_session()
        try:
            return session.query(SKU).filter(SKU.sku == sku).first()
        finally:
            session.close()

    def adjust_stock(self, sku: str, amount: int) -> Optional[int]:
        session = self.get_session()
        try:
            sku_obj = session.query(SKU).filter(SKU.sku == sku).first()
            if not sku_obj:
                return None
            sku_obj.available_stock += amount
            session.commit()
            return sku_obj.available_stock
        finally:
            session.close()

    def get_reservation_by_idempotency_key(self, key: str) -> Optional[Reservation]:
        session = self.get_session()
        try:
            return session.query(Reservation).filter(
                Reservation.idempotency_key == key
            ).first()
        finally:
            session.close()

    def create_reservation(
        self, sku: str, sku_id: int, quantity: int, idempotency_key: str
    ) -> Reservation:
        session = self.get_session()
        try:
            reservation = Reservation(
                sku=sku,
                sku_id=sku_id,
                quantity=quantity,
                idempotency_key=idempotency_key,
                status=ReservationStatus.PENDING,
                created_at=datetime.utcnow(),
            )
            session.add(reservation)
            session.commit()
            session.refresh(reservation)
            return reservation
        finally:
            session.close()

    def deduct_stock(self, sku_id: int, quantity: int) -> None:
        session = self.get_session()
        try:
            sku_obj = session.query(SKU).filter(SKU.id == sku_id).first()
            if sku_obj:
                sku_obj.available_stock -= quantity
                session.commit()
        finally:
            session.close()

    def get_reservation(self, reservation_id: int) -> Optional[Reservation]:
        session = self.get_session()
        try:
            return session.query(Reservation).filter(
                Reservation.id == reservation_id
            ).first()
        finally:
            session.close()

    def update_reservation_status(
        self, reservation_id: int, status: str
    ) -> Optional[Reservation]:
        session = self.get_session()
        try:
            reservation = session.query(Reservation).filter(
                Reservation.id == reservation_id
            ).first()
            if reservation:
                reservation.status = status
                session.commit()
                session.refresh(reservation)
            return reservation
        finally:
            session.close()

    def create_order(self, reservation_id: int) -> Order:
        session = self.get_session()
        try:
            order = Order(
                reservation_id=reservation_id,
                created_at=datetime.utcnow(),
            )
            session.add(order)
            session.commit()
            session.refresh(order)
            return order
        finally:
            session.close()

    def get_orders(self, page: int = 1, size: int = 10):
        session = self.get_session()
        try:
            offset = (page - 1) * size
            total = session.query(func.count(Order.id)).scalar()
            orders = session.query(Order).offset(offset).limit(size).all()
            return orders, total
        finally:
            session.close()

    def restore_stock(self, sku_id: int, quantity: int) -> None:
        session = self.get_session()
        try:
            sku_obj = session.query(SKU).filter(SKU.id == sku_id).first()
            if sku_obj:
                sku_obj.available_stock += quantity
                session.commit()
        finally:
            session.close()
