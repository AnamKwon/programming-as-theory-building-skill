from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session

Base = declarative_base()
DATABASE_URL = "sqlite:///./commerce.db"


class SKU(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String, unique=True, index=True, nullable=False)
    available_stock = Column(Integer, nullable=False, default=0)


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False)
    sku = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="PENDING")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    idempotency_key = Column(String, unique=True, index=True, nullable=False)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize database schema."""
    Base.metadata.create_all(bind=engine)


def get_session() -> Session:
    """Get database session."""
    return SessionLocal()


class Repository:
    def __init__(self, session: Session):
        self.session = session

    def create_sku(self, sku: str, initial_stock: int) -> SKU:
        """Create a new SKU with initial stock."""
        db_sku = SKU(sku=sku, available_stock=initial_stock)
        self.session.add(db_sku)
        self.session.commit()
        self.session.refresh(db_sku)
        return db_sku

    def get_sku_by_name(self, sku: str) -> Optional[SKU]:
        """Retrieve SKU by name."""
        return self.session.query(SKU).filter(SKU.sku == sku).first()

    def adjust_stock(self, sku: str, amount: int) -> Optional[SKU]:
        """Adjust stock for a SKU (positive or negative)."""
        db_sku = self.get_sku_by_name(sku)
        if not db_sku:
            return None
        db_sku.available_stock += amount
        self.session.commit()
        self.session.refresh(db_sku)
        return db_sku

    def get_reservation_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[Reservation]:
        """Check if a reservation with given idempotency key exists."""
        return self.session.query(Reservation).filter(
            Reservation.idempotency_key == idempotency_key
        ).first()

    def create_reservation(
        self,
        sku_id: int,
        sku: str,
        quantity: int,
        idempotency_key: str,
    ) -> Reservation:
        """Create a new reservation."""
        now = datetime.utcnow()
        reservation = Reservation(
            sku_id=sku_id,
            sku=sku,
            quantity=quantity,
            idempotency_key=idempotency_key,
            status="PENDING",
            created_at=now,
            updated_at=now,
        )
        self.session.add(reservation)
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    def get_reservation(self, reservation_id: int) -> Optional[Reservation]:
        """Retrieve a reservation by ID."""
        return self.session.query(Reservation).filter(
            Reservation.id == reservation_id
        ).first()

    def update_reservation_status(
        self, reservation_id: int, status: str
    ) -> Optional[Reservation]:
        """Update the status of a reservation."""
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            return None
        reservation.status = status
        reservation.updated_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(reservation)
        return reservation

    def create_order(self, reservation_id: int) -> Order:
        """Create a new order from a reservation."""
        order = Order(reservation_id=reservation_id, created_at=datetime.utcnow())
        self.session.add(order)
        self.session.commit()
        self.session.refresh(order)
        return order

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[Order], int]:
        """Get paginated orders."""
        query = self.session.query(Order)
        total = query.count()
        offset = (page - 1) * size
        orders = query.offset(offset).limit(size).all()
        return orders, total

    def commit(self):
        """Commit the current transaction."""
        self.session.commit()

    def rollback(self):
        """Rollback the current transaction."""
        self.session.rollback()

    def close(self):
        """Close the session."""
        self.session.close()
