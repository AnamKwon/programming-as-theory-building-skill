from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, create_engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderStatus(str, Enum):
    RESERVED = "reserved"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


# SQLAlchemy ORM Models


class SKU(Base):
    __tablename__ = "skus"

    product_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    current_stock = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(String, primary_key=True)
    product_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, default=ReservationStatus.PENDING, nullable=False)
    idempotency_key = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime, nullable=False)


class Order(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    reservation_id = Column(String, nullable=False)
    product_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, default=OrderStatus.RESERVED, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


# Pydantic Request/Response Models


class CreateSKURequest(BaseModel):
    product_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    initial_stock: int = Field(default=0, ge=0)


class AdjustStockRequest(BaseModel):
    quantity_delta: int = Field(..., description="Positive or negative integer to adjust stock")


class CreateReservationRequest(BaseModel):
    product_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, description="Unique key for idempotency")


class ReservationResponse(BaseModel):
    id: str
    product_id: str
    quantity: int
    status: ReservationStatus
    created_at: datetime
    expires_at: datetime


class OrderResponse(BaseModel):
    id: str
    reservation_id: str
    product_id: str
    quantity: int
    status: OrderStatus
    created_at: datetime
    updated_at: datetime


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    limit: int
    offset: int


class SKUResponse(BaseModel):
    product_id: str
    name: str
    current_stock: int
    created_at: datetime


class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str
