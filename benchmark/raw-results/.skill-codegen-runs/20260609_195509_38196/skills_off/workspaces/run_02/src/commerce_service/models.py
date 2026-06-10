from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Enum as SQLEnum, Integer, String, create_engine
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


# Database Models


class SKU(Base):
    __tablename__ = "skus"
    id = Column(Integer, primary_key=True)
    code = Column(String(100), unique=True, nullable=False, index=True)


class Stock(Base):
    __tablename__ = "stock"
    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, nullable=False, index=True)
    quantity = Column(Integer, default=0)


class Reservation(Base):
    __tablename__ = "reservations"
    id = Column(Integer, primary_key=True)
    idempotency_key = Column(String(255), unique=True, nullable=False, index=True)
    sku_id = Column(Integer, nullable=False, index=True)
    order_id = Column(Integer, nullable=True, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(ReservationStatus), default=ReservationStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)


# Pydantic Request/Response Schemas


class CreateSKURequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=100)


class AdjustStockRequest(BaseModel):
    sku_code: str = Field(..., min_length=1, max_length=100)
    delta: int = Field(..., ge=-1000000, le=1000000)


class CreateReservationRequest(BaseModel):
    sku_code: str = Field(..., min_length=1, max_length=100)
    quantity: int = Field(..., gt=0, le=1000000)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ReservationResponse(BaseModel):
    id: int
    sku_code: str
    quantity: int
    status: ReservationStatus
    created_at: datetime
    expires_at: datetime


class OrderResponse(BaseModel):
    id: int
    sku_code: str
    quantity: int
    status: OrderStatus
    created_at: datetime


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    limit: int
    offset: int
