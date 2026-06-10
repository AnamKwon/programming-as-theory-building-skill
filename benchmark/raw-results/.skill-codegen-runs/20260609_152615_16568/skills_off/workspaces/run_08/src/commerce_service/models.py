from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Enum as SQLEnum, Integer, String, create_engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# SQLAlchemy Models
class SKU(Base):
    __tablename__ = "skus"
    id = Column(Integer, primary_key=True)
    code = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)


class Stock(Base):
    __tablename__ = "stock"
    sku_id = Column(Integer, primary_key=True)
    available_qty = Column(Integer, default=0, nullable=False)
    reserved_qty = Column(Integer, default=0, nullable=False)


class Reservation(Base):
    __tablename__ = "reservations"
    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    idempotency_key = Column(String(255), unique=True, nullable=False, index=True)
    status = Column(SQLEnum(ReservationStatus), default=ReservationStatus.PENDING, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, nullable=False, index=True)
    sku_id = Column(Integer, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    confirmed_at = Column(DateTime, nullable=True)


# Pydantic Request/Response Models
class SKUCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)


class SKUResponse(BaseModel):
    id: int
    code: str
    name: str


class StockAdjustRequest(BaseModel):
    sku_id: int
    quantity_delta: int = Field(..., description="Change in available stock (can be negative)")


class ReservationCreate(BaseModel):
    sku_id: int
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=255)
    reservation_ttl_seconds: int = Field(default=300, ge=1)


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: ReservationStatus
    expires_at: datetime
    created_at: datetime


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    sku_id: int
    quantity: int
    status: OrderStatus
    created_at: datetime
    confirmed_at: Optional[datetime] = None


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    offset: int
    limit: int
