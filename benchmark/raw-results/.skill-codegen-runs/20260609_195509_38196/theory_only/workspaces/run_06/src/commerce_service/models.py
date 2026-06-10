"""Data models for ORM and API validation."""

from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Enum as SQLEnum, Integer, String, create_engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ReservationStatus(str, Enum):
    """Reservation lifecycle states."""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderStatus(str, Enum):
    """Order lifecycle states."""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


# ORM Models

class SKU(Base):
    __tablename__ = "skus"

    sku_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Stock(Base):
    __tablename__ = "stock"

    sku_id = Column(String, primary_key=True)
    quantity = Column(Integer, default=0, nullable=False)
    reserved = Column(Integer, default=0, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Reservation(Base):
    __tablename__ = "reservations"

    reservation_id = Column(String, primary_key=True)
    sku_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(ReservationStatus), default=ReservationStatus.PENDING, nullable=False)
    idempotency_key = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    confirmed_at = Column(DateTime, nullable=True)


class Order(Base):
    __tablename__ = "orders"

    order_id = Column(String, primary_key=True)
    reservation_id = Column(String, nullable=False)
    sku_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    confirmed_at = Column(DateTime, nullable=True)


class StockAdjustmentRequest(BaseModel):
    """Request to adjust stock level."""
    sku_id: str = Field(..., min_length=1, max_length=255)
    delta: int = Field(..., description="Quantity delta (positive or negative)")
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class SKUCreateRequest(BaseModel):
    """Request to create a SKU."""
    sku_id: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)


class SKUResponse(BaseModel):
    """SKU detail response."""
    sku_id: str
    name: str
    available_quantity: int
    reserved_quantity: int
    created_at: datetime


class ReservationCreateRequest(BaseModel):
    """Request to create a reservation."""
    sku_id: str = Field(..., min_length=1, max_length=255)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=255)
    ttl_seconds: int = Field(default=1800, ge=60, le=86400)


class ReservationResponse(BaseModel):
    """Reservation detail response."""
    reservation_id: str
    sku_id: str
    quantity: int
    status: ReservationStatus
    created_at: datetime
    expires_at: datetime


class OrderResponse(BaseModel):
    """Order detail response."""
    order_id: str
    reservation_id: str
    sku_id: str
    quantity: int
    status: OrderStatus
    created_at: datetime
    confirmed_at: datetime | None = None


class OrdersListResponse(BaseModel):
    """Paginated orders list response."""
    orders: list[OrderResponse]
    total: int
    limit: int
    offset: int


class ErrorDetail(BaseModel):
    """Error response structure."""
    error: str
    detail: str
    status_code: int


def init_db(database_url: str = "sqlite:///:memory:"):
    """Initialize database and create tables."""
    engine = create_engine(database_url, echo=False)
    Base.metadata.create_all(engine)
    return engine
