from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, Session, relationship

DATABASE_URL = "sqlite:///./commerce.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
Base = declarative_base()


class SKUModel(Base):
    __tablename__ = "skus"

    sku_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    current_stock = Column(Integer, nullable=False, default=0)
    reserved_stock = Column(Integer, nullable=False, default=0)

    reservations = relationship("ReservationModel", back_populates="sku")


class ReservationModel(Base):
    __tablename__ = "reservations"

    reservation_id = Column(String, primary_key=True)
    sku_id = Column(String, ForeignKey("skus.sku_id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    idempotency_key = Column(String, nullable=False, unique=True, index=True)
    order_id = Column(String, ForeignKey("orders.order_id"), nullable=True)

    sku = relationship("SKUModel", back_populates="reservations")
    order = relationship("OrderModel", back_populates="reservations")


class OrderModel(Base):
    __tablename__ = "orders"

    order_id = Column(String, primary_key=True)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    reservations = relationship("ReservationModel", back_populates="order")


Base.metadata.create_all(bind=engine)


class Repository:
    def __init__(self):
        self.engine = engine

    def get_session(self) -> Session:
        return Session(self.engine)

    def create_sku(self, sku_id: str, name: str, initial_stock: int) -> SKUModel:
        session = self.get_session()
        try:
            sku = SKUModel(sku_id=sku_id, name=name, current_stock=initial_stock)
            session.add(sku)
            session.commit()
            session.refresh(sku)
            return sku
        finally:
            session.close()

    def get_sku(self, sku_id: str) -> Optional[SKUModel]:
        session = self.get_session()
        try:
            return session.query(SKUModel).filter(SKUModel.sku_id == sku_id).first()
        finally:
            session.close()

    def adjust_sku_stock(self, sku_id: str, delta: int) -> Optional[SKUModel]:
        session = self.get_session()
        try:
            sku = session.query(SKUModel).filter(SKUModel.sku_id == sku_id).first()
            if not sku:
                return None
            sku.current_stock = max(0, sku.current_stock + delta)
            session.commit()
            session.refresh(sku)
            return sku
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

    def create_reservation(
        self,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        expires_at: datetime,
        idempotency_key: str,
    ) -> ReservationModel:
        session = self.get_session()
        try:
            reservation = ReservationModel(
                reservation_id=reservation_id,
                sku_id=sku_id,
                quantity=quantity,
                expires_at=expires_at,
                idempotency_key=idempotency_key,
                status="pending",
            )
            session.add(reservation)
            session.commit()
            session.refresh(reservation)
            return reservation
        finally:
            session.close()

    def update_reservation_status(self, reservation_id: str, status: str) -> Optional[ReservationModel]:
        session = self.get_session()
        try:
            reservation = session.query(ReservationModel).filter(
                ReservationModel.reservation_id == reservation_id
            ).first()
            if not reservation:
                return None
            reservation.status = status
            session.commit()
            session.refresh(reservation)
            return reservation
        finally:
            session.close()

    def link_reservation_to_order(self, reservation_id: str, order_id: str) -> Optional[ReservationModel]:
        session = self.get_session()
        try:
            reservation = session.query(ReservationModel).filter(
                ReservationModel.reservation_id == reservation_id
            ).first()
            if not reservation:
                return None
            reservation.order_id = order_id
            session.commit()
            session.refresh(reservation)
            return reservation
        finally:
            session.close()

    def update_sku_reserved_stock(self, sku_id: str, delta: int) -> Optional[SKUModel]:
        session = self.get_session()
        try:
            sku = session.query(SKUModel).filter(SKUModel.sku_id == sku_id).first()
            if not sku:
                return None
            sku.reserved_stock = max(0, sku.reserved_stock + delta)
            session.commit()
            session.refresh(sku)
            return sku
        finally:
            session.close()

    def create_order(self, order_id: str) -> OrderModel:
        session = self.get_session()
        try:
            order = OrderModel(order_id=order_id, status="pending")
            session.add(order)
            session.commit()
            session.refresh(order)
            return order
        finally:
            session.close()

    def get_order(self, order_id: str) -> Optional[OrderModel]:
        session = self.get_session()
        try:
            return session.query(OrderModel).filter(OrderModel.order_id == order_id).first()
        finally:
            session.close()

    def list_orders(self, skip: int = 0, limit: int = 20) -> tuple[list[OrderModel], int]:
        session = self.get_session()
        try:
            total = session.query(OrderModel).count()
            orders = session.query(OrderModel).offset(skip).limit(limit).all()
            return orders, total
        finally:
            session.close()

    def update_order_status(self, order_id: str, status: str) -> Optional[OrderModel]:
        session = self.get_session()
        try:
            order = session.query(OrderModel).filter(OrderModel.order_id == order_id).first()
            if not order:
                return None
            order.status = status
            session.commit()
            session.refresh(order)
            return order
        finally:
            session.close()
