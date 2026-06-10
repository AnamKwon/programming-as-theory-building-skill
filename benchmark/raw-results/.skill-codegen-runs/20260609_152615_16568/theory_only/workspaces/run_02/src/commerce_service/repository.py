"""Database repository layer."""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from .models import ReservationStatus, OrderStatus

DATABASE_URL = "sqlite:///./commerce.db"
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class SKUModel(Base):
    """Database model for SKU."""
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    stock = Column(Integer, default=0, nullable=False)
    reserved = Column(Integer, default=0, nullable=False)


class ReservationModel(Base):
    """Database model for Reservation."""
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(ReservationStatus), default=ReservationStatus.PENDING, nullable=False)
    idempotency_key = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)


class OrderModel(Base):
    """Database model for Order."""
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=False)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class Repository:
    """Data access layer."""

    def __init__(self, db: Session):
        self.db = db

    # SKU operations
    def get_sku(self, sku_id: int) -> Optional[SKUModel]:
        """Get SKU by ID."""
        return self.db.query(SKUModel).filter(SKUModel.id == sku_id).first()

    def get_sku_by_code(self, code: str) -> Optional[SKUModel]:
        """Get SKU by code."""
        return self.db.query(SKUModel).filter(SKUModel.code == code).first()

    def create_sku(self, code: str, name: str) -> SKUModel:
        """Create a new SKU."""
        sku = SKUModel(code=code, name=name, stock=0, reserved=0)
        self.db.add(sku)
        self.db.commit()
        self.db.refresh(sku)
        return sku

    def adjust_stock(self, sku_id: int, adjustment: int) -> Optional[SKUModel]:
        """Adjust stock for a SKU."""
        sku = self.get_sku(sku_id)
        if not sku:
            return None
        sku.stock = max(0, sku.stock + adjustment)
        self.db.commit()
        self.db.refresh(sku)
        return sku

    # Reservation operations
    def get_reservation(self, reservation_id: int) -> Optional[ReservationModel]:
        """Get reservation by ID."""
        return self.db.query(ReservationModel).filter(ReservationModel.id == reservation_id).first()

    def get_reservation_by_idempotency_key(self, key: str) -> Optional[ReservationModel]:
        """Get reservation by idempotency key."""
        return self.db.query(ReservationModel).filter(
            ReservationModel.idempotency_key == key
        ).first()

    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        idempotency_key: str,
        expires_at: datetime
    ) -> ReservationModel:
        """Create a new reservation."""
        reservation = ReservationModel(
            sku_id=sku_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
            status=ReservationStatus.PENDING,
            expires_at=expires_at
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def update_reservation_status(
        self,
        reservation_id: int,
        status: ReservationStatus
    ) -> Optional[ReservationModel]:
        """Update reservation status."""
        reservation = self.get_reservation(reservation_id)
        if not reservation:
            return None
        reservation.status = status
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def update_sku_reserved(self, sku_id: int, adjustment: int) -> Optional[SKUModel]:
        """Update reserved quantity for a SKU."""
        sku = self.get_sku(sku_id)
        if not sku:
            return None
        sku.reserved = max(0, sku.reserved + adjustment)
        self.db.commit()
        self.db.refresh(sku)
        return sku

    # Order operations
    def get_order(self, order_id: int) -> Optional[OrderModel]:
        """Get order by ID."""
        return self.db.query(OrderModel).filter(OrderModel.id == order_id).first()

    def create_order(self, reservation_id: int) -> OrderModel:
        """Create a new order."""
        order = OrderModel(reservation_id=reservation_id, status=OrderStatus.PENDING)
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def list_orders(self, offset: int = 0, limit: int = 20) -> tuple[list[OrderModel], int]:
        """List orders with pagination."""
        query = self.db.query(OrderModel).order_by(OrderModel.created_at.desc())
        total = query.count()
        items = query.offset(offset).limit(limit).all()
        return items, total
