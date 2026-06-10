from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, create_engine, select
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class SKU(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    sku = Column(String, unique=True, nullable=False)
    available_stock = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, nullable=False)
    sku = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    idempotency_key = Column(String, unique=True, nullable=False)
    status = Column(String, nullable=False, default="PENDING")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, nullable=False)
    sku_id = Column(Integer, nullable=False)
    sku = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Repository:
    def __init__(self, database_url: str = "sqlite:///commerce.db"):
        self.engine = create_engine(database_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def get_session(self):
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

    def get_sku_by_name(self, sku: str) -> SKU | None:
        session = self.get_session()
        try:
            return session.query(SKU).filter(SKU.sku == sku).first()
        finally:
            session.close()

    def update_sku_stock(self, sku: str, amount: int) -> SKU | None:
        session = self.get_session()
        try:
            sku_obj = session.query(SKU).filter(SKU.sku == sku).first()
            if sku_obj:
                sku_obj.available_stock += amount
                session.commit()
                session.refresh(sku_obj)
            return sku_obj
        finally:
            session.close()

    def create_reservation(
        self, sku_id: int, sku: str, quantity: int, idempotency_key: str
    ) -> Reservation:
        session = self.get_session()
        try:
            reservation = Reservation(
                sku_id=sku_id,
                sku=sku,
                quantity=quantity,
                idempotency_key=idempotency_key,
                status="PENDING",
            )
            session.add(reservation)
            session.commit()
            session.refresh(reservation)
            return reservation
        finally:
            session.close()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Reservation | None:
        session = self.get_session()
        try:
            return session.query(Reservation).filter(Reservation.idempotency_key == idempotency_key).first()
        finally:
            session.close()

    def get_reservation_by_id(self, reservation_id: int) -> Reservation | None:
        session = self.get_session()
        try:
            return session.query(Reservation).filter(Reservation.id == reservation_id).first()
        finally:
            session.close()

    def update_reservation_status(self, reservation_id: int, status: str) -> Reservation | None:
        session = self.get_session()
        try:
            reservation = session.query(Reservation).filter(Reservation.id == reservation_id).first()
            if reservation:
                reservation.status = status
                reservation.updated_at = datetime.utcnow()
                session.commit()
                session.refresh(reservation)
            return reservation
        finally:
            session.close()

    def create_order(self, reservation_id: int, sku_id: int, sku: str, quantity: int) -> Order:
        session = self.get_session()
        try:
            order = Order(
                reservation_id=reservation_id,
                sku_id=sku_id,
                sku=sku,
                quantity=quantity,
            )
            session.add(order)
            session.commit()
            session.refresh(order)
            return order
        finally:
            session.close()

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[Order], int]:
        session = self.get_session()
        try:
            offset = (page - 1) * size
            total = session.query(Order).count()
            orders = session.query(Order).offset(offset).limit(size).all()
            return orders, total
        finally:
            session.close()
