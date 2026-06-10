"""Domain and data models."""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Column, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import declarative_base


def utc_now():
    return datetime.now(timezone.utc)

Base = declarative_base()


class OrderStatus(str, Enum):
    PENDING = "pending"
    RESERVED = "reserved"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


# === SQLAlchemy ORM Models ===


class SKU(Base):
    __tablename__ = "skus"

    id = Column(String(64), primary_key=True)
    name = Column(String(256), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class StockLevel(Base):
    __tablename__ = "stock_levels"

    sku_id = Column(String(64), primary_key=True)
    available = Column(Integer, nullable=False, default=0)
    reserved = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(String(64), primary_key=True)
    sku_id = Column(String(64), nullable=False)
    quantity = Column(Integer, nullable=False)
    idempotency_key = Column(String(256), unique=True, nullable=True)
    status = Column(String(32), nullable=False, default=OrderStatus.PENDING.value)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)


class Order(Base):
    __tablename__ = "orders"

    id = Column(String(64), primary_key=True)
    reservation_id = Column(String(64), nullable=False)
    sku_id = Column(String(64), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False, default=OrderStatus.CONFIRMED.value)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)


# === Pydantic Models ===


class SKUCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=256)


class SKUResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    created_at: datetime


class StockAdjustment(BaseModel):
    quantity_delta: int = Field(..., description="Positive for increase, negative for decrease")


class StockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sku_id: str
    available: int
    reserved: int
    updated_at: datetime


class ReservationCreate(BaseModel):
    sku_id: str = Field(..., min_length=1, max_length=64)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(None, max_length=256)


class ReservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sku_id: str
    quantity: int
    status: str
    expires_at: datetime
    created_at: datetime


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    reservation_id: str
    sku_id: str
    quantity: int
    status: str
    created_at: datetime
    updated_at: datetime


class OrderList(BaseModel):
    orders: list[OrderResponse]
    total: int
    page: int
    page_size: int
    pages: int
