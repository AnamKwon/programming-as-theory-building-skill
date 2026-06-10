from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, DateTime, Enum as SQLEnum, Float
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class ReservationStatus(str, Enum):
    ACTIVE = "active"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


# SQLAlchemy ORM Models
class SKUModel(Base):
    __tablename__ = "skus"

    id = Column(String(50), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(String(1000))
    created_at = Column(DateTime, default=datetime.utcnow)


class StockModel(Base):
    __tablename__ = "stock"

    sku_id = Column(String(50), primary_key=True)
    available = Column(Integer, default=0)
    reserved = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ReservationModel(Base):
    __tablename__ = "reservations"

    id = Column(String(50), primary_key=True)
    sku_id = Column(String(50), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(ReservationStatus), default=ReservationStatus.ACTIVE)
    idempotency_key = Column(String(255), unique=True, nullable=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(String(50), primary_key=True)
    reservation_id = Column(String(50), nullable=False)
    sku_id = Column(String(50), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Pydantic Request/Response Models
class SKUCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)


class SKUResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    created_at: datetime


class StockAdjust(BaseModel):
    quantity: int = Field(..., description="Signed adjustment (positive/negative)")


class StockResponse(BaseModel):
    sku_id: str
    available: int
    reserved: int


class ReservationCreate(BaseModel):
    sku_id: str = Field(..., min_length=1, max_length=50)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ReservationResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    status: ReservationStatus
    expires_at: datetime
    created_at: datetime


class OrderResponse(BaseModel):
    id: str
    reservation_id: str
    sku_id: str
    quantity: int
    status: OrderStatus
    created_at: datetime
    updated_at: datetime


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    next_cursor: Optional[str]


class ErrorResponse(BaseModel):
    detail: str
    code: str
