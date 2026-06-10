from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
from datetime import datetime, timedelta, UTC
import enum
from contextlib import contextmanager

DATABASE_URL = "sqlite:///./commerce.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class ReservationStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderStatus(str, enum.Enum):
    RESERVED = "reserved"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class SKUModel(Base):
    __tablename__ = "skus"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, index=True)
    quantity = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    reservations = relationship("ReservationModel", back_populates="sku")


class ReservationModel(Base):
    __tablename__ = "reservations"
    id = Column(Integer, primary_key=True, index=True)
    sku_id = Column(Integer, ForeignKey("skus.id"))
    quantity = Column(Integer)
    status = Column(Enum(ReservationStatus), default=ReservationStatus.PENDING, index=True)
    idempotency_key = Column(String(255), unique=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    expires_at = Column(DateTime, default=lambda: datetime.now(UTC) + timedelta(minutes=15))

    sku = relationship("SKUModel", back_populates="reservations")
    order = relationship("OrderModel", back_populates="reservations", uselist=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)


class OrderModel(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    status = Column(Enum(OrderStatus), default=OrderStatus.RESERVED, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    reservations = relationship("ReservationModel", back_populates="order")


def init_db():
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


class Repository:
    def __init__(self, session: Session):
        self.session = session

    def create_sku(self, name: str, quantity: int) -> SKUModel:
        sku = SKUModel(name=name, quantity=quantity)
        self.session.add(sku)
        self.session.commit()
        self.session.refresh(sku)
        return sku

    def get_sku(self, sku_id: int) -> SKUModel | None:
        return self.session.query(SKUModel).filter(SKUModel.id == sku_id).first()

    def get_sku_by_name(self, name: str) -> SKUModel | None:
        return self.session.query(SKUModel).filter(SKUModel.name == name).first()

    def adjust_stock(self, sku_id: int, delta: int) -> SKUModel | None:
        sku = self.get_sku(sku_id)
        if not sku:
            return None
        sku.quantity = max(0, sku.quantity + delta)
        self.session.commit()
        self.session.refresh(sku)
        return sku

    def create_reservation(
        self, sku_id: int, quantity: int, idempotency_key: str
    ) -> ReservationModel:
        reservation = ReservationModel(
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
        )
        self.session.add(reservation)
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    def get_reservation(self, reservation_id: int) -> ReservationModel | None:
        return self.session.query(ReservationModel).filter(
            ReservationModel.id == reservation_id
        ).first()

    def get_reservation_by_idempotency_key(self, key: str) -> ReservationModel | None:
        return self.session.query(ReservationModel).filter(
            ReservationModel.idempotency_key == key
        ).first()

    def update_reservation_status(
        self, reservation_id: int, status: ReservationStatus
    ) -> ReservationModel | None:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            return None
        reservation.status = status
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    def create_order(self, reservations: list[ReservationModel]) -> OrderModel:
        order = OrderModel()
        self.session.add(order)
        self.session.flush()

        for res in reservations:
            res.order_id = order.id

        self.session.commit()
        self.session.refresh(order)
        return order

    def get_order(self, order_id: int) -> OrderModel | None:
        return self.session.query(OrderModel).filter(OrderModel.id == order_id).first()

    def list_orders(self, offset: int = 0, limit: int = 10) -> tuple[list[OrderModel], int]:
        total = self.session.query(OrderModel).count()
        orders = self.session.query(OrderModel).offset(offset).limit(limit).all()
        return orders, total

    def update_order_status(self, order_id: int, status: OrderStatus) -> OrderModel | None:
        order = self.get_order(order_id)
        if not order:
            return None
        order.status = status
        self.session.commit()
        self.session.refresh(order)
        return order

    def list_reservations_by_order(self, order_id: int) -> list[ReservationModel]:
        return self.session.query(ReservationModel).filter(
            ReservationModel.order_id == order_id
        ).all()
