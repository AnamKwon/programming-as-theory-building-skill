import os
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, Session

Base = declarative_base()

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///:memory:")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class SKU(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True, index=True)
    sku_name = Column(String(100), unique=True, nullable=False, index=True)
    available_stock = Column(Integer, nullable=False, default=0)
    reserved_stock = Column(Integer, nullable=False, default=0)


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)
    sku_id = Column(Integer, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String(50), nullable=False, default="pending")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    idempotency_key = Column(String(256), unique=True, nullable=False, index=True)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    reservation_id = Column(Integer, nullable=False, index=True)
    status = Column(String(50), nullable=False, default="confirmed")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


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

    def create_sku(self, sku_name: str, initial_stock: int) -> SKU:
        sku = SKU(sku_name=sku_name, available_stock=initial_stock, reserved_stock=0)
        self.db.add(sku)
        self.db.commit()
        self.db.refresh(sku)
        return sku

    def get_sku(self, sku_id: int) -> SKU | None:
        return self.db.query(SKU).filter(SKU.id == sku_id).first()

    def get_sku_by_name(self, sku_name: str) -> SKU | None:
        return self.db.query(SKU).filter(SKU.sku_name == sku_name).first()

    def adjust_stock(self, sku_id: int, delta: int) -> SKU:
        sku = self.get_sku(sku_id)
        if not sku:
            raise ValueError(f"SKU {sku_id} not found")
        sku.available_stock += delta
        self.db.commit()
        self.db.refresh(sku)
        return sku

    def create_reservation(
        self, sku_id: int, quantity: int, idempotency_key: str, ttl_seconds: int = 3600
    ) -> Reservation:
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        reservation = Reservation(
            sku_id=sku_id,
            quantity=quantity,
            status="pending",
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def get_reservation(self, reservation_id: int) -> Reservation | None:
        return self.db.query(Reservation).filter(Reservation.id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Reservation | None:
        return (
            self.db.query(Reservation)
            .filter(Reservation.idempotency_key == idempotency_key)
            .first()
        )

    def update_reservation_status(self, reservation_id: int, status: str) -> Reservation:
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")
        reservation.status = status
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def create_order(self, reservation_id: int, status: str = "confirmed") -> Order:
        order = Order(reservation_id=reservation_id, status=status)
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def get_order(self, order_id: int) -> Order | None:
        return self.db.query(Order).filter(Order.id == order_id).first()

    def get_orders(self, limit: int = 10, offset: int = 0) -> tuple[list[Order], int]:
        query = self.db.query(Order)
        total = query.count()
        orders = query.limit(limit).offset(offset).all()
        return orders, total

    def get_orders_by_reservation_id(self, reservation_id: int) -> list[Order]:
        return self.db.query(Order).filter(Order.reservation_id == reservation_id).all()
