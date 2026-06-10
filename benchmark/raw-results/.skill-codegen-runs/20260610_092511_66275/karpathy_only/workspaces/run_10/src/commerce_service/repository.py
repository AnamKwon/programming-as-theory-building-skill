import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import Column, DateTime, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class SKUModel(Base):
    __tablename__ = "skus"

    sku = Column(String(100), primary_key=True)
    description = Column(String(500), nullable=False)
    quantity = Column(Integer, nullable=False, default=0)


class ReservationModel(Base):
    __tablename__ = "reservations"

    reservation_id = Column(String(36), primary_key=True)
    order_id = Column(String(100), nullable=False)
    sku = Column(String(100), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    idempotency_key = Column(String(200), nullable=False, unique=True)


class OrderModel(Base):
    __tablename__ = "orders"

    order_id = Column(String(100), primary_key=True)
    status = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Repository:
    def __init__(self, db_url: str = "sqlite:///commerce.db"):
        self.engine = create_engine(db_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def get_session(self):
        return self.SessionLocal()

    # SKU operations
    def create_sku(self, sku: str, description: str, quantity: int) -> SKUModel:
        session = self.get_session()
        try:
            sku_model = SKUModel(sku=sku, description=description, quantity=quantity)
            session.add(sku_model)
            session.commit()
            session.refresh(sku_model)
            return sku_model
        finally:
            session.close()

    def get_sku(self, sku: str) -> Optional[SKUModel]:
        session = self.get_session()
        try:
            return session.query(SKUModel).filter(SKUModel.sku == sku).first()
        finally:
            session.close()

    def adjust_stock(self, sku: str, adjustment: int) -> Optional[SKUModel]:
        session = self.get_session()
        try:
            sku_model = session.query(SKUModel).filter(SKUModel.sku == sku).first()
            if not sku_model:
                return None
            sku_model.quantity += adjustment
            session.commit()
            session.refresh(sku_model)
            return sku_model
        finally:
            session.close()

    # Reservation operations
    def create_reservation(
        self,
        order_id: str,
        sku: str,
        quantity: int,
        idempotency_key: str,
        ttl_seconds: int = 3600,
    ) -> ReservationModel:
        session = self.get_session()
        try:
            reservation = ReservationModel(
                reservation_id=str(uuid.uuid4()),
                order_id=order_id,
                sku=sku,
                quantity=quantity,
                idempotency_key=idempotency_key,
                expires_at=datetime.utcnow() + timedelta(seconds=ttl_seconds),
            )
            session.add(reservation)
            session.commit()
            session.refresh(reservation)
            return reservation
        finally:
            session.close()

    def get_reservation(self, reservation_id: str) -> Optional[ReservationModel]:
        session = self.get_session()
        try:
            return session.query(ReservationModel).filter(
                ReservationModel.reservation_id == reservation_id
            ).first()
        finally:
            session.close()

    def get_reservation_by_idempotency_key(self, key: str) -> Optional[ReservationModel]:
        session = self.get_session()
        try:
            return session.query(ReservationModel).filter(
                ReservationModel.idempotency_key == key
            ).first()
        finally:
            session.close()

    def update_reservation_status(
        self, reservation_id: str, status: str
    ) -> Optional[ReservationModel]:
        session = self.get_session()
        try:
            reservation = session.query(ReservationModel).filter(
                ReservationModel.reservation_id == reservation_id
            ).first()
            if reservation:
                reservation.status = status
                session.commit()
                session.refresh(reservation)
            return reservation
        finally:
            session.close()

    # Order operations
    def create_order(self, order_id: str) -> OrderModel:
        session = self.get_session()
        try:
            order = OrderModel(order_id=order_id)
            session.add(order)
            session.commit()
            session.refresh(order)
            return order
        finally:
            session.close()

    def get_order(self, order_id: str) -> Optional[OrderModel]:
        session = self.get_session()
        try:
            return session.query(OrderModel).filter(
                OrderModel.order_id == order_id
            ).first()
        finally:
            session.close()

    def list_orders(self, limit: int = 10, offset: int = 0) -> tuple[list[OrderModel], int]:
        session = self.get_session()
        try:
            total = session.query(OrderModel).count()
            orders = session.query(OrderModel).order_by(
                OrderModel.created_at.desc()
            ).limit(limit).offset(offset).all()
            return orders, total
        finally:
            session.close()

    def update_order_status(self, order_id: str, status: str) -> Optional[OrderModel]:
        session = self.get_session()
        try:
            order = session.query(OrderModel).filter(
                OrderModel.order_id == order_id
            ).first()
            if order:
                order.status = status
                session.commit()
                session.refresh(order)
            return order
        finally:
            session.close()

    def get_reservations_for_order(self, order_id: str) -> list[ReservationModel]:
        session = self.get_session()
        try:
            return session.query(ReservationModel).filter(
                ReservationModel.order_id == order_id
            ).all()
        finally:
            session.close()
