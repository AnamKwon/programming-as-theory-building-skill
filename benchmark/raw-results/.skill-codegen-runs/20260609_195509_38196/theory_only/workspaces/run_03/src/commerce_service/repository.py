"""Data access layer using SQLAlchemy and SQLite."""
import sqlite3
from datetime import datetime, timedelta
from threading import Lock

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    Enum as SQLEnum,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.pool import StaticPool

from .models import ReservationState, OrderState


Base = declarative_base()


class SKU(Base):
    __tablename__ = "skus"
    id = Column(Integer, primary_key=True)
    sku = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Inventory(Base):
    __tablename__ = "inventory"
    id = Column(Integer, primary_key=True)
    sku_id = Column(String, nullable=False, unique=True)
    available = Column(Integer, default=0, nullable=False)
    reserved = Column(Integer, default=0, nullable=False)


class Reservation(Base):
    __tablename__ = "reservations"
    id = Column(Integer, primary_key=True)
    sku_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    state = Column(SQLEnum(ReservationState), default=ReservationState.PENDING, nullable=False)
    idempotency_key = Column(String, nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, nullable=False)
    state = Column(SQLEnum(OrderState), default=OrderState.PENDING, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Repository:
    """Repository for all database operations."""

    def __init__(self, db_url: str = "sqlite:///commerce.db"):
        self.engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self._lock = Lock()

    def _get_session(self) -> Session:
        return self.SessionLocal()

    def create_sku(self, sku: str, name: str) -> SKU:
        """Create a new SKU."""
        session = self._get_session()
        try:
            db_sku = SKU(sku=sku, name=name)
            session.add(db_sku)
            session.commit()
            session.refresh(db_sku)
            return db_sku
        finally:
            session.close()

    def get_sku(self, sku_id: str) -> SKU | None:
        """Get SKU by ID."""
        session = self._get_session()
        try:
            return session.query(SKU).filter(SKU.sku == sku_id).first()
        finally:
            session.close()

    def adjust_stock(self, sku_id: str, adjustment: int) -> int:
        """Adjust stock level for a SKU. Returns new available quantity."""
        with self._lock:
            session = self._get_session()
            try:
                inv = session.query(Inventory).filter(Inventory.sku_id == sku_id).first()
                if not inv:
                    inv = Inventory(sku_id=sku_id, available=max(0, adjustment))
                    session.add(inv)
                else:
                    inv.available = max(0, inv.available + adjustment)
                session.commit()
                return inv.available
            finally:
                session.close()

    def get_inventory(self, sku_id: str) -> tuple[int, int]:
        """Get current inventory (available, reserved) for a SKU."""
        session = self._get_session()
        try:
            inv = session.query(Inventory).filter(Inventory.sku_id == sku_id).first()
            if not inv:
                return (0, 0)
            return (inv.available, inv.reserved)
        finally:
            session.close()

    def create_reservation(
        self,
        sku_id: str,
        quantity: int,
        idempotency_key: str,
        ttl_minutes: int = 5,
    ) -> Reservation | None:
        """Create a reservation. Returns None if idempotency key already exists."""
        with self._lock:
            session = self._get_session()
            try:
                existing = session.query(Reservation).filter(
                    Reservation.idempotency_key == idempotency_key
                ).first()
                if existing:
                    return None

                expires_at = datetime.utcnow() + timedelta(minutes=ttl_minutes)
                reservation = Reservation(
                    sku_id=sku_id,
                    quantity=quantity,
                    idempotency_key=idempotency_key,
                    expires_at=expires_at,
                )
                session.add(reservation)
                session.commit()
                session.refresh(reservation)
                return reservation
            finally:
                session.close()

    def get_reservation(self, reservation_id: int) -> Reservation | None:
        """Get reservation by ID."""
        session = self._get_session()
        try:
            return session.query(Reservation).filter(Reservation.id == reservation_id).first()
        finally:
            session.close()

    def update_reservation_state(self, reservation_id: int, state: ReservationState) -> bool:
        """Update reservation state. Returns True if successful."""
        session = self._get_session()
        try:
            res = session.query(Reservation).filter(Reservation.id == reservation_id).first()
            if not res:
                return False
            res.state = state
            session.commit()
            return True
        finally:
            session.close()

    def reserve_stock(self, sku_id: str, quantity: int) -> bool:
        """Atomically reserve stock if available. Returns True if successful."""
        with self._lock:
            session = self._get_session()
            try:
                inv = session.query(Inventory).filter(Inventory.sku_id == sku_id).first()
                if not inv or inv.available < quantity:
                    return False
                inv.available -= quantity
                inv.reserved += quantity
                session.commit()
                return True
            finally:
                session.close()

    def release_reserved_stock(self, sku_id: str, quantity: int) -> bool:
        """Release reserved stock back to available. Returns True if successful."""
        with self._lock:
            session = self._get_session()
            try:
                inv = session.query(Inventory).filter(Inventory.sku_id == sku_id).first()
                if not inv:
                    return False
                inv.reserved = max(0, inv.reserved - quantity)
                inv.available += quantity
                session.commit()
                return True
            finally:
                session.close()

    def create_order(self, reservation_id: int) -> Order:
        """Create an order from a confirmed reservation."""
        session = self._get_session()
        try:
            order = Order(reservation_id=reservation_id)
            session.add(order)
            session.commit()
            session.refresh(order)
            return order
        finally:
            session.close()

    def list_orders(self, page: int = 1, page_size: int = 10) -> tuple[list[Order], int]:
        """List orders with pagination. Returns (orders, total_count)."""
        session = self._get_session()
        try:
            query = session.query(Order).order_by(Order.created_at.desc())
            total = query.count()
            orders = query.offset((page - 1) * page_size).limit(page_size).all()
            return (orders, total)
        finally:
            session.close()
