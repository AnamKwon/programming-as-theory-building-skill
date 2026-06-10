from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Enum as SQLEnum, Integer, String, create_engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class OrderState(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class SKUOrm(Base):
    __tablename__ = "skus"

    sku_id = Column(String(50), primary_key=True)
    stock_level = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ReservationOrm(Base):
    __tablename__ = "reservations"

    reservation_id = Column(String(50), primary_key=True)
    sku_id = Column(String(50), nullable=False)
    quantity = Column(Integer, nullable=False)
    state = Column(SQLEnum(OrderState), nullable=False, default=OrderState.PENDING)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)


class OrderOrm(Base):
    __tablename__ = "orders"

    order_id = Column(String(50), primary_key=True)
    reservation_id = Column(String(50), nullable=False)
    sku_id = Column(String(50), nullable=False)
    quantity = Column(Integer, nullable=False)
    state = Column(SQLEnum(OrderState), nullable=False, default=OrderState.PENDING)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)


class IdempotencyOrm(Base):
    __tablename__ = "idempotency_keys"

    idempotency_key = Column(String(255), primary_key=True)
    response_data = Column(String(4096), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


# Pydantic Request/Response Schemas


class CreateSKURequest(BaseModel):
    sku_id: str = Field(..., min_length=1, max_length=50)
    initial_stock: int = Field(default=0, ge=0)


class CreateSKUResponse(BaseModel):
    sku_id: str
    stock_level: int
    created_at: datetime


class AdjustStockRequest(BaseModel):
    quantity_delta: int = Field(..., description="Can be positive or negative")


class AdjustStockResponse(BaseModel):
    sku_id: str
    stock_level: int
    adjusted_at: datetime


class CreateReservationRequest(BaseModel):
    sku_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class CreateReservationResponse(BaseModel):
    reservation_id: str
    sku_id: str
    quantity: int
    expires_at: datetime
    created_at: datetime


class ConfirmReservationResponse(BaseModel):
    order_id: str
    reservation_id: str
    sku_id: str
    quantity: int
    confirmed_at: datetime


class CancelReservationResponse(BaseModel):
    reservation_id: str
    cancelled_at: datetime


class OrderResponse(BaseModel):
    order_id: str
    reservation_id: str
    sku_id: str
    quantity: int
    state: OrderState
    created_at: datetime
    confirmed_at: Optional[datetime]


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    next_cursor: Optional[str] = None
    has_more: bool


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
