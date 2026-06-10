from datetime import datetime
from enum import Enum

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
    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SKUModel(Base):
    __tablename__ = "skus"

    sku_code = Column(String(50), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)


class StockModel(Base):
    __tablename__ = "stocks"

    id = Column(Integer, primary_key=True)
    sku_code = Column(String(50), nullable=False, index=True)
    available = Column(Integer, nullable=False, default=0)
    reserved = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ReservationModel(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    sku_code = Column(String(50), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default=ReservationStatus.PENDING)
    idempotency_key = Column(String(100), unique=True, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    sku_code = Column(String(50), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default=OrderStatus.PENDING)
    reservation_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CreateSKURequest(BaseModel):
    sku_code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=500)


class AdjustStockRequest(BaseModel):
    sku_code: str = Field(..., min_length=1, max_length=50)
    quantity: int = Field(..., ge=-10000, le=10000)


class CreateReservationRequest(BaseModel):
    sku_code: str = Field(..., min_length=1, max_length=50)
    quantity: int = Field(..., ge=1, le=10000)
    idempotency_key: str | None = Field(None, max_length=100)
    reservation_duration_seconds: int = Field(default=3600, ge=60, le=86400)


class SKUResponse(BaseModel):
    sku_code: str
    name: str
    description: str | None
    created_at: datetime


class StockResponse(BaseModel):
    sku_code: str
    available: int
    reserved: int


class ReservationResponse(BaseModel):
    id: int
    sku_code: str
    quantity: int
    status: str
    created_at: datetime
    expires_at: datetime


class OrderResponse(BaseModel):
    id: int
    sku_code: str
    quantity: int
    status: str
    created_at: datetime
    updated_at: datetime


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    offset: int
    limit: int


class ErrorResponse(BaseModel):
    code: str
    message: str
