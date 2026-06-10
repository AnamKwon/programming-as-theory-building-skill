"""Database repository layer."""

import os
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import declarative_base, sessionmaker, Session

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class SKUModel(Base):
    """Database model for SKUs."""

    __tablename__ = "skus"

    sku = Column(String, primary_key=True, index=True)
    stock = Column(Integer, default=0)


class ReservationModel(Base):
    """Database model for reservations."""

    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String, ForeignKey("skus.sku"), index=True)
    quantity = Column(Integer)
    status = Column(String, default="PENDING")
    idempotency_key = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class OrderModel(Base):
    """Database model for orders."""

    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)


class Repository:
    """Repository for database operations."""

    def __init__(self, session: Session):
        """Initialize repository with database session."""
        self.session = session

    def create_sku(self, sku: str, stock: int) -> SKUModel:
        """Create a new SKU."""
        sku_model = SKUModel(sku=sku, stock=stock)
        self.session.add(sku_model)
        self.session.commit()
        self.session.refresh(sku_model)
        return sku_model

    def get_sku(self, sku: str) -> Optional[SKUModel]:
        """Get a SKU by code."""
        stmt = select(SKUModel).where(SKUModel.sku == sku)
        return self.session.execute(stmt).scalars().first()

    def update_sku_stock(self, sku: str, new_stock: int) -> Optional[SKUModel]:
        """Update SKU stock level."""
        sku_model = self.get_sku(sku)
        if sku_model:
            sku_model.stock = new_stock
            self.session.commit()
            self.session.refresh(sku_model)
        return sku_model

    def create_reservation(
        self,
        sku: str,
        quantity: int,
        idempotency_key: str,
    ) -> Optional[ReservationModel]:
        """Create a new reservation.

        Returns None if idempotency_key already exists.
        """
        reservation = ReservationModel(
            sku=sku,
            quantity=quantity,
            idempotency_key=idempotency_key,
            status="PENDING",
        )
        self.session.add(reservation)
        try:
            self.session.commit()
            self.session.refresh(reservation)
            return reservation
        except IntegrityError:
            self.session.rollback()
            return None

    def get_reservation_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[ReservationModel]:
        """Get reservation by idempotency key."""
        stmt = select(ReservationModel).where(
            ReservationModel.idempotency_key == idempotency_key
        )
        return self.session.execute(stmt).scalars().first()

    def get_reservation(self, reservation_id: int) -> Optional[ReservationModel]:
        """Get a reservation by ID."""
        return self.session.query(ReservationModel).filter_by(id=reservation_id).first()

    def update_reservation_status(
        self, reservation_id: int, status: str
    ) -> Optional[ReservationModel]:
        """Update reservation status."""
        reservation = self.get_reservation(reservation_id)
        if reservation:
            reservation.status = status
            self.session.commit()
            self.session.refresh(reservation)
        return reservation

    def create_order(self, reservation_id: int) -> OrderModel:
        """Create a new order."""
        order = OrderModel(reservation_id=reservation_id)
        self.session.add(order)
        self.session.commit()
        self.session.refresh(order)
        return order

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[OrderModel], int]:
        """Get paginated orders.

        Returns tuple of (orders, total_count).
        """
        total = self.session.query(OrderModel).count()
        offset = (page - 1) * size
        orders = (
            self.session.query(OrderModel)
            .offset(offset)
            .limit(size)
            .all()
        )
        return orders, total
