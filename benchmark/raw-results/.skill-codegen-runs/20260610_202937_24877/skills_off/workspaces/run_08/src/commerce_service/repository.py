import os
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy import Column, DateTime, Integer, String, create_engine, select
from sqlalchemy.orm import Session, declarative_base, sessionmaker

Base = declarative_base()


class SKUModel(Base):
    __tablename__ = "skus"

    sku = Column(String, primary_key=True)
    available_stock = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class ReservationModel(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sku = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False)
    idempotency_key = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    reservation_id = Column(Integer, nullable=False)
    sku = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class Repository:
    def __init__(self, database_url: Optional[str] = None):
        if database_url is None:
            database_url = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")
        self.engine = create_engine(database_url, connect_args={"check_same_thread": False} if "sqlite" in database_url else {})
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()

    def create_sku(self, sku: str, initial_stock: int) -> SKUModel:
        session = self.get_session()
        try:
            sku_model = SKUModel(sku=sku, available_stock=initial_stock, created_at=datetime.now(timezone.utc))
            session.add(sku_model)
            session.commit()
            return sku_model
        finally:
            session.close()

    def get_sku(self, sku: str) -> Optional[SKUModel]:
        session = self.get_session()
        try:
            return session.query(SKUModel).filter(SKUModel.sku == sku).first()
        finally:
            session.close()

    def adjust_stock(self, sku: str, amount: int) -> Optional[SKUModel]:
        session = self.get_session()
        try:
            sku_model = session.query(SKUModel).filter(SKUModel.sku == sku).first()
            if sku_model:
                sku_model.available_stock += amount
                session.commit()
                return sku_model
            return None
        finally:
            session.close()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[ReservationModel]:
        session = self.get_session()
        try:
            return session.query(ReservationModel).filter(ReservationModel.idempotency_key == idempotency_key).first()
        finally:
            session.close()

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> ReservationModel:
        session = self.get_session()
        try:
            reservation = ReservationModel(
                sku=sku,
                quantity=quantity,
                status="PENDING",
                idempotency_key=idempotency_key,
                created_at=datetime.now(timezone.utc),
            )
            session.add(reservation)
            session.commit()
            session.refresh(reservation)
            return reservation
        finally:
            session.close()

    def get_reservation(self, reservation_id: int) -> Optional[ReservationModel]:
        session = self.get_session()
        try:
            return session.query(ReservationModel).filter(ReservationModel.id == reservation_id).first()
        finally:
            session.close()

    def update_reservation_status(self, reservation_id: int, status: str) -> Optional[ReservationModel]:
        session = self.get_session()
        try:
            reservation = session.query(ReservationModel).filter(ReservationModel.id == reservation_id).first()
            if reservation:
                reservation.status = status
                session.commit()
                session.refresh(reservation)
                return reservation
            return None
        finally:
            session.close()

    def create_order(self, reservation_id: int, sku: str, quantity: int) -> OrderModel:
        session = self.get_session()
        try:
            order = OrderModel(
                reservation_id=reservation_id,
                sku=sku,
                quantity=quantity,
                created_at=datetime.now(timezone.utc),
            )
            session.add(order)
            session.commit()
            session.refresh(order)
            return order
        finally:
            session.close()

    def get_orders(self, page: int = 1, size: int = 10) -> Tuple[list[OrderModel], int]:
        session = self.get_session()
        try:
            total = session.query(OrderModel).count()
            offset = (page - 1) * size
            orders = session.query(OrderModel).offset(offset).limit(size).all()
            return orders, total
        finally:
            session.close()
