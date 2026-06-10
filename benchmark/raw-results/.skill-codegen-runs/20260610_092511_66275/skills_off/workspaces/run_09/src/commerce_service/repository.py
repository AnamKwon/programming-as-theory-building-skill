from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship

Base = declarative_base()


class SkuDB(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(255), nullable=False)

    stocks = relationship("StockDB", back_populates="sku", cascade="all, delete-orphan")
    reservations = relationship("ReservationDB", back_populates="sku")


class StockDB(Base):
    __tablename__ = "stocks"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), unique=True, nullable=False)
    quantity_available = Column(Integer, default=0, nullable=False)

    sku = relationship("SkuDB", back_populates="stocks")


class OrderDB(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    status = Column(String(50), default="pending", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    reservations = relationship("ReservationDB", back_populates="order", cascade="all, delete-orphan")


class ReservationDB(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String(50), default="pending", nullable=False)
    idempotency_key = Column(String(255), unique=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime, nullable=True)

    order = relationship("OrderDB", back_populates="reservations")
    sku = relationship("SkuDB", back_populates="reservations")


class Repository:
    def __init__(self, database_url: str = "sqlite:///commerce.db"):
        self.engine = create_engine(database_url, connect_args={"check_same_thread": False})
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()

    def create_sku(self, session: Session, code: str, name: str) -> SkuDB:
        sku = SkuDB(code=code, name=name)
        stock = StockDB(sku=sku, quantity_available=0)
        session.add(sku)
        session.add(stock)
        session.commit()
        session.refresh(sku)
        return sku

    def get_sku_by_id(self, session: Session, sku_id: int) -> Optional[SkuDB]:
        return session.query(SkuDB).filter(SkuDB.id == sku_id).first()

    def adjust_stock(self, session: Session, sku_id: int, quantity_delta: int) -> Optional[StockDB]:
        stock = session.query(StockDB).filter(StockDB.sku_id == sku_id).first()
        if not stock:
            return None
        stock.quantity_available = max(0, stock.quantity_available + quantity_delta)
        session.commit()
        session.refresh(stock)
        return stock

    def get_stock(self, session: Session, sku_id: int) -> Optional[StockDB]:
        return session.query(StockDB).filter(StockDB.sku_id == sku_id).first()

    def create_reservation(
        self,
        session: Session,
        sku_id: int,
        quantity: int,
        idempotency_key: str,
        expires_at: Optional[datetime] = None,
    ) -> tuple[ReservationDB, OrderDB]:
        order = OrderDB(status="pending")
        session.add(order)
        session.flush()

        reservation = ReservationDB(
            order_id=order.id,
            sku_id=sku_id,
            quantity=quantity,
            status="pending",
            idempotency_key=idempotency_key,
            expires_at=expires_at,
        )
        session.add(reservation)
        session.commit()
        session.refresh(order)
        session.refresh(reservation)
        return reservation, order

    def get_reservation_by_id(self, session: Session, reservation_id: int) -> Optional[ReservationDB]:
        return session.query(ReservationDB).filter(ReservationDB.id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, session: Session, key: str) -> Optional[ReservationDB]:
        return session.query(ReservationDB).filter(ReservationDB.idempotency_key == key).first()

    def update_reservation_status(
        self, session: Session, reservation_id: int, status: str
    ) -> Optional[ReservationDB]:
        reservation = self.get_reservation_by_id(session, reservation_id)
        if not reservation:
            return None
        reservation.status = status
        session.commit()
        session.refresh(reservation)
        return reservation

    def get_order_by_id(self, session: Session, order_id: int) -> Optional[OrderDB]:
        return session.query(OrderDB).filter(OrderDB.id == order_id).first()

    def list_orders(self, session: Session, page: int = 1, page_size: int = 10) -> tuple[list[OrderDB], int]:
        query = session.query(OrderDB).order_by(OrderDB.created_at.desc())
        total = query.count()
        offset = (page - 1) * page_size
        orders = query.offset(offset).limit(page_size).all()
        return orders, total

    def get_pending_reservations(self, session: Session) -> list[ReservationDB]:
        return session.query(ReservationDB).filter(ReservationDB.status == "pending").all()

    def update_order_status(self, session: Session, order_id: int, status: str) -> Optional[OrderDB]:
        order = self.get_order_by_id(session, order_id)
        if not order:
            return None
        order.status = status
        order.updated_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(order)
        return order
