import os
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Literal
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class SKUModel(Base):
    __tablename__ = "skus"
    id = Column(Integer, primary_key=True, index=True)
    sku_code = Column(String, unique=True, index=True)
    name = Column(String)
    stock_count = Column(Integer, default=0)


class ReservationModel(Base):
    __tablename__ = "reservations"
    id = Column(Integer, primary_key=True, index=True)
    sku_id = Column(Integer, index=True)
    quantity = Column(Integer)
    state = Column(String, default="pending")
    idempotency_key = Column(String, unique=True, index=True)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


class OrderModel(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    sku_id = Column(Integer, index=True)
    quantity = Column(Integer)
    state = Column(String, default="reserved")
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class Repository:
    def __init__(self, db: Session):
        self.db = db

    def create_sku(self, sku_code: str, name: str, stock_count: int) -> SKUModel:
        sku = SKUModel(sku_code=sku_code, name=name, stock_count=stock_count)
        self.db.add(sku)
        self.db.commit()
        self.db.refresh(sku)
        return sku

    def get_sku(self, sku_id: int) -> SKUModel | None:
        return self.db.query(SKUModel).filter(SKUModel.id == sku_id).first()

    def update_sku_stock(self, sku_id: int, quantity_delta: int) -> SKUModel | None:
        sku = self.get_sku(sku_id)
        if sku:
            sku.stock_count += quantity_delta
            self.db.commit()
            self.db.refresh(sku)
        return sku

    def create_reservation(
        self, sku_id: int, quantity: int, idempotency_key: str, expires_at: datetime
    ) -> ReservationModel:
        reservation = ReservationModel(
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def get_reservation(self, reservation_id: int) -> ReservationModel | None:
        return self.db.query(ReservationModel).filter(ReservationModel.id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, key: str) -> ReservationModel | None:
        return self.db.query(ReservationModel).filter(ReservationModel.idempotency_key == key).first()

    def update_reservation_state(self, reservation_id: int, state: str) -> ReservationModel | None:
        reservation = self.get_reservation(reservation_id)
        if reservation:
            reservation.state = state
            self.db.commit()
            self.db.refresh(reservation)
        return reservation

    def create_order(self, sku_id: int, quantity: int, state: str = "reserved") -> OrderModel:
        order = OrderModel(sku_id=sku_id, quantity=quantity, state=state)
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def get_order(self, order_id: int) -> OrderModel | None:
        return self.db.query(OrderModel).filter(OrderModel.id == order_id).first()

    def update_order_state(self, order_id: int, state: str) -> OrderModel | None:
        order = self.get_order(order_id)
        if order:
            order.state = state
            self.db.commit()
            self.db.refresh(order)
        return order

    def list_orders(self, page: int = 1, page_size: int = 10) -> tuple[list[OrderModel], int]:
        total = self.db.query(OrderModel).count()
        orders = (
            self.db.query(OrderModel)
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return orders, total
