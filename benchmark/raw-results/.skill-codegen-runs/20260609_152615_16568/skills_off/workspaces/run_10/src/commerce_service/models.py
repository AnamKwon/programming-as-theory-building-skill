from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

RESERVATION_TTL_SECONDS = 3600  # 1 hour


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SKUModel(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True, index=True)
    sku_code = Column(String, unique=True, index=True, nullable=False)
    stock_available = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ReservationModel(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(ReservationStatus), default=ReservationStatus.PENDING, nullable=False)
    idempotency_key = Column(String, unique=True, index=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, default=lambda: datetime.utcnow() + timedelta(seconds=RESERVATION_TTL_SECONDS), nullable=False)


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# Pydantic schemas

class SKUCreate(BaseModel):
    sku_code: str = Field(..., min_length=1, max_length=100)


class SKUResponse(BaseModel):
    id: int
    sku_code: str
    stock_available: int
    created_at: datetime

    model_config = {"from_attributes": True}


class StockAdjustment(BaseModel):
    delta: int = Field(..., description="Change in stock (positive or negative)")


class ReservationCreate(BaseModel):
    sku_id: int
    quantity: int = Field(..., gt=0)
    idempotency_key: Optional[str] = Field(None, min_length=1, max_length=200)


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    order_id: Optional[int]
    quantity: int
    status: ReservationStatus
    created_at: datetime
    expires_at: datetime

    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    id: int
    status: OrderStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderPage(BaseModel):
    total: int
    page: int
    limit: int
    orders: list[OrderResponse]


class ErrorResponse(BaseModel):
    detail: str
