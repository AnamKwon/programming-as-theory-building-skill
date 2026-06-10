from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Enum as SQLEnum, Integer, String, create_engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ReservationState(str, Enum):
    RESERVED = "reserved"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


# ============================================================================
# SQLAlchemy Models (Database Layer)
# ============================================================================


class SKURecord(Base):
    __tablename__ = "skus"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    available_stock = Column(Integer, default=0)
    reserved_stock = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReservationRecord(Base):
    __tablename__ = "reservations"

    id = Column(String, primary_key=True)
    sku_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    state = Column(SQLEnum(ReservationState), default=ReservationState.RESERVED)
    idempotency_key = Column(String, nullable=True, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    confirmed_at = Column(DateTime, nullable=True)


# ============================================================================
# Pydantic Models (API Layer)
# ============================================================================


class SKUCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    initial_stock: int = Field(default=0, ge=0)


class SKUResponse(BaseModel):
    id: str
    name: str
    available_stock: int
    reserved_stock: int
    created_at: datetime


class StockAdjustment(BaseModel):
    sku_id: str
    quantity: int = Field(..., description="Positive for increase, negative for decrease")


class ReservationCreate(BaseModel):
    sku_id: str
    quantity: int = Field(..., gt=0)
    idempotency_key: Optional[str] = Field(None, max_length=200)


class ReservationResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    state: ReservationState
    created_at: datetime
    expires_at: Optional[datetime]
    confirmed_at: Optional[datetime]


class OrderResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    state: ReservationState
    created_at: datetime
    expires_at: Optional[datetime]
    confirmed_at: Optional[datetime]


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    page: int
    page_size: int


class ErrorResponse(BaseModel):
    detail: str
    error_code: str = "INTERNAL_ERROR"
