from datetime import datetime, timedelta, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
import enum

Base = declarative_base()


class ReservationState(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class SKU(Base):
    __tablename__ = "skus"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class Stock(Base):
    __tablename__ = "stock"

    id = Column(Integer, primary_key=True)
    sku_id = Column(String, ForeignKey("skus.id"), nullable=False, unique=True)
    quantity = Column(Integer, default=0, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(String, primary_key=True)
    sku_id = Column(String, ForeignKey("skus.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    idempotency_key = Column(String, nullable=False, unique=True)
    state = Column(SQLEnum(ReservationState), default=ReservationState.PENDING, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    confirmed_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)


class Order(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    reservation_id = Column(String, ForeignKey("reservations.id"), nullable=False)
    sku_id = Column(String, ForeignKey("skus.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    state = Column(SQLEnum(ReservationState), default=ReservationState.PENDING, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    confirmed_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
