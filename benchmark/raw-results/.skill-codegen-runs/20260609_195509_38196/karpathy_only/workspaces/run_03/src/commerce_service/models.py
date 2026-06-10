"""Data models for requests, responses, and ORM."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Enum as SQLEnum, Integer, String, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class OrderStatus(str, Enum):
    RESERVED = "reserved"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# ===== ORM Models =====


class SKUModel(Base):
    __tablename__ = "skus"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)


class StockModel(Base):
    __tablename__ = "stock"

    sku_id = Column(String, primary_key=True)
    quantity = Column(Integer, default=0, nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)


class ReservationModel(Base):
    __tablename__ = "reservations"

    id = Column(String, primary_key=True)
    sku_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(ReservationStatus), default=ReservationStatus.PENDING, nullable=False)
    idempotency_key = Column(String, unique=True, nullable=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    reservation_id = Column(String, unique=True, nullable=False, index=True)
    sku_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.RESERVED, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)


# ===== Request/Response Schemas =====


class SKUCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)


class SKUResponse(BaseModel):
    id: str
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class StockAdjust(BaseModel):
    delta: int = Field(..., description="Positive to add, negative to remove")


class StockResponse(BaseModel):
    sku_id: str
    quantity: int
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReservationCreate(BaseModel):
    sku_id: str = Field(..., min_length=1, max_length=100)
    quantity: int = Field(..., gt=0)
    idempotency_key: Optional[str] = Field(None, min_length=1, max_length=255)


class ReservationResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    status: ReservationStatus
    expires_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    id: str
    reservation_id: str
    sku_id: str
    quantity: int
    status: OrderStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
