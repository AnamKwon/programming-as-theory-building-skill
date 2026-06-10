"""Database access layer using SQLAlchemy ORM."""

from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Enum as SQLEnum, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from commerce_service.models import ReservationStatus, OrderStatus


DATABASE_URL = "sqlite:///./commerce.db"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}, echo=False
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class SKU(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    sku_code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    stock_count = Column(Integer, default=0)


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(ReservationStatus), default=ReservationStatus.PENDING)
    idempotency_key = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)


class Repository:
    def __init__(self, session: Session):
        self.session = session

    def create_sku(self, sku_code: str, name: str, initial_stock: int) -> SKU:
        sku = SKU(sku_code=sku_code, name=name, stock_count=initial_stock)
        self.session.add(sku)
        self.session.commit()
        self.session.refresh(sku)
        return sku

    def get_sku(self, sku_id: int) -> Optional[SKU]:
        return self.session.query(SKU).filter(SKU.id == sku_id).first()

    def update_sku_stock(self, sku_id: int, quantity_delta: int) -> Optional[SKU]:
        sku = self.get_sku(sku_id)
        if not sku:
            return None
        sku.stock_count += quantity_delta
        self.session.commit()
        self.session.refresh(sku)
        return sku

    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        expires_at: datetime,
        idempotency_key: Optional[str] = None,
    ) -> Reservation:
        reservation = Reservation(
            sku_id=sku_id,
            quantity=quantity,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )
        self.session.add(reservation)
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    def get_reservation(self, reservation_id: int) -> Optional[Reservation]:
        return self.session.query(Reservation).filter(Reservation.id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, key: str) -> Optional[Reservation]:
        return (
            self.session.query(Reservation)
            .filter(Reservation.idempotency_key == key)
            .first()
        )

    def update_reservation_status(
        self, reservation_id: int, status: ReservationStatus
    ) -> Optional[Reservation]:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            return None
        reservation.status = status
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    def update_reservation_order_id(
        self, reservation_id: int, order_id: int
    ) -> Optional[Reservation]:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            return None
        reservation.order_id = order_id
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    def create_order(self) -> Order:
        order = Order(status=OrderStatus.PENDING)
        self.session.add(order)
        self.session.commit()
        self.session.refresh(order)
        return order

    def get_order(self, order_id: int) -> Optional[Order]:
        return self.session.query(Order).filter(Order.id == order_id).first()

    def update_order_status(self, order_id: int, status: OrderStatus) -> Optional[Order]:
        order = self.get_order(order_id)
        if not order:
            return None
        order.status = status
        self.session.commit()
        self.session.refresh(order)
        return order

    def list_orders(self, offset: int = 0, limit: int = 20) -> tuple[list[Order], int]:
        total = self.session.query(Order).count()
        orders = (
            self.session.query(Order)
            .order_by(Order.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return orders, total


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
