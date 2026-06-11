import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.exc import IntegrityError

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class SKU(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String, unique=True, nullable=False, index=True)
    stock = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, default="PENDING")
    idempotency_key = Column(String, unique=True, nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


class Repository:
    def __init__(self, db: Session):
        self.db = db

    def create_sku(self, sku: str, initial_stock: int) -> SKU:
        db_sku = SKU(sku=sku, stock=initial_stock)
        self.db.add(db_sku)
        self.db.commit()
        self.db.refresh(db_sku)
        return db_sku

    def get_sku_by_sku_str(self, sku: str) -> SKU | None:
        return self.db.query(SKU).filter(SKU.sku == sku).first()

    def get_sku_by_id(self, sku_id: int) -> SKU | None:
        return self.db.query(SKU).filter(SKU.id == sku_id).first()

    def adjust_stock(self, sku: str, amount: int) -> int:
        db_sku = self.get_sku_by_sku_str(sku)
        if not db_sku:
            raise ValueError(f"SKU {sku} not found")

        db_sku.stock += amount
        self.db.commit()
        self.db.refresh(db_sku)
        return db_sku.stock

    def get_available_stock(self, sku_id: int) -> int:
        db_sku = self.get_sku_by_id(sku_id)
        if not db_sku:
            return 0
        return db_sku.stock

    def create_reservation(self, sku_id: int, quantity: int, idempotency_key: str | None = None) -> Reservation:
        reservation = Reservation(
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            status="PENDING"
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Reservation | None:
        return self.db.query(Reservation).filter(Reservation.idempotency_key == idempotency_key).first()

    def get_reservation_by_id(self, reservation_id: int) -> Reservation | None:
        return self.db.query(Reservation).filter(Reservation.id == reservation_id).first()

    def update_reservation_status(self, reservation_id: int, status: str) -> Reservation:
        reservation = self.get_reservation_by_id(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        reservation.status = status
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def deduct_stock(self, sku_id: int, quantity: int) -> None:
        db_sku = self.get_sku_by_id(sku_id)
        if not db_sku:
            raise ValueError(f"SKU {sku_id} not found")

        db_sku.stock -= quantity
        self.db.commit()

    def restore_stock(self, sku_id: int, quantity: int) -> None:
        db_sku = self.get_sku_by_id(sku_id)
        if not db_sku:
            raise ValueError(f"SKU {sku_id} not found")

        db_sku.stock += quantity
        self.db.commit()

    def create_order(self, reservation_id: int) -> Order:
        order = Order(reservation_id=reservation_id)
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def get_orders(self, offset: int = 0, limit: int = 10) -> tuple[list[Order], int]:
        total = self.db.query(Order).count()
        orders = self.db.query(Order).offset(offset).limit(limit).all()
        return orders, total
