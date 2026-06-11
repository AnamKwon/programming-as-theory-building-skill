"""Data access layer for database operations."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Integer, String, DateTime, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

Base = declarative_base()
DATABASE_URL = "sqlite:///./commerce.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class SKUModel(Base):
    """SKU database model."""
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String, unique=True, index=True)
    available_stock = Column(Integer)


class ReservationModel(Base):
    """Reservation database model."""
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String, index=True)
    quantity = Column(Integer)
    status = Column(String, default="PENDING")
    idempotency_key = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class OrderModel(Base):
    """Order database model."""
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    reservation_id = Column(Integer, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Get database session for dependency injection."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class Repository:
    """Repository for all database operations."""

    def __init__(self, db: Session):
        self.db = db

    def create_sku(self, sku: str, initial_stock: int) -> SKUModel:
        """Create a new SKU with initial stock."""
        sku_record = SKUModel(sku=sku, available_stock=initial_stock)
        self.db.add(sku_record)
        self.db.commit()
        self.db.refresh(sku_record)
        return sku_record

    def get_sku_by_name(self, sku: str) -> Optional[SKUModel]:
        """Get SKU by name."""
        return self.db.query(SKUModel).filter(SKUModel.sku == sku).first()

    def adjust_stock(self, sku: str, amount: int) -> Optional[SKUModel]:
        """Adjust stock for a SKU by amount (positive or negative)."""
        sku_record = self.get_sku_by_name(sku)
        if not sku_record:
            return None
        sku_record.available_stock += amount
        self.db.commit()
        self.db.refresh(sku_record)
        return sku_record

    def create_reservation(
        self,
        sku: str,
        quantity: int,
        idempotency_key: str,
    ) -> ReservationModel:
        """Create a new reservation."""
        reservation = ReservationModel(
            sku=sku,
            quantity=quantity,
            idempotency_key=idempotency_key,
            status="PENDING",
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def get_reservation_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> Optional[ReservationModel]:
        """Get reservation by idempotency key."""
        return self.db.query(ReservationModel).filter(
            ReservationModel.idempotency_key == idempotency_key
        ).first()

    def get_reservation_by_id(self, reservation_id: int) -> Optional[ReservationModel]:
        """Get reservation by ID."""
        return self.db.query(ReservationModel).filter(
            ReservationModel.id == reservation_id
        ).first()

    def update_reservation_status(
        self,
        reservation_id: int,
        status: str,
    ) -> Optional[ReservationModel]:
        """Update reservation status."""
        reservation = self.get_reservation_by_id(reservation_id)
        if not reservation:
            return None
        reservation.status = status
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def create_order(self, reservation_id: int) -> OrderModel:
        """Create a new order from a reservation."""
        order = OrderModel(reservation_id=reservation_id)
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def get_orders_paginated(self, page: int = 1, size: int = 10) -> tuple[list[OrderModel], int]:
        """Get paginated list of orders."""
        total = self.db.query(OrderModel).count()
        offset = (page - 1) * size
        orders = self.db.query(OrderModel).offset(offset).limit(size).all()
        return orders, total
