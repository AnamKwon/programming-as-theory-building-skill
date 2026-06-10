from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from contextlib import contextmanager

DATABASE_URL = "sqlite:///./commerce.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class SKU(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String, unique=True, index=True)
    available_stock = Column(Integer)
    reserved_stock = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String, index=True)
    quantity = Column(Integer)
    idempotency_key = Column(String, unique=True, index=True)
    status = Column(String, default="PENDING")
    created_at = Column(DateTime, default=datetime.utcnow)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"))
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class Repository:
    def __init__(self, db: Session):
        self.db = db

    def create_sku(self, sku: str, initial_stock: int) -> SKU:
        db_sku = SKU(sku=sku, available_stock=initial_stock, reserved_stock=0)
        self.db.add(db_sku)
        self.db.commit()
        self.db.refresh(db_sku)
        return db_sku

    def get_sku_by_sku(self, sku: str) -> SKU | None:
        return self.db.query(SKU).filter(SKU.sku == sku).first()

    def adjust_stock(self, sku: str, amount: int) -> SKU:
        db_sku = self.get_sku_by_sku(sku)
        if not db_sku:
            raise ValueError(f"SKU {sku} not found")
        db_sku.available_stock += amount
        self.db.commit()
        self.db.refresh(db_sku)
        return db_sku

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Reservation | None:
        return self.db.query(Reservation).filter(
            Reservation.idempotency_key == idempotency_key
        ).first()

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str
    ) -> Reservation:
        db_reservation = Reservation(
            sku=sku,
            quantity=quantity,
            idempotency_key=idempotency_key,
            status="PENDING",
        )
        self.db.add(db_reservation)
        self.db.commit()
        self.db.refresh(db_reservation)
        return db_reservation

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

    def create_order(self, reservation_id: int) -> Order:
        db_order = Order(reservation_id=reservation_id)
        self.db.add(db_order)
        self.db.commit()
        self.db.refresh(db_order)
        return db_order

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[Order], int]:
        skip = (page - 1) * size
        orders = self.db.query(Order).offset(skip).limit(size).all()
        total = self.db.query(Order).count()
        return orders, total

    def update_sku_reserved_stock(self, sku_id: int, reserved_amount: int):
        db_sku = self.db.query(SKU).filter(SKU.id == sku_id).first()
        if db_sku:
            db_sku.reserved_stock += reserved_amount
            self.db.commit()
            self.db.refresh(db_sku)
        return db_sku
