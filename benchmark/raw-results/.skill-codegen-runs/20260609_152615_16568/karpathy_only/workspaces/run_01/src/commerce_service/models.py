from datetime import datetime
from typing import Optional
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import Column, String, Integer, DateTime, Enum as SQLEnum
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class OrderStatus(str, Enum):
    PENDING = "pending"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


# SQLAlchemy Models
class SKUModel(Base):
    __tablename__ = "skus"

    sku_id = Column(String, primary_key=True)
    quantity = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReservationModel(Base):
    __tablename__ = "reservations"

    reservation_id = Column(String, primary_key=True)
    sku_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(ReservationStatus), default=ReservationStatus.PENDING)
    idempotency_key = Column(String, unique=True, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class OrderModel(Base):
    __tablename__ = "orders"

    order_id = Column(String, primary_key=True)
    reservation_id = Column(String, nullable=False)
    sku_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Pydantic Request Models
class CreateSKURequest(BaseModel):
    sku_id: str = Field(..., min_length=1, max_length=100)
    quantity: int = Field(..., ge=0)


class AdjustStockRequest(BaseModel):
    adjustment: int = Field(..., ge=-1000000, le=1000000)


class CreateReservationRequest(BaseModel):
    sku_id: str = Field(..., min_length=1, max_length=100)
    quantity: int = Field(..., ge=1)
    idempotency_key: Optional[str] = Field(None, max_length=255)


# Pydantic Response Models
class SKUResponse(BaseModel):
    sku_id: str
    quantity: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ReservationResponse(BaseModel):
    reservation_id: str
    sku_id: str
    quantity: int
    status: ReservationStatus
    expires_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    order_id: str
    reservation_id: str
    sku_id: str
    quantity: int
    status: OrderStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    next_cursor: Optional[str] = None
