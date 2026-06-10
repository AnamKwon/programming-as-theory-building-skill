from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

DATABASE_URL = "sqlite:///./commerce.db"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class SKU(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String, unique=True, index=True)
    available_stock = Column(Integer)


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String, index=True)
    quantity = Column(Integer)
    status = Column(String, default="PENDING")
    idempotency_key = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    reservation_id = Column(Integer, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class SKURepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_sku(self, sku: str) -> SKU | None:
        return self.db.query(SKU).filter(SKU.sku == sku).first()

    def get_by_id(self, id: int) -> SKU | None:
        return self.db.query(SKU).filter(SKU.id == id).first()

    def create(self, sku: str, initial_stock: int) -> SKU:
        db_sku = SKU(sku=sku, available_stock=initial_stock)
        self.db.add(db_sku)
        self.db.commit()
        self.db.refresh(db_sku)
        return db_sku

    def update_stock(self, sku: str, amount: int) -> SKU | None:
        db_sku = self.get_by_sku(sku)
        if db_sku:
            db_sku.available_stock += amount
            self.db.commit()
            self.db.refresh(db_sku)
        return db_sku


class ReservationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, id: int) -> Reservation | None:
        return self.db.query(Reservation).filter(Reservation.id == id).first()

    def get_by_idempotency_key(self, key: str) -> Reservation | None:
        return self.db.query(Reservation).filter(Reservation.idempotency_key == key).first()

    def create(self, sku: str, quantity: int, idempotency_key: str, status: str = "PENDING") -> Reservation:
        db_reservation = Reservation(
            sku=sku,
            quantity=quantity,
            idempotency_key=idempotency_key,
            status=status,
        )
        self.db.add(db_reservation)
        self.db.commit()
        self.db.refresh(db_reservation)
        return db_reservation

    def update_status(self, id: int, status: str) -> Reservation | None:
        db_reservation = self.get_by_id(id)
        if db_reservation:
            db_reservation.status = status
            db_reservation.updated_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(db_reservation)
        return db_reservation


class OrderRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, reservation_id: int) -> Order:
        db_order = Order(reservation_id=reservation_id)
        self.db.add(db_order)
        self.db.commit()
        self.db.refresh(db_order)
        return db_order

    def get_all(self, page: int = 1, size: int = 10) -> tuple[list[Order], int]:
        total = self.db.query(Order).count()
        offset = (page - 1) * size
        orders = self.db.query(Order).offset(offset).limit(size).all()
        return orders, total
