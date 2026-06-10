from datetime import datetime
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import enum

Base = declarative_base()


class SKU(Base):
    __tablename__ = "skus"
    id = Column(String(100), primary_key=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Stock(Base):
    __tablename__ = "stock"
    sku_id = Column(String(100), primary_key=True)
    available = Column(Integer, nullable=False, default=0)
    reserved = Column(Integer, nullable=False, default=0)


class ReservationStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class Reservation(Base):
    __tablename__ = "reservations"
    id = Column(String(36), primary_key=True)
    sku_id = Column(String(100), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default=ReservationStatus.PENDING.value)
    idempotency_key = Column(String(255), unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)


class Order(Base):
    __tablename__ = "orders"
    id = Column(String(36), primary_key=True)
    reservation_id = Column(String(36), unique=True, nullable=False)
    sku_id = Column(String(100), nullable=False)
    quantity = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Repository:
    def __init__(self, db_url: str = "sqlite:///commerce.db"):
        self.engine = create_engine(db_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()

    def create_sku(self, session: Session, sku_id: str, name: str, initial_stock: int) -> SKU:
        sku = SKU(id=sku_id, name=name)
        session.add(sku)
        session.add(Stock(sku_id=sku_id, available=initial_stock, reserved=0))
        session.commit()
        return sku

    def get_sku(self, session: Session, sku_id: str) -> SKU | None:
        return session.query(SKU).filter(SKU.id == sku_id).first()

    def adjust_stock(self, session: Session, sku_id: str, delta: int) -> Stock:
        stock = session.query(Stock).filter(Stock.sku_id == sku_id).first()
        if not stock:
            raise ValueError(f"SKU {sku_id} not found")
        stock.available += delta
        if stock.available < 0:
            raise ValueError(f"Insufficient stock for {sku_id}")
        session.commit()
        return stock

    def get_stock(self, session: Session, sku_id: str) -> Stock | None:
        return session.query(Stock).filter(Stock.sku_id == sku_id).first()

    def create_reservation(
        self, session: Session, res_id: str, sku_id: str, quantity: int,
        idempotency_key: str, expires_at: datetime
    ) -> Reservation:
        res = Reservation(
            id=res_id,
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            status=ReservationStatus.PENDING.value,
        )
        session.add(res)
        stock = session.query(Stock).filter(Stock.sku_id == sku_id).first()
        stock.available -= quantity
        stock.reserved += quantity
        session.commit()
        return res

    def get_reservation_by_idempotency_key(self, session: Session, key: str) -> Reservation | None:
        return session.query(Reservation).filter(Reservation.idempotency_key == key).first()

    def get_reservation(self, session: Session, res_id: str) -> Reservation | None:
        return session.query(Reservation).filter(Reservation.id == res_id).first()

    def confirm_reservation(self, session: Session, res_id: str, order_id: str) -> Order:
        res = session.query(Reservation).filter(Reservation.id == res_id).first()
        if not res:
            raise ValueError(f"Reservation {res_id} not found")
        if res.status != ReservationStatus.PENDING.value:
            raise ValueError(f"Reservation {res_id} is not pending")
        if res.expires_at < datetime.utcnow():
            res.status = ReservationStatus.CANCELLED.value
            stock = session.query(Stock).filter(Stock.sku_id == res.sku_id).first()
            stock.available += res.quantity
            stock.reserved -= res.quantity
            session.commit()
            raise ValueError(f"Reservation {res_id} has expired")

        res.status = ReservationStatus.CONFIRMED.value
        stock = session.query(Stock).filter(Stock.sku_id == res.sku_id).first()
        stock.reserved -= res.quantity
        session.commit()

        order = Order(id=order_id, reservation_id=res_id, sku_id=res.sku_id, quantity=res.quantity)
        session.add(order)
        session.commit()
        return order

    def cancel_reservation(self, session: Session, res_id: str) -> Reservation:
        res = session.query(Reservation).filter(Reservation.id == res_id).first()
        if not res:
            raise ValueError(f"Reservation {res_id} not found")
        if res.status != ReservationStatus.PENDING.value:
            raise ValueError(f"Reservation {res_id} is not pending")

        res.status = ReservationStatus.CANCELLED.value
        stock = session.query(Stock).filter(Stock.sku_id == res.sku_id).first()
        stock.available += res.quantity
        stock.reserved -= res.quantity
        session.commit()
        return res

    def list_orders(self, session: Session, skip: int, limit: int) -> tuple[list[Order], int]:
        total = session.query(Order).count()
        orders = session.query(Order).offset(skip).limit(limit).all()
        return orders, total
