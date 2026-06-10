from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Enum as SQLEnum, Integer, String, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class OrderStatus(str, Enum):
    PENDING_RESERVATION = "pending_reservation"
    RESERVED = "reserved"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


# === ORM Models ===


class SKU(Base):
    __tablename__ = "skus"

    id = Column(String(64), primary_key=True)
    available_stock = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(String(64), primary_key=True)
    sku_id = Column(String(64), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING_RESERVATION)
    idempotency_key = Column(String(255), unique=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=func.now())


class Order(Base):
    __tablename__ = "orders"

    id = Column(String(64), primary_key=True)
    sku_id = Column(String(64), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.CONFIRMED)
    reservation_id = Column(String(64))
    created_at = Column(DateTime, default=func.now())


# === Request/Response Schemas ===


class CreateSKURequest(BaseModel):
    sku_id: str = Field(..., min_length=1, max_length=64)
    initial_stock: int = Field(..., ge=0)


class CreateSKUResponse(BaseModel):
    sku_id: str
    available_stock: int


class AdjustStockRequest(BaseModel):
    delta: int = Field(..., description="Positive to add, negative to remove")


class AdjustStockResponse(BaseModel):
    sku_id: str
    available_stock: int


class CreateReservationRequest(BaseModel):
    sku_id: str = Field(..., min_length=1, max_length=64)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=255)
    ttl_seconds: int = Field(default=3600, ge=60)


class CreateReservationResponse(BaseModel):
    reservation_id: str
    sku_id: str
    quantity: int
    status: str
    expires_at: datetime


class ConfirmReservationResponse(BaseModel):
    order_id: str
    sku_id: str
    quantity: int
    status: str
    created_at: datetime


class OrderResponse(BaseModel):
    order_id: str
    sku_id: str
    quantity: int
    status: str
    created_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    limit: int
    offset: int


class HealthResponse(BaseModel):
    status: str
